"""
Survey endpoints. QA uploads the responses and manages the mappings; QA and
department admins read the results. Students and teachers see none of it.
"""
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GraduateAttribute, Program, SurveyMapping, SurveyResponse, SurveyUpload
from .permissions import IsDeptAdminOrQA, IsQA
from .surveys import (
    SURVEY_FORMS, SURVEY_KPI, batch_code, current_mapping, parse_rating, question_results,
)

MAX_ROWS = 5000


def _user_department(user):
    for attr in ('qa_profile', 'dept_admin_profile'):
        profile = getattr(user, attr, None)
        if profile:
            return profile.department
    return None


def _scoped_program(request, program_id):
    """The program if the user may see it, else None. A superadmin has no department."""
    program = Program.objects.select_related('department').filter(code__iexact=program_id).first()
    if not program:
        return None
    department = _user_department(request.user)
    if request.user.role != 'admin' and (not department or program.department_id != department.id):
        return None
    return program


def _targets(program, form_type):
    if SURVEY_FORMS[form_type]['usedFor'] == 'GA':
        gas = GraduateAttribute.objects.filter(program=program)
        return [{'id': g.ga_id, 'name': g.name} for g in gas]
    return [{'id': o.code, 'name': o.description} for o in program.objectives.all()]


class SurveyFormsView(APIView):
    """GET /api/surveys/forms/?programId=bscs: the four forms with this program's mappings."""
    permission_classes = [IsDeptAdminOrQA]

    def get(self, request):
        program = _scoped_program(request, request.query_params.get('programId', '').strip())
        if not program:
            return Response({'error': 'Program not found'}, status=status.HTTP_404_NOT_FOUND)
        forms = []
        for form_type, form in SURVEY_FORMS.items():
            mapping = current_mapping(program, form_type)
            forms.append({
                'formType': form_type,
                'title':    form['title'],
                'usedFor':  form['usedFor'],
                'targets':  _targets(program, form_type),
                'questions': [
                    {'no': i, 'text': text, 'target': mapping.get(i, '')}
                    for i, text in enumerate(form['questions'], start=1)
                ],
            })
        return Response({'programId': program.code.lower(), 'forms': forms})


class SurveyMappingView(APIView):
    """
    PUT /api/surveys/mapping/ { programId, formType, mapping: {question no: target} }
    Past results keep the mapping saved with their upload.
    """
    permission_classes = [IsQA]

    def put(self, request):
        program = _scoped_program(request, str(request.data.get('programId', '')).strip())
        form_type = request.data.get('formType')
        if not program or form_type not in SURVEY_FORMS:
            return Response({'error': 'Program or form not found'}, status=status.HTTP_404_NOT_FOUND)
        mapping = request.data.get('mapping')
        if not isinstance(mapping, dict):
            return Response({'error': 'mapping is required'}, status=status.HTTP_400_BAD_REQUEST)

        allowed = {t['id'] for t in _targets(program, form_type)}
        question_count = len(SURVEY_FORMS[form_type]['questions'])
        rows = {}
        for key, target in mapping.items():
            if not str(key).isdigit() or not 1 <= int(key) <= question_count:
                return Response({'error': f'Question "{key}" is not on this form.'}, status=status.HTTP_400_BAD_REQUEST)
            target = str(target or '').strip()
            if target and target not in allowed:
                return Response({'error': f'"{target}" does not belong to {program.code}.'}, status=status.HTTP_400_BAD_REQUEST)
            rows[int(key)] = target

        with transaction.atomic():
            for no, target in rows.items():
                SurveyMapping.objects.update_or_create(
                    program=program, form_type=form_type, question_no=no, defaults={'target': target})
        return Response({'saved': len(rows)})


def _clean(row, key, limit=200):
    return str(row.get(key) or '').strip()[:limit]


def _find_program(value, department, default):
    """A program from the form's Program answer: its code, its name, or part of its name."""
    text = str(value or '').strip().lower()
    programs = list(Program.objects.filter(department=department))
    if not text:
        return default
    for program in programs:
        if text == program.code.lower() or text == program.name.lower():
            return program
    matches = [p for p in programs if p.code.lower() in text or text in p.name.lower() or p.name.lower() in text]
    return matches[0] if len(matches) == 1 else None


