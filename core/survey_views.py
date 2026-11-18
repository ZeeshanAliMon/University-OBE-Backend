"""
Survey endpoints. QA uploads the responses and manages the mappings; QA and
department admins read the results. Students and teachers see none of it.
"""
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GraduateAttribute, Program, SurveyMapping, SurveyQuestionText, SurveyResponse, SurveyUpload
from .permissions import IsDeptAdminOrQA, IsQA
from .models import AdmissionStudent
from .surveys import (
    SURVEY_FORMS, SURVEY_KPI, batch_code, batch_sort_key, current_mapping, department_targets, form_questions,
    meaningful_comment, parse_rating, parse_year, question_results, rating_stats,
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
                    for i, text in enumerate(form_questions(program.department, form_type), start=1)
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


class SurveyQuestionView(APIView):
    """
    PUT /api/surveys/questions/ { programId, formType, questionNo, text }
    Changes a question's wording for the program's department. Its number stays,
    so responses already uploaded still count for the same question.
    """
    permission_classes = [IsQA]

    def put(self, request):
        program = _scoped_program(request, str(request.data.get('programId', '')).strip())
        form_type = request.data.get('formType')
        if not program or form_type not in SURVEY_FORMS:
            return Response({'error': 'Program or form not found'}, status=status.HTTP_404_NOT_FOUND)

        questions = form_questions(program.department, form_type)
        number = str(request.data.get('questionNo', '')).strip()
        if not number.isdigit() or not 1 <= int(number) <= len(questions):
            return Response({'error': f'Question "{number}" is not on this form.'}, status=status.HTTP_400_BAD_REQUEST)
        question_no = int(number)

        text = ' '.join(str(request.data.get('text') or '').split())
        limit = SurveyQuestionText._meta.get_field('text').max_length
        if not text:
            return Response({'error': 'Write the question.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(text) > limit:
            return Response({'error': f'A question can have at most {limit} characters.'}, status=status.HTTP_400_BAD_REQUEST)
        # Uploaded files are matched to questions by their wording, so each must be distinct.
        for no, other in enumerate(questions, start=1):
            if no != question_no and other.casefold() == text.casefold():
                return Response({'error': f'Question {no} already has this wording.'}, status=status.HTTP_400_BAD_REQUEST)

        SurveyQuestionText.objects.update_or_create(
            department=program.department, form_type=form_type, question_no=question_no, defaults={'text': text})
        return Response({'no': question_no, 'text': text})


def _clean(row, key, limit=200):
    return str(row.get(key) or '').strip()[:limit]


def _find_program(value, department, default):
    """
    A program from the form's Program answer: its code (BSCS), the end of its code
    (CS, AI), its name, or part of its name. None when it names no programme, as
    forms often say "Unknown".
    """
    text = str(value or '').strip().lower()
    programs = list(Program.objects.filter(department=department))
    if not text:
        return default
    for program in programs:
        if text == program.code.lower() or text == program.name.lower():
            return program
    matches = [p for p in programs if p.code.lower() in text or text in p.name.lower() or p.name.lower() in text]
    if len(matches) == 1:
        return matches[0]
    if len(text) >= 2 and text.isalpha():
        suffix = [p for p in programs if p.code.lower().endswith(text)]
        if len(suffix) == 1:
            return suffix[0]
    return default


class SurveyUploadView(APIView):
    """
    GET  /api/surveys/uploads/
    POST /api/surveys/uploads/ { formType, year?, fileName, defaultProgramId?, rows, dryRun? }

    The browser reads the downloaded file and sends one object per response:
    { program, year, regNo, batch, section, graduationYear, respondentName, respondentEmail,
      supervisorName, employeeName, designation, organization, organizationType,
      workingSince, comment, submittedAt, ratings: {question no: answer} }

    Each response's year comes from its own year column ("Summer 2026"), else its
    graduation year, else `year`. A batch it can't read ("2022") becomes
    `defaultBatch`. A Program answer that names no programme ("Unknown") is kept as
    "Not specified": it counts in batch totals, not in any programme's. Bad rows
    are reported and left out. Saving replaces the responses this
    form already has for the years in the file, so a cumulative file can be
    uploaded again without counting anything twice. dryRun checks without saving.
    """

    def get_permissions(self):
        return [IsDeptAdminOrQA()] if self.request.method == 'GET' else [IsQA()]

    def get(self, request):
        uploads = SurveyUpload.objects.select_related('uploaded_by').prefetch_related('responses')
        department = _user_department(request.user)
        if request.user.role != 'admin':
            uploads = uploads.filter(department=department)
        return Response([{
            'id':          u.id,
            'formType':    u.form_type,
            'formTitle':   u.get_form_type_display(),
            'years':       sorted({r.year for r in u.responses.all()}),
            'fileName':    u.file_name,
            'responses':   len(u.responses.all()),
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
        year = str(request.data.get('year') or '').strip()
        if year and (not year.isdigit() or not 2000 <= int(year) <= 2100):
            return Response({'error': 'The year must be like 2026.'}, status=status.HTTP_400_BAD_REQUEST)
        default_year = int(year) if year else None
        rows = request.data.get('rows')
        if not isinstance(rows, list) or not rows:
            return Response({'error': 'The file has no responses.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > MAX_ROWS:
            return Response({'error': f'A file can have at most {MAX_ROWS} responses.'}, status=status.HTTP_400_BAD_REQUEST)

        default_id = str(request.data.get('defaultProgramId') or '').strip()
        default = Program.objects.filter(department=department, code__iexact=default_id).first() if default_id else None
        default_batch = batch_code(request.data.get('defaultBatch'))
        unrecognized = {}
        question_count = len(SURVEY_FORMS[form_type]['questions'])

        cleaned, errors = [], []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                errors.append({'row': index, 'error': 'Not a response.'})
                continue
            program = _find_program(row.get('program'), department, default)
            if not program:
                answer = str(row.get('program') or '').strip() or '(blank)'
                unrecognized[answer] = unrecognized.get(answer, 0) + 1
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
            row_year = parse_year(row.get('year')) or parse_year(row.get('graduationYear')) or default_year
            if not row_year:
                errors.append({'row': index, 'error': 'No year: the row has none and no year was given for the file.'})
                continue
            graduation_year = None
            text_year = str(row.get('graduationYear') or '').strip()
            if text_year[:4].isdigit():
                graduation_year = int(text_year[:4])
            reg_no = _clean(row, 'regNo', 60)
            cleaned.append(SurveyResponse(
                program=program, ratings=ratings, reg_no=reg_no, year=row_year, period=_clean(row, 'year', 40),
                batch=batch_code(row.get('batch')) or batch_code(reg_no) or default_batch,
                section=_clean(row, 'section', 30), graduation_year=graduation_year,
                respondent_name=_clean(row, 'respondentName'), respondent_email=_clean(row, 'respondentEmail', 254),
                supervisor_name=_clean(row, 'supervisorName'), employee_name=_clean(row, 'employeeName'),
                designation=_clean(row, 'designation'), organization=_clean(row, 'organization'),
                organization_type=_clean(row, 'organizationType', 60), working_since=_clean(row, 'workingSince', 60),
                comment=str(row.get('comment') or '').strip(), submitted_at=_clean(row, 'submittedAt', 40),
            ))

        per_program, per_year, per_batch = {}, {}, {}
        for response in cleaned:
            code = response.program.code if response.program else 'Not specified'
            per_program[code] = per_program.get(code, 0) + 1
            per_year[response.year] = per_year.get(response.year, 0) + 1
            per_batch[response.batch or 'Not recorded'] = per_batch.get(response.batch or 'Not recorded', 0) + 1
        replaced = SurveyResponse.objects.filter(
            upload__department=department, upload__form_type=form_type, year__in=list(per_year))
        summary = {
            'accepted': len(cleaned), 'skipped': len(errors), 'errors': errors[:50],
            'programs': per_program, 'years': {str(y): n for y, n in sorted(per_year.items())},
            'batches': per_batch, 'unrecognizedPrograms': unrecognized,
            'replaces': replaced.count() or None,
        }
        if request.data.get('dryRun') is True:
            return Response({'dryRun': True, **summary})
        if not cleaned:
            return Response({'error': 'No response could be saved.', **summary}, status=status.HTTP_400_BAD_REQUEST)

        snapshot = {}
        for response in cleaned:
            if not response.program:
                continue
            code = response.program.code.upper()
            if code not in snapshot:
                # Questions not mapped yet are left out, so they count once QA maps them.
                snapshot[code] = {str(k): v for k, v in current_mapping(response.program, form_type).items() if v}
        with transaction.atomic():
            replaced.delete()
            SurveyUpload.objects.filter(department=department, form_type=form_type, responses__isnull=True).delete()
            upload = SurveyUpload.objects.create(
                department=department, form_type=form_type, year=default_year,
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
    GET /api/surveys/results/?programId=bscs&formType=exit[&year=2026][&batch=SP23]
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
        batch = batch_code(request.query_params.get('batch', ''))

        questions, response_count = question_results(program, form_type, year=year, batches=[batch] if batch else None)
        all_responses = SurveyResponse.objects.filter(program=program, upload__form_type=form_type)
        responses = all_responses.select_related('upload')
        if year:
            responses = responses.filter(year=year)
        if batch:
            responses = responses.filter(batch=batch)
        return Response({
            'programId':  program.code.lower(),
            'programName': program.name,
            'formType':   form_type,
            'formTitle':  SURVEY_FORMS[form_type]['title'],
            'usedFor':    SURVEY_FORMS[form_type]['usedFor'],
            'year':       year,
            'batch':      batch or None,
            'years':      sorted(set(all_responses.values_list('year', flat=True))),
            'batches':    sorted(set(all_responses.exclude(batch='').values_list('batch', flat=True)),
                                 key=lambda b: (b[2:], b[:2] != 'SP')),
            'kpi':        SURVEY_KPI,
            'responseCount': response_count,
            'questions':  questions,
            'comments':   [r.comment for r in responses if r.comment],
            'responses':  [{
                'year':         r.year,
                'period':       r.period,
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


class SurveyAnalysisView(APIView):
    """
    GET /api/surveys/analysis/?formType=exit[&groups=SP22,FA22]

    The data for a survey analysis report in the university's format: respondents
    by programme and batch, each KPI's average rating and share rated 3 or above,
    per programme within each batch, per batch and consolidated, and the written
    comments. Internship and exit responses are grouped by batch; alumni and
    employer responses by graduation year. groups limits the report to some.
    """
    permission_classes = [IsDeptAdminOrQA]

    def get(self, request):
        form_type = request.query_params.get('formType')
        if form_type not in SURVEY_FORMS:
            return Response({'error': 'Form not found'}, status=status.HTTP_404_NOT_FOUND)
        department = _user_department(request.user)
        if not department:
            return Response({'error': 'Department not found'}, status=status.HTTP_403_FORBIDDEN)

        form = SURVEY_FORMS[form_type]
        by_batch = form_type in ('internship', 'exit')
        responses = list(SurveyResponse.objects.filter(upload__department=department, upload__form_type=form_type)
                         .select_related('program'))

        def group_of(r):
            if by_batch:
                return r.batch or 'Not recorded'
            return str(r.graduation_year) if r.graduation_year else 'Not recorded'

        def order(key):
            if key == 'Not recorded':
                return (1, (0, 0))
            return (0, batch_sort_key(key) if by_batch else (int(key), 0))

        available = sorted({group_of(r) for r in responses}, key=order)
        wanted = [g.strip().upper() if by_batch else g.strip() for g in request.query_params.get('groups', '').split(',') if g.strip()]
        groups = [g for g in available if not wanted or g in wanted]
        programs = list(Program.objects.filter(department=department).order_by('code'))
        count = len(form['questions'])
        targets = department_targets(programs, form_type)

        population = {}
        if by_batch:
            for adm in AdmissionStudent.objects.filter(department=department).select_related('program'):
                key = batch_code(adm.reg_no)
                if key:
                    population.setdefault(key, {'total': 0})
                    population[key]['total'] += 1
                    population[key][adm.program.code] = population[key].get(adm.program.code, 0) + 1

        groups_out = []
        selected = []
        for key in groups:
            rs = [r for r in responses if group_of(r) == key]
            selected += rs
            by_program = {}
            for r in rs:
                by_program.setdefault(r.program.code if r.program else '', []).append(r)
            groups_out.append({
                'key':        key,
                'population': population.get(key, {}).get('total'),
                'composition': {code or 'Not specified': len(v) for code, v in by_program.items()},
                'stats':      rating_stats(rs, count),
                'programs':   {code: rating_stats(v, count) for code, v in by_program.items() if code},
                'comments':   [{'program': r.program.code if r.program else '', 'text': r.comment.strip()}
                               for r in rs if meaningful_comment(r.comment)],
            })

        return Response({
            'formType':     form_type,
            'formTitle':    form['title'],
            'usedFor':      form['usedFor'],
            'groupBy':      'batch' if by_batch else 'graduationYear',
            'department':   department.name,
            'kpi':          SURVEY_KPI,
            'kpis':         [{'no': i, 'text': text, 'target': targets.get(i, '')}
                             for i, text in enumerate(form_questions(department, form_type), start=1)],
            'programs':     [{'code': p.code, 'name': p.name} for p in programs],
            'available':    available,
            'groups':       groups_out,
            'consolidated': rating_stats(selected, count),
        })