class SurveyUploadView(APIView):
    """
    GET  /api/surveys/uploads/
    POST /api/surveys/uploads/ { formType, year, fileName, defaultProgramId?, rows, dryRun? }

    The browser reads the downloaded file and sends one object per response:
    { program, regNo, batch, section, graduationYear, respondentName, respondentEmail,
      supervisorName, employeeName, designation, organization, organizationType,
      workingSince, comment, submittedAt, ratings: {question no: answer} }

    Bad rows are reported and left out. A file for a form and year that already
    has one replaces it, so nothing counts twice. dryRun checks without saving.
    """

    def get_permissions(self):
        return [IsDeptAdminOrQA()] if self.request.method == 'GET' else [IsQA()]

    def get(self, request):
        uploads = SurveyUpload.objects.select_related('uploaded_by')
        department = _user_department(request.user)
        if request.user.role != 'admin':
            uploads = uploads.filter(department=department)
        return Response([{
            'id':          u.id,
            'formType':    u.form_type,
            'formTitle':   u.get_form_type_display(),
            'year':        u.year,
            'fileName':    u.file_name,
            'responses':   u.responses.count(),
            'uploadedAt':  u.uploaded_at,
            'uploadedBy':  u.uploaded_by.get_full_name() if u.uploaded_by else '',
        } for u in uploads])

    def post(self, request):
        department = _user_department(request.user)
        if not department:
            return Response({'error': 'QA profile not found'}, status=status.HTTP_403_FORBIDDEN)
        form_type = request.data.get('formType')
        if form_type not in SURVEY_FORMS:
            return Response({'error': 'Choose one of the four forms.'}, status=status.HTTP_400_BAD_REQUEST)
        year = str(request.data.get('year', '')).strip()
        if not year.isdigit() or not 2000 <= int(year) <= 2100:
            return Response({'error': 'Choose the year these responses were collected.'}, status=status.HTTP_400_BAD_REQUEST)
        rows = request.data.get('rows')
        if not isinstance(rows, list) or not rows:
            return Response({'error': 'The file has no responses.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > MAX_ROWS:
            return Response({'error': f'A file can have at most {MAX_ROWS} responses.'}, status=status.HTTP_400_BAD_REQUEST)

        default_id = str(request.data.get('defaultProgramId') or '').strip()
        default = Program.objects.filter(department=department, code__iexact=default_id).first() if default_id else None
        question_count = len(SURVEY_FORMS[form_type]['questions'])

        cleaned, errors = [], []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                errors.append({'row': index, 'error': 'Not a response.'})
                continue
            program = _find_program(row.get('program'), department, default)
            if not program:
                errors.append({'row': index, 'error': f'Program "{row.get("program") or ""}" was not recognized.'})
                continue
            ratings, row_error = {}, None
            for key, answer in (row.get('ratings') or {}).items():
                if not str(key).isdigit() or not 1 <= int(key) <= question_count:
                    continue
                try:
                    rating = parse_rating(answer)
                except ValueError as e:
                    row_error = f'Question {key}: {e}'
                    break
                if rating is not None:
                    ratings[str(int(key))] = rating
            if row_error or not ratings:
                errors.append({'row': index, 'error': row_error or 'No ratings were answered.'})
                continue
            graduation_year = None
            text_year = str(row.get('graduationYear') or '').strip()
            if text_year[:4].isdigit():
                graduation_year = int(text_year[:4])
            reg_no = _clean(row, 'regNo', 60)
            cleaned.append(SurveyResponse(
                program=program, ratings=ratings, reg_no=reg_no,
                batch=batch_code(row.get('batch')) or batch_code(reg_no),
                section=_clean(row, 'section', 30), graduation_year=graduation_year,
                respondent_name=_clean(row, 'respondentName'), respondent_email=_clean(row, 'respondentEmail', 254),
                supervisor_name=_clean(row, 'supervisorName'), employee_name=_clean(row, 'employeeName'),
                designation=_clean(row, 'designation'), organization=_clean(row, 'organization'),
                organization_type=_clean(row, 'organizationType', 60), working_since=_clean(row, 'workingSince', 60),
                comment=str(row.get('comment') or '').strip(), submitted_at=_clean(row, 'submittedAt', 40),
            ))

        existing = SurveyUpload.objects.filter(department=department, form_type=form_type, year=int(year)).first()
        per_program = {}
        for response in cleaned:
            per_program[response.program.code] = per_program.get(response.program.code, 0) + 1
        summary = {
            'accepted': len(cleaned), 'skipped': len(errors), 'errors': errors[:50],
            'programs': per_program, 'replaces': existing.responses.count() if existing else None,
        }
        if request.data.get('dryRun') is True:
            return Response({'dryRun': True, **summary})
        if not cleaned:
            return Response({'error': 'No response could be saved.', **summary}, status=status.HTTP_400_BAD_REQUEST)

        snapshot = {}
        for response in cleaned:
            code = response.program.code.upper()
            if code not in snapshot:
                snapshot[code] = {str(k): v for k, v in current_mapping(response.program, form_type).items()}
        with transaction.atomic():
            if existing:
                existing.delete()
            upload = SurveyUpload.objects.create(
                department=department, form_type=form_type, year=int(year),
                file_name=_clean(request.data, 'fileName', 255), mapping_snapshot=snapshot, uploaded_by=request.user,
            )
            for response in cleaned:
                response.upload = upload
            SurveyResponse.objects.bulk_create(cleaned)
        return Response({'id': upload.id, **summary}, status=status.HTTP_201_CREATED)


class SurveyUploadDetailView(APIView):
    """DELETE /api/surveys/uploads/<id>/"""
    permission_classes = [IsQA]

    def delete(self, request, upload_id):
        upload = SurveyUpload.objects.filter(pk=upload_id, department=_user_department(request.user)).first()
        if not upload:
            return Response({'error': 'Upload not found'}, status=status.HTTP_404_NOT_FOUND)
        upload.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SurveyResultsView(APIView):
    """
    GET /api/surveys/results/?programId=bscs&formType=exit[&year=2026]
    Each question against the KPI, the comments without names, and the named
    responses, for QA and department admins.
    """
    permission_classes = [IsDeptAdminOrQA]

    def get(self, request):
        program = _scoped_program(request, request.query_params.get('programId', '').strip())
        form_type = request.query_params.get('formType')
        if not program or form_type not in SURVEY_FORMS:
            return Response({'error': 'Program or form not found'}, status=status.HTTP_404_NOT_FOUND)
        year = request.query_params.get('year', '').strip()
        year = int(year) if year.isdigit() else None

        questions, response_count = question_results(program, form_type, year=year)
        responses = SurveyResponse.objects.filter(program=program, upload__form_type=form_type).select_related('upload')
        if year:
            responses = responses.filter(upload__year=year)
        return Response({
            'programId':  program.code.lower(),
            'programName': program.name,
            'formType':   form_type,
            'formTitle':  SURVEY_FORMS[form_type]['title'],
            'usedFor':    SURVEY_FORMS[form_type]['usedFor'],
            'year':       year,
            'years':      sorted(set(SurveyResponse.objects.filter(program=program, upload__form_type=form_type)
                                     .values_list('upload__year', flat=True))),
            'kpi':        SURVEY_KPI,
            'responseCount': response_count,
            'questions':  questions,
            'comments':   [r.comment for r in responses if r.comment],
            'responses':  [{
                'year':         r.upload.year,
                'name':         r.respondent_name,
                'email':        r.respondent_email,
                'regNo':        r.reg_no,
                'batch':        r.batch,
                'graduationYear': r.graduation_year,
                'supervisor':   r.supervisor_name,
                'employee':     r.employee_name,
                'organization': r.organization,
                'ratings':      r.ratings,
            } for r in responses],
        })
