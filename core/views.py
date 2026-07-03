from django.contrib.auth import authenticate
from django.db import models
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from rest_framework             import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response    import Response
from rest_framework.views       import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models      import (
    User,
    Department, Program, GraduateAttribute, CLO, Course,
    InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
    InstructorProfile, QAProfile, Student,
    AdmissionProfile, DeptAdminProfile, CourseAssignment,
    SemesterPlan, AdmissionStudent,
)
from .serializers import (
    LoginSerializer, UserSerializer,
    DepartmentSerializer, ProgramSerializer,
    GraduateAttributeSerializer, CLOSerializer, CourseSerializer,
    InstructorCourseSerializer, AdmissionStudentSerializer,
    ProgramWriteSerializer, GraduateAttributeWriteSerializer,
    CourseWriteSerializer, CLOWriteSerializer,
    TeacherWriteSerializer, StudentWriteSerializer,
)
from .permissions import IsQA, IsQAOrReadOnly, IsInstructor, IsAdmission, IsDeptAdmin, IsDeptAdminOrQA


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def get_instructor_profile(user):
    try:
        return user.instructor_profile
    except Exception:
        return None


def get_admin_department(user):
    """
    Returns the Department a dept_admin user manages, or None.
    Shared across every dept_admin-facing view so 'own department only'
    enforcement is consistent and centralized in one place.
    """
    try:
        return user.dept_admin_profile.department
    except Exception:
        return None



def prefetch_instructor_course(qs):
    """Standard prefetch set for InstructorCourse querysets."""
    return qs.select_related('department', 'program').prefetch_related(
        'grade_scale',
        'categories__unit_items__questions',
        'students__marks__unit_item__category',
        'students__obe_marks__question',
        'obe_questions',
    )


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]
    # Previously unlimited — anyone could brute-force a password against any
    # known email with no rate limit, no lockout, no delay at all. 10/min
    # per IP via DEFAULT_THROTTLE_RATES in settings.py.
    throttle_scope = 'login'

    def post(self, request):
        s = LoginSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        email    = s.validated_data['email'].lower().strip()
        password = s.validated_data['password']

        # Look up user by email, then authenticate with their username
        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        except User.MultipleObjectsReturned:
            return Response({'error': 'Multiple accounts with this email — contact admin'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=user_obj.username, password=password)
        if user is None:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return Response({'error': 'Account is disabled'}, status=status.HTTP_401_UNAUTHORIZED)
        user_data = UserSerializer(user).data

        if user.role == 'qa':
            try:
                user_data['departmentId']   = user.qa_profile.department.dept_id
                user_data['departmentName'] = user.qa_profile.department.name
            except Exception:
                pass

        if user.role == 'instructor':
            try:
                user_data['departmentId']   = user.instructor_profile.department.dept_id
                user_data['departmentName'] = user.instructor_profile.department.name
            except Exception:
                pass

        if user.role == 'dept_admin':
            try:
                user_data['departmentId']   = user.dept_admin_profile.department.dept_id
                user_data['departmentName'] = user.dept_admin_profile.department.name
            except Exception:
                pass

        if user.role == 'admission':
            try:
                user_data['departmentId']   = user.admission_profile.department.dept_id
                user_data['departmentName'] = user.admission_profile.department.name
            except Exception:
                pass

        if user.role == 'student':
            try:
                user_data['regNo']        = user.student_profile.reg_no
                user_data['departmentId'] = user.student_profile.department.dept_id
            except Exception:
                pass

        user_data['mustChangePassword'] = user.must_change_password
        return Response({**get_tokens_for_user(user), 'user': user_data})


# ─── Departments ──────────────────────────────────────────────────────────────

class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            DepartmentSerializer(Department.objects.all().order_by('name'), many=True).data
        )


class DepartmentDetailView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsQA()]

    def _get(self, slug):
        try:
            return Department.objects.get(dept_id=slug)
        except Department.DoesNotExist:
            return None

    def get(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(DepartmentSerializer(obj).data)

    def patch(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        s = DepartmentSerializer(obj, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Programs ─────────────────────────────────────────────────────────────────

class ProgramListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Program.objects.select_related('department').prefetch_related(
            'objectives__ga_mappings__graduate_attribute'
        ).all().order_by('name')
        return Response(ProgramSerializer(qs, many=True).data)

    def post(self, request):
        ws = ProgramWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d       = ws.validated_data
        dept_id = d['departmentId']

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if Program.objects.filter(code__iexact=d['code']).exists():
            return Response(
                {'error': f'Program with code "{d["code"]}" already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        program = Program.objects.create(
            name=d['name'], code=d['code'], department=department,
            vision=d.get('vision', ''), mission=d.get('mission', '')
        )
        # Also process POs if sent on creation
        pos_data = request.data.get('pos', [])
        if pos_data:
            ProgramSerializer()._sync_pos(program, pos_data)

        qs = Program.objects.select_related('department').prefetch_related(
            'objectives__ga_mappings__graduate_attribute'
        ).get(pk=program.pk)
        return Response(ProgramSerializer(qs).data, status=status.HTTP_201_CREATED)


class ProgramDetailView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsQA()]

    def _get(self, slug):
        try:
            return Program.objects.select_related('department').prefetch_related(
                'objectives__ga_mappings__graduate_attribute'
            ).get(code__iexact=slug)
        except Program.DoesNotExist:
            return None

    def get(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProgramSerializer(obj).data)

    def patch(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        if 'pos' in data:
            data['pos_write'] = data.pop('pos')
        s = ProgramSerializer(obj, data=data, partial=True)
        if s.is_valid():
            s.save()
            return Response(ProgramSerializer(self._get(slug)).data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Graduate Attributes ──────────────────────────────────────────────────────

class GraduateAttributeListView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsQA()]

    def get(self, request):
        qs = GraduateAttribute.objects.select_related('department', 'program').order_by('ga_id')
        dept = request.query_params.get('departmentId')
        if dept:
            qs = qs.filter(department__dept_id=dept)
        return Response(GraduateAttributeSerializer(qs, many=True).data)

    def post(self, request):
        ws = GraduateAttributeWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d       = ws.validated_data
        ga_id   = d['id']
        dept_id = d['departmentId']
        prog_id = d.get('programId', '')

        if GraduateAttribute.objects.filter(ga_id=ga_id).exists():
            ga = GraduateAttribute.objects.get(ga_id=ga_id)
            return Response(GraduateAttributeSerializer(ga).data, status=status.HTTP_200_OK)
        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({"error": f'Department "{dept_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)
        program = None
        if prog_id:
            try:
                program = Program.objects.get(code__iexact=prog_id)
            except Program.DoesNotExist:
                pass
        ga = GraduateAttribute.objects.create(
            ga_id=ga_id, name=d['name'],
            description=d.get('description', ''),
            department=department, program=program
        )
        return Response(GraduateAttributeSerializer(ga).data, status=status.HTTP_201_CREATED)


# ─── Courses ──────────────────────────────────────────────────────────────────

class CourseListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Course.objects.select_related(
            'department', 'program'
        ).prefetch_related('mapped_gas').all().order_by('code')
        return Response(CourseSerializer(qs, many=True).data)

    def post(self, request):
        ws = CourseWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d          = ws.validated_data
        dept_id    = d['departmentId']
        program_id = d.get('programId', '')
        mapped_gas = d.get('mappedGAs', [])

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        program = None
        if program_id:
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                pass

        course = Course.objects.create(
            code=d['code'], title=d['title'],
            type=d.get('type', 'core'),
            department=department, program=program,
            credit_hours=d.get('creditHours', 3)
        )
        if mapped_gas:
            course.mapped_gas.set(GraduateAttribute.objects.filter(ga_id__in=mapped_gas))

        return Response(
            CourseSerializer(
                Course.objects.select_related('department', 'program')
                              .prefetch_related('mapped_gas').get(pk=course.pk)
            ).data,
            status=status.HTTP_201_CREATED
        )


class CourseDetailView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsQA()]

    def _get(self, slug):
        try:
            return Course.objects.select_related(
                'department', 'program'
            ).prefetch_related('mapped_gas').get(code__iexact=slug)
        except Course.DoesNotExist:
            return None

    def get(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CourseSerializer(obj).data)

    def patch(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        if 'mappedGAs' in data:
            data['mappedGAs_write'] = data.pop('mappedGAs')
        s = CourseSerializer(obj, data=data, partial=True)
        if s.is_valid():
            s.save()
            return Response(CourseSerializer(self._get(slug)).data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug):
        obj = self._get(slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Instructor Courses ───────────────────────────────────────────────────────

class InstructorCourseView(APIView):
    permission_classes = [IsInstructor]

    def get(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response(
                {'error': 'Instructor profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Auto-create InstructorCourse stubs for any CourseAssignment
        # not yet in the instructor's course list
        assignments = CourseAssignment.objects.filter(
            instructor=profile
        ).select_related('course', 'program')

        for assignment in assignments:
            course   = assignment.course
            program  = assignment.program
            term     = assignment.academic_year  # e.g. 'Fall-2024', may be blank for legacy

            # Unique ID for this assignment — includes term so the SAME
            # teacher+course in a DIFFERENT semester is a separate record.
            # This is what prevents a new term's offering from overwriting
            # a previous term's marks when a teacher repeats a course.
            prog_suffix  = program.code.lower() if program else 'all'
            term_suffix  = f"-{term.lower().replace(' ', '')}" if term else ''
            frontend_id  = f"course-assigned-{course.code}-{profile.employee_id}-{prog_suffix}{term_suffix}"

            # Skip auto-create if a CLOSED InstructorCourse already exists for
            # this exact assignment+term — closed courses are finalized and
            # must never be silently reopened or duplicated.
            existing_closed = InstructorCourse.objects.filter(
                instructor=profile, frontend_id=frontend_id, status='closed'
            ).exists()
            if existing_closed:
                continue

            InstructorCourse.objects.get_or_create(
                instructor=profile,
                frontend_id=frontend_id,
                defaults=dict(
                    code=course.code,
                    title=course.title,
                    course_type='Theory',
                    department=course.department,
                    program=program,
                    credit_hours=course.credit_hours,
                    academic_year=term,
                )
            )

        qs = prefetch_instructor_course(
            InstructorCourse.objects.filter(instructor=profile).order_by('created_at')
        )
        return Response(InstructorCourseSerializer(qs, many=True).data)

    def post(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response(
                {'error': 'Instructor profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )

        courses_data = request.data.get('courses', [])
        if not isinstance(courses_data, list):
            return Response(
                {'error': '"courses" must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )

        saved, errors = [], []

        for idx, c in enumerate(courses_data):
            frontend_id = c.get('id', '')
            dept_id     = c.get('departmentId', '')
            program_id  = c.get('programId')

            # Closed courses are read-only — reject any edit attempt
            existing = InstructorCourse.objects.filter(
                instructor=profile, frontend_id=frontend_id
            ).first()
            if existing and existing.status == 'closed':
                errors.append({
                    'index': idx,
                    'error': f'Course "{frontend_id}" is closed (finalized {existing.closed_at}) and cannot be edited.'
                })
                continue

            try:
                department = Department.objects.get(dept_id=dept_id)
            except Department.DoesNotExist:
                errors.append({'index': idx, 'error': f'Department "{dept_id}" not found'})
                continue

            try:
                with transaction.atomic():
                    program = None
                    if program_id:
                        try:
                            program = Program.objects.get(code__iexact=program_id)
                        except Program.DoesNotExist:
                            pass

                    # ── Upsert course header ──────────────────────────────────────────
                    course, _ = InstructorCourse.objects.update_or_create(
                        instructor=profile,
                        frontend_id=frontend_id,
                        defaults=dict(
                            code                    = c.get('code', ''),
                            title                   = c.get('title', ''),
                            course_type             = c.get('courseType', 'Theory'),
                            department              = department,
                            program                 = program,
                            credit_hours            = c.get('creditHours', 3),
                            clo_count               = c.get('cloCount', 4),
                            selected_grading_system = c.get('selectedGradingSystem', 'ready1'),
                        )
                    )

                    # ── Sync GradeScale ───────────────────────────────────────────────
                    custom_grading = c.get('customGradingSystem', [])
                    course.grade_scale.all().delete()
                    for order, entry in enumerate(custom_grading):
                        try:
                            GradeScale.objects.create(
                                course         = course,
                                grade          = entry.get('grade', ''),
                                min_percentage = float(entry.get('percentage', 0)),
                                points         = float(entry.get('points', 0)),
                                order          = order,
                            )
                        except (ValueError, TypeError):
                            pass

                    # ── Sync Categories + UnitItems ───────────────────────────────────
                    incoming_categories = c.get('categories', [])
                    incoming_units_data = c.get('unitsData', {})
                    incoming_cat_names  = [cat['name'] for cat in incoming_categories]

                    course.categories.exclude(name__in=incoming_cat_names).delete()

                    cat_obj_map  = {}   # cat_name -> MarksCategory instance
                    unit_obj_map = {}   # (cat_name, unit_no) -> UnitItem instance

                    for order, cat_data in enumerate(incoming_categories):
                        cat_name = cat_data['name']
                        cat_obj, _ = MarksCategory.objects.update_or_create(
                            course=course, name=cat_name,
                            defaults={
                                'percentage': cat_data.get('percentage', 0),
                                'units':      cat_data.get('units', 0),
                                'order':      order,
                            }
                        )
                        cat_obj_map[cat_name] = cat_obj

                        incoming_units    = incoming_units_data.get(cat_name, [])
                        incoming_unit_nos = [u['unitNo'] for u in incoming_units]
                        cat_obj.unit_items.exclude(unit_no__in=incoming_unit_nos).delete()

                        for unit_data in incoming_units:
                            unit_no  = unit_data['unitNo']
                            unit_obj, _ = UnitItem.objects.update_or_create(
                                category=cat_obj,
                                unit_no=unit_no,
                                defaults={
                                    'passing':     unit_data.get('passing', 5),
                                    'total_marks': unit_data.get('totalMarks', 10),
                                    'weightage':   unit_data.get('weightage', 0),
                                    'mapped_clos': unit_data.get('mappedCLOs', []),
                                }
                            )
                            unit_obj_map[(cat_name, unit_no)] = unit_obj

                    # ── Sync OBE Questions ────────────────────────────────────────────
                    incoming_questions = c.get('obeQuestions', [])
                    incoming_q_ids     = [q['id'] for q in incoming_questions]
                    course.obe_questions.exclude(frontend_id__in=incoming_q_ids).delete()

                    q_obj_map = {}   # frontend_id -> OBEQuestion
                    for order, q_data in enumerate(incoming_questions):
                        cat_name = q_data.get('categoryName', '')
                        unit_no  = q_data.get('unitNo', 0)
                        unit_obj = unit_obj_map.get((cat_name, unit_no))

                        q_obj, _ = OBEQuestion.objects.update_or_create(
                            course=course,
                            frontend_id=q_data['id'],
                            defaults={
                                'unit_item':     unit_obj,
                                'category_name': cat_name,
                                'unit_no':       unit_no,
                                'question_name': q_data.get('questionName', ''),
                                'max_marks':     q_data.get('maxMarks', 0),
                                'mapped_clos':   q_data.get('mappedCLOs', []),
                                'order':         order,
                            }
                        )
                        q_obj_map[q_data['id']] = q_obj

                    # ── Sync Students ─────────────────────────────────────────────────
                    incoming_students = c.get('students', [])
                    incoming_reg_nos  = [s['regNo'] for s in incoming_students]
                    course.students.exclude(reg_no__in=incoming_reg_nos).delete()

                    for s_data in incoming_students:
                        reg_no     = s_data['regNo']
                        student, _ = CourseStudent.objects.update_or_create(
                            course=course, reg_no=reg_no,
                            defaults={'name': s_data.get('name', '')}
                        )

                        # ── Sync StudentMarks (now FK to UnitItem) ────────────────────
                        incoming_marks = s_data.get('marks', {})

                        # Build set of incoming unit_item PKs
                        incoming_unit_pks = set()
                        mark_rows = []

                        for key, score in incoming_marks.items():
                            # key = '{categoryName}-{unitNo}'
                            last_dash = key.rfind('-')
                            try:
                                cat_name = key[:last_dash]
                                unit_no  = int(key[last_dash + 1:])
                                unit_obj = unit_obj_map.get((cat_name, unit_no))
                                if unit_obj:
                                    incoming_unit_pks.add(unit_obj.pk)
                                    mark_rows.append((unit_obj, score))
                            except (ValueError, IndexError):
                                pass

                        # Delete marks for units no longer in payload
                        student.marks.exclude(unit_item__in=incoming_unit_pks).delete()

                        for unit_obj, score in mark_rows:
                            StudentMark.objects.update_or_create(
                                student=student, unit_item=unit_obj,
                                defaults={'score': score}
                            )

                        # ── Sync OBE Marks ────────────────────────────────────────────
                    incoming_obe_marks = c.get('obeMarks', {})
                    for reg_no, q_marks in incoming_obe_marks.items():
                        try:
                            student = CourseStudent.objects.get(course=course, reg_no=reg_no)
                        except CourseStudent.DoesNotExist:
                            continue
                        for q_frontend_id, score in q_marks.items():
                            q_obj = q_obj_map.get(q_frontend_id)
                            if q_obj:
                                OBEStudentMark.objects.update_or_create(
                                    student=student, question=q_obj,
                                    defaults={'score': score}
                                )

                    saved.append(course)
            except (KeyError, ValueError, TypeError) as e:
                # Previously unhandled — a malformed entry anywhere in
                # this course (missing required key, wrong type) crashed
                # the ENTIRE batch save with a raw 500, silently discarding
                # every other course already processed in the same request
                # (including ones already committed to the DB before the
                # crash point) with no useful error returned to the frontend.
                # Reproduced before fixing: a second course missing a
                # category's "name" key 500'd the whole request even though
                # the first course in the same batch was well-formed.
                errors.append({
                    'index': idx,
                    'error': f'Could not save course "{frontend_id}" — malformed data ({e.__class__.__name__}: {e})',
                })
                continue

        if errors and not saved:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        result = InstructorCourseSerializer(
            prefetch_instructor_course(
                InstructorCourse.objects.filter(pk__in=[obj.pk for obj in saved])
            ),
            many=True
        ).data

        if errors:
            return Response({'courses': result, 'errors': errors}, status=status.HTTP_207_MULTI_STATUS)
        return Response(result, status=status.HTTP_200_OK)



# ─── Instructor Profile
class InstructorProfileView(APIView):
    """
    GET /api/instructor/profile/
    Returns the authenticated instructor's profile — department, designation.
    Used by InstructorDashboard to pre-fill department when creating a course.
    """
    permission_classes = [IsInstructor]

    def get(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response({'error': 'Instructor profile not found'}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            'employeeId':   profile.employee_id,
            'designation':  profile.designation,
            'department': {
                'id':   profile.department.dept_id,
                'name': profile.department.name,
            }
        })


# ─── Admission Students ───────────────────────────────────────────────────────



class AdmissionStudentListView(APIView):
    """
    GET  /api/students/   → list all students (admission + any authenticated)
    POST /api/students/   → create student (admission only)

    Frontend Student type: { regNo, name, departmentId, programId, batch }
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsAdmission()]

    def get(self, request):
        qs = AdmissionStudent.objects.select_related(
            'department', 'program'
        ).all().order_by('reg_no')
        return Response(AdmissionStudentSerializer(qs, many=True).data)

    def post(self, request):
        payload = request.data
        is_bulk = isinstance(payload, list)
        records = payload if is_bulk else [payload]
        created, errors = [], []

        for idx, data in enumerate(records):
            # Validate field types/lengths/choices before touching the DB
            row_ws = StudentWriteSerializer(data=data)
            if not row_ws.is_valid():
                errors.append({'index': idx, 'regNo': data.get('regNo', ''), 'error': row_ws.errors})
                continue
            vd         = row_ws.validated_data
            reg_no     = vd['regNo'].upper()
            name       = vd['name']
            dept_id    = vd['departmentId']
            program_id = vd['programId']
            batch      = vd.get('batch', 'Fall')
            semester   = vd.get('semester', '1st')

            # Email: use provided or auto-generate from reg_no
            raw_email = vd.get('email', '').strip().lower()
            email = raw_email if raw_email else f"{reg_no.lower().replace(' ', '')}@iqra.edu.pk"

            try:
                department = Department.objects.get(dept_id=dept_id)
            except Department.DoesNotExist:
                errors.append({'index': idx, 'regNo': reg_no, 'error': f'Department "{dept_id}" not found'})
                continue
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                errors.append({'index': idx, 'regNo': reg_no, 'error': f'Program "{program_id}" not found'})
                continue

            try:
                student, _ = AdmissionStudent.objects.update_or_create(
                    reg_no=reg_no,
                    defaults=dict(
                        name=name, email=email,
                        department=department, program=program,
                        batch=batch, semester=semester
                    )
                )

                # Auto-create or update the login User + Student profile
                from django.contrib.auth.hashers import make_password as _make_password
                from django.conf import settings as _settings
                from .models import Student as StudentProfile
                import re as _re
                user_obj   = User.objects.filter(email__iexact=email).first()
                if not user_obj:
                    # New student — create account with shared default password.
                    # must_change_password=True is the actual security boundary here
                    # (enforced server-side by PasswordChangeEnforcingJWTAuthentication) —
                    # previously this was False, which let bulk-imported students log in
                    # and use the app indefinitely on the known default password.
                    name_parts = name.split()
                    user_obj = User.objects.create(
                        username=email,
                        email=email,
                        first_name=name_parts[0] if name_parts else '',
                        last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                        role='student',
                        password=_make_password(_settings.DEFAULT_TEMP_PASSWORD),
                        must_change_password=True,
                        is_active=True,
                    )
                else:
                    # Guard against a real data-corruption bug: if this email
                    # already belongs to a login account linked to a DIFFERENT
                    # reg_no, silently reassigning that account's Student
                    # profile to this row's reg_no would sever the earlier
                    # student's login entirely while this AdmissionStudent
                    # roster row still reports "created" successfully — two
                    # roster entries end up sharing one login, and whichever
                    # row is processed last silently wins. Reject instead.
                    existing_profile = StudentProfile.objects.filter(user=user_obj).first()
                    if existing_profile and existing_profile.reg_no != reg_no:
                        errors.append({
                            'index': idx, 'regNo': reg_no,
                            'error': f'Email "{email}" is already linked to student '
                                     f'{existing_profile.reg_no}\'s login account — each '
                                     f'student needs a unique email. The admission record '
                                     f'for {reg_no} was saved, but no login account could '
                                     f'be created or linked for them yet. Fix the email and '
                                     f're-submit this row to provision their login.',
                        })
                        continue
                    # Update name if changed
                    name_parts = name.split()
                    user_obj.first_name = name_parts[0] if name_parts else ''
                    user_obj.last_name  = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                    user_obj.save()

                # Link Student profile (reg_no is the bridge)
                StudentProfile.objects.update_or_create(
                    user=user_obj,
                    defaults=dict(reg_no=reg_no, department=department, program=program)
                )
            except IntegrityError as e:
                # Most likely cause: reg_no or email collides with a DIFFERENT
                # existing record than the one this row is trying to update
                # (e.g. the same email already belongs to another reg_no).
                # Previously this was unhandled — one bad row in a bulk Excel
                # import would 500 the entire batch and silently discard every
                # row already processed earlier in the same request.
                errors.append({
                    'index': idx, 'regNo': reg_no,
                    'error': f'Could not save this row — likely a duplicate reg_no or email already used by a different student ({e.__class__.__name__})',
                })
                continue
            except Exception as e:
                # Belt-and-suspenders: any other unexpected failure on this row
                # skips just this row instead of taking down the whole batch.
                errors.append({'index': idx, 'regNo': reg_no, 'error': f'Unexpected error saving this row: {e}'})
                continue

            created.append(student)

        serialized = AdmissionStudentSerializer(created, many=True).data
        if is_bulk:
            body = {'created': serialized}
            if errors: body['errors'] = errors
            code = status.HTTP_207_MULTI_STATUS if errors else status.HTTP_201_CREATED
            return Response(body, status=code)
        if errors:
            return Response({'error': errors[0]['error']}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialized[0], status=status.HTTP_201_CREATED)


class AdmissionStudentDetailView(APIView):
    """
    PATCH  /api/students/<reg_no>/   → update student
    DELETE /api/students/<reg_no>/   → delete student
    """
    def get_permissions(self):
        return [IsAdmission()]

    def _get(self, reg_no):
        try:
            return AdmissionStudent.objects.select_related(
                'department', 'program'
            ).get(reg_no=reg_no.upper())
        except AdmissionStudent.DoesNotExist:
            return None

    def patch(self, request, reg_no):
        student = self._get(reg_no)
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'name' in data:
            student.name = data['name'].strip()
        if 'batch' in data:
            student.batch = data['batch']
        if 'semester' in data:
            student.semester = data['semester']

        if 'departmentId' in data:
            try:
                # slug field was removed — use dept_id (the canonical identifier)
                student.department = Department.objects.get(dept_id=data['departmentId'])
            except Department.DoesNotExist:
                return Response(
                    {'error': f'Department "{data["departmentId"]}" not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if 'programId' in data:
            try:
                # slug field was removed — use code__iexact (the canonical identifier)
                student.program = Program.objects.get(code__iexact=data['programId'])
            except Program.DoesNotExist:
                return Response(
                    {'error': f'Program "{data["programId"]}" not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        student.save()
        return Response(AdmissionStudentSerializer(student).data)

    def delete(self, request, reg_no):
        student = self._get(reg_no)
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        student.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# ─── Course Assignments (Dept Admin) ─────────────────────────────────────────



class CourseAssignmentView(APIView):
    """
    GET    /api/admin/course-assignments/
    POST   /api/admin/course-assignments/   { teacherId, courseCode, programId }
    DELETE /api/admin/course-assignments/   { teacherId, courseCode, programId }

    Dept admin assigns an instructor to a course+program combination.

    Department scoping: a dept_admin may only view, create, or remove
    assignments for COURSES in their own managed department. They may
    however assign ANY instructor university-wide to those courses —
    cross-department teaching is intentional and documented (e.g. a
    Computing admin may assign a Humanities instructor to teach a
    Computing course). Only the course side is locked to "own department".
    """
    permission_classes = [IsDeptAdmin]

    def get(self, request):
        admin_dept = get_admin_department(request.user)
        if not admin_dept:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)

        qs = CourseAssignment.objects.select_related(
            'instructor__user', 'course', 'program'
        ).filter(course__department=admin_dept)
        data = [{
            'teacherId':   a.instructor.employee_id,
            'teacherName': a.instructor.user.get_full_name() or a.instructor.user.username,
            'courseCode':  a.course.code,
            'courseTitle': a.course.title,
            'programId':   a.program.code.lower() if a.program else None,
            'programName': a.program.name         if a.program else None,
        } for a in qs]
        return Response(data)

    def post(self, request):
        admin_dept = get_admin_department(request.user)
        if not admin_dept:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)

        data          = request.data
        teacher_id    = data.get('teacherId', '').strip()
        course_code   = data.get('courseCode', '').strip().upper()
        program_id    = data.get('programId', '').strip()
        academic_year = data.get('academicYear', '').strip()  # e.g. 'Fall-2024'

        if not teacher_id or not course_code:
            return Response({'error': 'teacherId and courseCode are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instructor = InstructorProfile.objects.get(employee_id=teacher_id)
        except InstructorProfile.DoesNotExist:
            return Response({'error': f'Instructor "{teacher_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            course = Course.objects.get(code__iexact=course_code)
        except Course.DoesNotExist:
            return Response({'error': f'Course "{course_code}" not found'}, status=status.HTTP_400_BAD_REQUEST)

        # The course must belong to the requesting admin's own department.
        # The instructor can be from anywhere — only the course is locked.
        if course.department_id != admin_dept.id:
            return Response(
                {'error': f'Course "{course_code}" does not belong to your department ({admin_dept.name}).'},
                status=status.HTTP_403_FORBIDDEN
            )

        program = None
        if program_id:
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)

        dept_admin = request.user.dept_admin_profile

        assignment, created = CourseAssignment.objects.get_or_create(
            instructor=instructor, course=course, program=program, academic_year=academic_year,
            defaults={'assigned_by': dept_admin}
        )
        return Response({
            'teacherId':  assignment.instructor.employee_id,
            'courseCode': assignment.course.code,
            'programId':  assignment.program.code.lower() if assignment.program else None,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        admin_dept = get_admin_department(request.user)
        if not admin_dept:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)

        data          = request.data
        teacher_id    = data.get('teacherId', '').strip()
        course_code   = data.get('courseCode', '').strip().upper()
        program_id    = data.get('programId', '').strip()
        academic_year = data.get('academicYear', '').strip()

        qs = CourseAssignment.objects.filter(
            instructor__employee_id=teacher_id,
            course__code__iexact=course_code,
            course__department=admin_dept,   # scoped — can't delete other depts' assignments
        )
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)
        deleted, _ = qs.delete()
        if not deleted:
            return Response({'error': 'Assignment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Clean up the auto-created InstructorCourse stub for this assignment.
        # Only delete if it has NO student data — preserve any gradebook the
        # instructor has already started filling in, even after unassignment.
        #
        # BUG FIX: this frontend_id was previously built WITHOUT the term
        # suffix, but InstructorCourseView.get() (where the stub is actually
        # created) always includes it when academic_year is set — see the
        # term_suffix logic there. That mismatch meant the lookup below never
        # matched a real stub for any assignment with an academic_year set
        # (the realistic case), so this cleanup silently no-op'd every time,
        # leaving an orphaned empty InstructorCourse row behind on every
        # delete. Reproduced and confirmed via a live create→auto-create→
        # delete cycle before fixing. Now builds the id the same way both
        # places do.
        prog_suffix = program_id.lower() if program_id else 'all'
        term_suffix = f"-{academic_year.lower().replace(' ', '')}" if academic_year else ''
        frontend_id = f"course-assigned-{course_code}-{teacher_id}-{prog_suffix}{term_suffix}"
        try:
            ic = InstructorCourse.objects.get(frontend_id=frontend_id)
            if not ic.students.exists() and not ic.obe_questions.exists():
                ic.delete()
        except InstructorCourse.DoesNotExist:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)



# ─── Teachers List (all instructors across all depts) ─────────────────────────

class TeacherListView(APIView):
    """
    GET /api/teachers/
    Returns all instructors across ALL departments.
    Used by dept_admin when assigning teachers to courses
    (can assign teachers from any department to their courses).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profiles = InstructorProfile.objects.select_related(
            'user', 'department'
        ).all().order_by('department__name', 'user__last_name')
        data = [
            {
                'employeeId':   p.employee_id,
                'name':         p.user.get_full_name() or p.user.username,
                'email':        p.user.email,
                'designation':  p.designation,
                'departmentId': p.department.dept_id,
                'departmentName': p.department.name,
            }
            for p in profiles
        ]
        return Response(data)


# ─── Dept Admin Profile ───────────────────────────────────────────────────────

class DeptAdminProfileView(APIView):
    """
    GET /api/admin/profile/
    Returns the dept_admin's managed department.
    Frontend uses this on load to know which dept to scope the UI to.
    """
    permission_classes = [IsDeptAdmin]

    def get(self, request):
        try:
            profile = request.user.dept_admin_profile
        except Exception:
            return Response(
                {'error': 'Dept admin profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )
        return Response({
            'email':          request.user.email,
            'user_type':      'dept_admin',
            'departmentId':   profile.department.dept_id,
            'departmentName': profile.department.name,
            'employeeId':     profile.employee_id,
        })


# ─── Semester Plans ───────────────────────────────────────────────────────────

class SemesterPlanView(APIView):
    """
    GET  /api/admin/semester-plans/?programId=bscs
         Returns all semester plans for a program.

    POST /api/admin/semester-plans/
         Body: { programId: 'bscs', semester: '1st', courseCodes: ['CMC111', ...] }
         Upserts — safe to call multiple times.

    DELETE /api/admin/semester-plans/
         Body: { programId: 'bscs', semester: '1st' }
         Clears a semester plan.
    """
    permission_classes = [IsDeptAdmin]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        dept = get_admin_department(request.user)
        if not dept:
            return Response({'error': 'Profile not found'}, status=status.HTTP_403_FORBIDDEN)

        qs = SemesterPlan.objects.select_related('program')
        # SECURITY FIX: previously, when programId was provided, this skipped
        # department scoping entirely — any dept_admin could pass ANY other
        # department's program code and read that department's semester plan.
        # Reproduced before fixing: a Business dept admin successfully read
        # Computing's semester plan by requesting ?programId=BSCS directly.
        # Every dept_admin request must be scoped to their own department
        # regardless of which query params are supplied.
        qs = qs.filter(program__department=dept)
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)

        data = [
            {
                'programId':   plan.program.code.lower(),
                'semester':    plan.semester,
                'courseCodes': plan.course_codes,
            }
            for plan in qs
        ]
        return Response(data)

    def post(self, request):
        dept = get_admin_department(request.user)
        if not dept:
            return Response({'error': 'Profile not found'}, status=status.HTTP_403_FORBIDDEN)

        program_id   = request.data.get('programId', '').strip()
        semester     = request.data.get('semester', '').strip()
        course_codes = request.data.get('courseCodes', [])

        if not program_id or not semester:
            return Response(
                {'error': 'programId and semester are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            program = Program.objects.get(code__iexact=program_id, department=dept)
        except Program.DoesNotExist:
            return Response(
                {'error': f'Program "{program_id}" not found in your department'},
                status=status.HTTP_404_NOT_FOUND
            )

        admin_profile = request.user.dept_admin_profile
        plan, _ = SemesterPlan.objects.update_or_create(
            program=program, semester=semester,
            defaults={'course_codes': course_codes, 'updated_by': admin_profile}
        )
        return Response({
            'programId':   plan.program.code.lower(),
            'semester':    plan.semester,
            'courseCodes': plan.course_codes,
        })

    def delete(self, request):
        dept = get_admin_department(request.user)
        if not dept:
            return Response({'error': 'Profile not found'}, status=status.HTTP_403_FORBIDDEN)

        program_id = request.data.get('programId', '').strip()
        semester   = request.data.get('semester', '').strip()
        try:
            plan = SemesterPlan.objects.get(
                program__code__iexact=program_id,
                program__department=dept,
                semester=semester
            )
            plan.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except SemesterPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)


# ─── Student Course View (student sees their own courses + marks) ─────────────

class StudentCoursesView(APIView):
    """
    GET /api/student/courses/
    Returns all courses the authenticated student is enrolled in,
    with their own marks only (not the full class roster).

    Response shape per course:
    {
        "id":          "course-CMC111-INS-CS-001-bscs",
        "code":        "CMC111",
        "title":       "Programming Fundamentals (BSCS)",
        "creditHours": 3,
        "categories":  [...],
        "studentMarks": { "Assignments-1": 8.5, "Mid Term-1": 24.5 }
    }

    Requires: User.role == 'student'
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'student':
            return Response(
                {'error': 'Only students can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get reg_no from Student profile
        try:
            reg_no = request.user.student_profile.reg_no
        except Exception:
            # No Student profile — fall back to username for demo/seed users
            reg_no = request.user.email.split('@')[0]  # fallback only

        # Find all CourseStudent rows matching this reg_no
        enrollments = CourseStudent.objects.filter(
            reg_no=reg_no
        ).select_related(
            'course__department',
            'course__program',
        ).prefetch_related(
            'marks__unit_item__category',
            'course__categories',
        )

        result = []
        for enrollment in enrollments:
            ic = enrollment.course
            # Build student-specific marks dict
            student_marks = {
                f"{m.unit_item.category.name}-{m.unit_item.unit_no}": m.score
                for m in enrollment.marks.select_related('unit_item__category').all()
            }
            # Build categories list
            categories = [
                {'name': c.name, 'percentage': c.percentage, 'units': c.units}
                for c in ic.categories.order_by('order').all()
            ]
            result.append({
                'id':           f"course-{ic.code}-{ic.instructor.employee_id}-{ic.program.code.lower() if ic.program else 'all'}",
                'code':         ic.code,
                'title':        f"{ic.title} ({ic.program.code if ic.program else ''})",
                'creditHours':  ic.credit_hours,
                'categories':   categories,
                'studentMarks': student_marks,
            })

        return Response(result)



# ═══════════════════════════════════════════════════════════════════════════════
# OBE REPORTS
# ═══════════════════════════════════════════════════════════════════════════════
#
# All report endpoints are read-only (GET).
# Computations are done dynamically — no caching — so grade updates
# immediately reflect in reports.
#
# Attainment threshold: 50% (v1 hardcoded, configurable later)
# Missing GA mappings: gracefully omitted (empty lists, no 500 errors)
# ───────────────────────────────────────────────────────────────────────────────

ATTAINMENT_THRESHOLD = 50.0   # % — student "attains" a CLO/GA if score >= this

# ── Built-in grading scales ───────────────────────────────────────────────────
READY1_SCALE = [
    ('A',   90.0, 4.00),
    ('A-',  85.0, 3.67),
    ('B+',  81.0, 3.33),
    ('B',   77.0, 3.00),
    ('B-',  73.0, 2.67),
    ('C+',  69.0, 2.33),
    ('C',   65.0, 2.00),
    ('C-',  61.0, 1.67),
    ('D+',  57.0, 1.33),
    ('D',   53.0, 1.00),
    ('F',    0.0, 0.00),
]
READY2_SCALE = [
    ('A',   88.0, 4.00),
    ('B+',  81.0, 3.50),
    ('B',   74.0, 3.00),
    ('C+',  67.0, 2.50),
    ('C',   60.0, 2.00),
    ('D',   50.0, 1.00),
    ('F',    0.0, 0.00),
]


def _apply_scale(percentage: float, scale: list) -> tuple:
    """Return (grade_letter, grade_points) for a percentage score."""
    for grade, threshold, points in scale:
        if percentage >= threshold:
            return grade, points
    return 'F', 0.0


def _get_grade(percentage: float, instructor_course) -> tuple:
    """Return (grade_letter, grade_points) using the course grading system."""
    system = instructor_course.selected_grading_system
    if system == 'ready2':
        return _apply_scale(percentage, READY2_SCALE)
    if system == 'custom':
        custom = list(
            instructor_course.grade_scale.order_by('-min_percentage')
            .values_list('grade', 'min_percentage', 'points')
        )
        if custom:
            return _apply_scale(percentage, custom)
    return _apply_scale(percentage, READY1_SCALE)


def _student_total_percentage(course_student) -> float:
    """
    Weighted total percentage using:
      (score / total_marks) * (unit_weightage / 100) * category_percentage
    Sums to 0-100 scale.
    """
    marks_qs = course_student.marks.select_related('unit_item__category')
    total = 0.0
    for mark in marks_qs:
        ui  = mark.unit_item
        cat = ui.category
        if ui.total_marks > 0 and cat.percentage > 0:
            total += (mark.score / ui.total_marks) * (ui.weightage / 100) * cat.percentage
    return round(total, 2)


def _clo_attainments_for_student(course_student, questions_qs):
    """Returns dict: { 'CLO-1': percentage_float, ... }"""
    obe_marks = {
        m.question_id: m.score
        for m in course_student.obe_marks.select_related('question').all()
    }
    clo_scores = {}
    clo_max    = {}
    for q in questions_qs:
        score = obe_marks.get(q.pk, 0.0)
        for clo in q.mapped_clos:
            clo_scores.setdefault(clo, []).append(score)
            clo_max.setdefault(clo,   []).append(q.max_marks)
    result = {}
    for clo in clo_scores:
        total_score = sum(clo_scores[clo])
        total_max   = sum(clo_max[clo])
        result[clo] = round((total_score / total_max * 100) if total_max > 0 else 0.0, 2)
    return result


# ── 1. Program GA Attainment ──────────────────────────────────────────────────

class ProgramGAAttainmentView(APIView):
    """
    GET /api/reports/program-ga-attainment/?programId=bscs
    Response shape (matches frontend contract):
    {
      "programId": "bscs",
      "programName": "Bachelor of Science in Computer Science",
      "attainmentThreshold": 50.0,
      "attributes": [
        {
          "id": "GA-1",
          "title": "Academic Grounding",
          "description": "...",
          "averageAttainment": 74.5,
          "contributingCoursesCount": 3,
          "attainmentStatus": "Passed",
          "contributingCourses": [
            { "code": "CMC111", "title": "...", "averageMarks": 78.2 }
          ]
        }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.select_related('department').get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        gas = GraduateAttribute.objects.filter(
            models.Q(department=program.department, program__isnull=True) |
            models.Q(program=program)
        ).order_by('ga_id')

        instructor_courses = InstructorCourse.objects.filter(
            program=program
        ).prefetch_related('students__marks__unit_item__category')

        course_avg_map   = {}
        course_title_map = {}
        for ic in instructor_courses:
            students = list(ic.students.prefetch_related('marks__unit_item__category').all())
            if not students:
                continue
            percentages = [_student_total_percentage(s) for s in students]
            course_avg_map[ic.code]   = round(sum(percentages) / len(percentages), 2)
            course_title_map[ic.code] = ic.title

        course_codes    = list(course_avg_map.keys())
        catalog_courses = Course.objects.filter(code__in=course_codes).prefetch_related('mapped_gas')

        ga_courses = {}
        for course in catalog_courses:
            avg = course_avg_map.get(course.code, 0.0)
            for ga in course.mapped_gas.all():
                ga_courses.setdefault(ga.ga_id, []).append({
                    'code':         course.code,
                    'title':        course_title_map.get(course.code, course.title),
                    'averageMarks': avg,
                })

        attributes = []
        for ga in gas:
            contributing    = ga_courses.get(ga.ga_id, [])
            avg_attainment  = round(sum(c['averageMarks'] for c in contributing) / len(contributing), 2) if contributing else 0.0
            attributes.append({
                'id':                      ga.ga_id,
                'title':                   ga.name,
                'description':             ga.description,
                'averageAttainment':       avg_attainment,
                'contributingCoursesCount': len(contributing),
                'attainmentStatus':        'Passed' if avg_attainment >= ATTAINMENT_THRESHOLD else 'Failed',
                'contributingCourses':     contributing,
            })

        return Response({
            'programId':          program.code.lower(),
            'programName':        program.name,
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'attributes':         attributes,
        })


# ── 2. Student GA Attainment ──────────────────────────────────────────────────

class StudentGAAttainmentView(APIView):
    """
    GET /api/reports/student-ga-attainment/?regNo=FA22-BSCS-0012
    Response shape (matches frontend contract):
    {
      "regNo": "FA22-BSCS-0012",
      "studentName": "Ahmed Ali",
      "programId": "bscs",
      "attainments": [
        {
          "gaId": "GA-1",
          "gaTitle": "Academic Grounding",
          "score": 75.8,
          "passed": true,
          "contributingCourses": [
            { "code": "CMC111", "title": "...", "score": 78.2 }
          ]
        }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reg_no = request.query_params.get('regNo', '').strip()
        if not reg_no:
            return Response({'error': 'regNo is required'}, status=status.HTTP_400_BAD_REQUEST)

        admission_student = AdmissionStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('program').first()

        student_name    = admission_student.name    if admission_student else reg_no
        student_program = admission_student.program if admission_student else None

        course_students = CourseStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('course__program').prefetch_related(
            'obe_marks__question', 'marks__unit_item__category',
        )

        if not course_students.exists():
            return Response({
                'regNo':       reg_no,
                'studentName': student_name,
                'programId':   student_program.code.lower() if student_program else None,
                'attainments': [],
            })

        course_codes = [cs.course.code for cs in course_students]
        catalog_map  = {
            c.code: c
            for c in Course.objects.filter(code__in=course_codes).prefetch_related('mapped_gas')
        }

        ga_scores         = {}   # ga_id → [scores]
        ga_info           = {}   # ga_id → { gaId, gaTitle }
        ga_course_details = {}   # ga_id → [{ code, title, score }]

        for cs in course_students:
            catalog_course = catalog_map.get(cs.course.code)
            if not catalog_course:
                continue
            student_pct = _student_total_percentage(cs)
            for ga in catalog_course.mapped_gas.all():
                ga_scores.setdefault(ga.ga_id, []).append(student_pct)
                ga_info[ga.ga_id] = {'gaId': ga.ga_id, 'gaTitle': ga.name}
                ga_course_details.setdefault(ga.ga_id, []).append({
                    'code':  cs.course.code,
                    'title': cs.course.title,
                    'score': student_pct,
                })

        attainments = []
        for ga_id, scores in sorted(ga_scores.items()):
            avg = round(sum(scores) / len(scores), 2) if scores else 0.0
            attainments.append({
                'gaId':               ga_id,
                'gaTitle':            ga_info[ga_id]['gaTitle'],
                'score':              avg,
                'passed':             avg >= ATTAINMENT_THRESHOLD,
                'contributingCourses': ga_course_details.get(ga_id, []),
            })

        return Response({
            'regNo':       reg_no,
            'studentName': student_name,
            'programId':   student_program.code.lower() if student_program else None,
            'attainments': attainments,
        })


# ── 3. Course GA & CLO Attainment ────────────────────────────────────────────

class CourseAttainmentView(APIView):
    """
    GET /api/reports/course-attainment/?courseCode=CMC111&programId=bscs
    Response shape (matches frontend contract):
    {
      "courseCode": "CMC111",
      "courseTitle": "Programming Fundamentals",
      "programId": "bscs",
      "attainmentThreshold": 50.0,
      "classSize": 42,
      "clos": [
        {
          "code": "CLO-1",
          "description": "CLO-1",
          "mappedGA": "GA-1",
          "averageMarks": 74.5,
          "maxMarks": 100,
          "attainmentPercentage": 74.5,
          "passedCount": 28,
          "totalCount": 30,
          "attainmentStatus": "Passed"
        }
      ],
      "mappedGAs": [{ "gaId": "GA-1", "name": "Academic Grounding" }]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        course_code = request.query_params.get('courseCode', '').strip().upper()
        program_id  = request.query_params.get('programId', '').strip()

        if not course_code:
            return Response({'error': 'courseCode is required'}, status=status.HTTP_400_BAD_REQUEST)

        qs = InstructorCourse.objects.filter(code__iexact=course_code)
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)

        if not qs.exists():
            return Response(
                {'error': f'No course offering found for "{course_code}"'},
                status=status.HTTP_404_NOT_FOUND
            )

        all_students  = []
        all_questions = []
        course_title  = ''
        prog_id_out   = program_id.lower() if program_id else None

        for ic in qs.prefetch_related(
            'students__obe_marks__question',
            'students__marks__unit_item__category',
            'obe_questions',
        ):
            course_title = ic.title
            if not prog_id_out and ic.program:
                prog_id_out = ic.program.code.lower()
            all_students.extend(list(ic.students.all()))
            all_questions.extend(list(ic.obe_questions.all()))

        class_size = len(all_students)

        # CLO max marks (total across all questions mapped to that CLO)
        clo_max_marks = {}
        for q in all_questions:
            for clo in q.mapped_clos:
                clo_max_marks.setdefault(clo, 0.0)
                clo_max_marks[clo] += q.max_marks

        # Per-student CLO scores
        clo_scores_all = {}
        for student in all_students:
            clo_attain = _clo_attainments_for_student(student, all_questions)
            for clo, pct in clo_attain.items():
                clo_scores_all.setdefault(clo, []).append(pct)

        # GA catalog for mapping
        catalog_course = Course.objects.filter(
            code__iexact=course_code
        ).prefetch_related('mapped_gas').first()

        # Build CLO → GA mapping
        # Priority: real CLO table records (exact join) → fallback to first course GA
        clo_to_ga = {}
        db_clos = CLO.objects.filter(
            course__in=qs
        ).select_related('mapped_ga')
        for db_clo in db_clos:
            if db_clo.mapped_ga:
                clo_to_ga[db_clo.code] = db_clo.mapped_ga.ga_id

        # Fallback for CLOs not yet in CLO table
        if catalog_course:
            ga_list = list(catalog_course.mapped_gas.all())
            for q in all_questions:
                for clo_code in q.mapped_clos:
                    if clo_code not in clo_to_ga and ga_list:
                        clo_to_ga[clo_code] = ga_list[0].ga_id

        # Build CLO description map from DB (reuses db_clos above instead of
        # re-running the same CLO.objects.filter(course__in=qs) query twice)
        clo_description_map = {
            c.code: c.description
            for c in db_clos
            if c.description
        }

        clos_result = []
        for clo in sorted(clo_scores_all.keys()):
            scores         = clo_scores_all[clo]
            class_avg      = round(sum(scores) / len(scores), 2) if scores else 0.0
            passed_count   = sum(1 for s in scores if s >= ATTAINMENT_THRESHOLD)
            attain_pct     = round((passed_count / len(scores) * 100), 2) if scores else 0.0
            mapped_q_count = sum(1 for q in all_questions if clo in q.mapped_clos)
            clos_result.append({
                'code':                clo,
                'description':         clo_description_map.get(clo, clo),  # real desc or code as fallback
                'mappedGA':            clo_to_ga.get(clo, ''),
                'averageMarks':        class_avg,
                'maxMarks':            100,
                'attainmentPercentage': attain_pct,
                'passedCount':         passed_count,
                'totalCount':          len(scores),
                'attainmentStatus':    'Passed' if attain_pct >= ATTAINMENT_THRESHOLD else 'Failed',
                'mappedQuestionsCount': mapped_q_count,
            })

        mapped_gas = []
        if catalog_course:
            mapped_gas = [
                {'gaId': ga.ga_id, 'name': ga.name}
                for ga in catalog_course.mapped_gas.all()
            ]

        return Response({
            'courseCode':          course_code,
            'courseTitle':         course_title,
            'programId':           prog_id_out,
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'classSize':           class_size,
            'clos':                clos_result,
            'mappedGAs':           mapped_gas,
        })


# ── 4. Student Summary Report Card ───────────────────────────────────────────

class StudentSummaryView(APIView):
    """
    GET /api/reports/student-summary/?regNo=FA22-BSCS-0012
    Response shape (matches frontend contract):
    {
      "regNo": "FA22-BSCS-0012",
      "name": "Ahmed Ali",
      "programId": "bscs",
      "cgpa": 3.64,
      "totalCreditsCompleted": 15,
      "enrolledCourses": [
        {
          "courseCode": "CMC111",
          "courseTitle": "Programming Fundamentals",
          "creditHours": 3,
          "grade": "A-",
          "gpa": 3.67,
          "marksSummary": { "obtained": 74.5, "total": 100 },
          "cloAttainments": [
            { "code": "CLO-1", "attained": true, "percentage": 78.5 }
          ]
        }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reg_no = request.query_params.get('regNo', '').strip()
        if not reg_no:
            return Response({'error': 'regNo is required'}, status=status.HTTP_400_BAD_REQUEST)

        admission_student = AdmissionStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('program').first()

        student_name    = admission_student.name    if admission_student else reg_no
        student_program = admission_student.program if admission_student else None

        course_students = CourseStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('course').prefetch_related(
            'marks__unit_item__category',
            'obe_marks__question',
            'course__grade_scale',
        )

        enrolled_courses      = []
        total_credit_points   = 0.0
        total_credits         = 0

        for cs in course_students:
            ic          = cs.course
            student_pct = _student_total_percentage(cs)
            grade_letter, grade_points = _get_grade(student_pct, ic)

            questions        = list(ic.obe_questions.all())
            clo_pcts         = _clo_attainments_for_student(cs, questions)
            clo_attainments  = [
                {
                    'code':       clo,
                    'attained':   pct >= ATTAINMENT_THRESHOLD,
                    'percentage': pct,
                }
                for clo, pct in sorted(clo_pcts.items())
            ]

            credit_hours         = ic.credit_hours
            total_credit_points += grade_points * credit_hours
            total_credits       += credit_hours

            enrolled_courses.append({
                'courseCode':   ic.code,
                'courseTitle':  ic.title,
                'creditHours':  credit_hours,
                'grade':        grade_letter,
                'gpa':          grade_points,
                'marksSummary': {'obtained': student_pct, 'total': 100.0},
                'cloAttainments': clo_attainments,
            })

        cgpa = round(total_credit_points / total_credits, 2) if total_credits > 0 else 0.0

        return Response({
            'regNo':                reg_no,
            'name':                 student_name,
            'programId':            student_program.code.lower() if student_program else None,
            'cgpa':                 cgpa,
            'totalCreditsCompleted': total_credits,
            'enrolledCourses':      enrolled_courses,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# CLO MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class CLOListView(APIView):
    """
    GET  /api/instructor/courses/<frontend_id>/clos/
         Returns all CLOs for a specific instructor course.

    POST /api/instructor/courses/<frontend_id>/clos/
         Create a new CLO.
         Body: { code, description, mappedGA, order }
         mappedGA: GA id string e.g. "GA-1" or null
    """
    permission_classes = [IsInstructor]

    def _get_course(self, frontend_id):
        try:
            return InstructorCourse.objects.get(frontend_id=frontend_id)
        except InstructorCourse.DoesNotExist:
            return None

    def get(self, request, frontend_id):
        course = self._get_course(frontend_id)
        if not course:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        clos = course.clos.select_related('mapped_ga').all()
        return Response(CLOSerializer(clos, many=True).data)

    def post(self, request, frontend_id):
        course = self._get_course(frontend_id)
        if not course:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        ws = CLOWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d     = ws.validated_data
        code  = d['code']
        ga_id = d.get('mappedGA') or ''

        if CLO.objects.filter(course=course, code=code).exists():
            return Response(
                {'error': f'CLO "{code}" already exists for this course'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ga = None
        if ga_id:
            try:
                ga = GraduateAttribute.objects.get(ga_id=ga_id)
            except GraduateAttribute.DoesNotExist:
                return Response(
                    {'error': f'Graduate Attribute "{ga_id}" not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        clo = CLO.objects.create(
            course=course, code=code,
            description=d.get('description', ''), mapped_ga=ga, order=d.get('order', 0)
        )
        return Response(CLOSerializer(clo).data, status=status.HTTP_201_CREATED)


class CLODetailView(APIView):
    """
    GET    /api/instructor/courses/<frontend_id>/clos/<clo_id>/
    PATCH  /api/instructor/courses/<frontend_id>/clos/<clo_id>/
           Body: { description?, mappedGA?, order? }
    DELETE /api/instructor/courses/<frontend_id>/clos/<clo_id>/
    """
    permission_classes = [IsInstructor]

    def _get(self, frontend_id, clo_id):
        try:
            return CLO.objects.select_related('mapped_ga', 'course').get(
                pk=clo_id, course__frontend_id=frontend_id
            )
        except CLO.DoesNotExist:
            return None

    def get(self, request, frontend_id, clo_id):
        clo = self._get(frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CLOSerializer(clo).data)

    def patch(self, request, frontend_id, clo_id):
        clo = self._get(frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'description' in data:
            clo.description = data['description'].strip()
        if 'order' in data:
            clo.order = data['order']
        if 'mappedGA' in data:
            ga_id = data['mappedGA']
            if ga_id:
                try:
                    clo.mapped_ga = GraduateAttribute.objects.get(ga_id=ga_id)
                except GraduateAttribute.DoesNotExist:
                    return Response(
                        {'error': f'Graduate Attribute "{ga_id}" not found'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                clo.mapped_ga = None
        clo.save()
        return Response(CLOSerializer(clo).data)

    def delete(self, request, frontend_id, clo_id):
        clo = self._get(frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)
        clo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Additional OBE Reports ───────────────────────────────────────────────────

ATTAINMENT_THRESHOLD = 50.0


class COAttainmentSummaryView(APIView):
    """
    GET /api/reports/co-attainment-summary/?programId=bscs&semester=6th

    Course Outcome Attainment Summary — the primary HEC deliverable.
    Shows for each course: CLO × attainment%, mapped GA, pass/fail status.
    QA uses this to identify weak courses in a program.

    Response:
    {
      "programId": "bscs",
      "semester": "6th",
      "courses": [
        {
          "courseCode": "CMC371",
          "courseTitle": "Software Engineering",
          "clos": [
            {
              "code": "CLO-1",
              "description": "...",
              "mappedGA": "GA-1",
              "attainmentPercent": 72.5,
              "status": "Met"
            }
          ]
        }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        semester   = request.query_params.get('semester', '').strip()

        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        ic_qs = InstructorCourse.objects.filter(program=program).prefetch_related(
            'clos__mapped_ga',
            'students__obe_marks__question',
            'obe_questions',
        )
        if semester:
            ic_qs = ic_qs.filter(semester=semester)

        courses_data = []
        for ic in ic_qs:
            # Build mark lookup once per course: { question_pk: [scores] }
            all_questions = list(ic.obe_questions.all())
            q_marks = {}
            for m in OBEStudentMark.objects.filter(question__in=all_questions).select_related('question'):
                q_marks.setdefault(m.question_id, []).append(m.score)

            clos_data = []
            for clo in ic.clos.select_related('mapped_ga').all():
                questions = [q for q in all_questions if clo.code in (q.mapped_clos or [])]
                total_possible = sum(q.max_marks * len(q_marks.get(q.pk, [])) for q in questions)
                total_obtained = sum(sum(q_marks.get(q.pk, [])) for q in questions)

                pct        = round((total_obtained / total_possible * 100), 1) if total_possible > 0 else 0
                status_str = 'Met' if pct >= ATTAINMENT_THRESHOLD else 'Not Met'

                clos_data.append({
                    'code':              clo.code,
                    'description':       clo.description,
                    'mappedGA':          clo.mapped_ga.ga_id if clo.mapped_ga else None,
                    'attainmentPercent': pct,
                    'status':            status_str,
                })

            courses_data.append({
                'courseCode':   ic.code,
                'courseTitle':  ic.title,
                'semester':     ic.semester,
                'academicYear': ic.academic_year,
                'clos':         clos_data,
            })

        return Response({
            'programId': program.code.lower(),
            'semester':  semester or 'all',
            'courses':   courses_data,
        })


class POAttainmentView(APIView):
    """
    GET /api/reports/po-attainment/?programId=bscs

    Program Outcome Attainment — aggregates CLO → GA → PO.
    The direct HEC compliance report.

    Response:
    {
      "programId": "bscs",
      "programName": "...",
      "pos": [
        {
          "id": "PO1",
          "text": "...",
          "attainmentPercent": 68.3,
          "status": "Partially Met",
          "contributingGAs": [
            { "gaId": "GA-1", "gaName": "...", "attainmentPercent": 72.5 }
          ]
        }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        gas = list(GraduateAttribute.objects.filter(department=program.department))

        # Perf fix: previously this ran one InstructorCourse query per GA, then
        # inside that a .filter() call on a prefetched relation (which silently
        # discards the prefetch cache and re-hits the DB), then an OBEStudentMark
        # query per (GA, course, CLO) triple — for a department with, say, 8 GAs,
        # 20 courses, and 3 CLOs each, that's roughly 8 + 8*20*3 = ~488 queries.
        # Fetch every relevant course once, with CLOs and questions prefetched...
        courses = list(
            InstructorCourse.objects.filter(
                program=program,
                clos__mapped_ga__in=gas,
            )
            .prefetch_related('clos', 'obe_questions')
            .distinct()
        )

        # ...and every OBE mark for any question in any of those courses, once.
        all_question_ids = [q.pk for ic in courses for q in ic.obe_questions.all()]
        marks_by_question = {}
        for m in OBEStudentMark.objects.filter(question_id__in=all_question_ids):
            marks_by_question.setdefault(m.question_id, []).append(m.score)

        # Everything below this point is in-memory — no more queries.
        ga_attainment = {}   # ga_id → percent
        for ga in gas:
            total_possible = 0
            total_obtained  = 0
            for ic in courses:
                clos_for_ga = [c for c in ic.clos.all() if c.mapped_ga_id == ga.id]
                if not clos_for_ga:
                    continue
                clo_codes = {c.code for c in clos_for_ga}
                questions = [
                    q for q in ic.obe_questions.all()
                    if clo_codes & set(q.mapped_clos or [])
                ]
                for q in questions:
                    scores = marks_by_question.get(q.pk, [])
                    total_possible += q.max_marks * len(scores)
                    total_obtained  += sum(scores)

            ga_attainment[ga.ga_id] = round(
                (total_obtained / total_possible * 100), 1
            ) if total_possible > 0 else 0

        # Map GAs up to POs
        pos_data = []
        for po in program.objectives.prefetch_related('ga_mappings__graduate_attribute').all():
            contributing_gas = []
            po_percents = []

            for mapping in po.ga_mappings.select_related('graduate_attribute').all():
                ga     = mapping.graduate_attribute
                pct    = ga_attainment.get(ga.ga_id, 0)
                po_percents.append(pct)
                contributing_gas.append({
                    'gaId':              ga.ga_id,
                    'gaName':            ga.name,
                    'attainmentPercent': pct,
                })

            po_avg = round(sum(po_percents) / len(po_percents), 1) if po_percents else 0
            if po_avg >= 70:
                po_status = 'Met'
            elif po_avg >= ATTAINMENT_THRESHOLD:
                po_status = 'Partially Met'
            else:
                po_status = 'Not Met'

            pos_data.append({
                'id':                 po.code,
                'text':               po.description,
                'attainmentPercent':  po_avg,
                'status':             po_status,
                'contributingGAs':    contributing_gas,
            })

        return Response({
            'programId':   program.code.lower(),
            'programName': program.name,
            'pos':         pos_data,
        })


class InstructorPerformanceView(APIView):
    """
    GET /api/reports/instructor-performance/?departmentId=computing

    Shows per-instructor: which courses are below attainment threshold.
    For dept_admin and QA use.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dept_id = request.query_params.get('departmentId', '').strip()
        if not dept_id:
            return Response({'error': 'departmentId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({'error': f'Department "{dept_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        instructors = list(
            InstructorProfile.objects.filter(
                department=department
            ).select_related('user').prefetch_related(
                'instructor_courses__clos',
                'instructor_courses__obe_questions',
            )
        )

        # Perf fix: this previously ran one OBEStudentMark query per course,
        # inside a loop over every instructor — for a department with 15
        # instructors averaging 3 courses each, that's 45+ queries just for
        # marks. Batch-fetch every mark for every question across every
        # instructor's courses in this department in a single query instead.
        all_question_ids = [
            q.pk
            for profile in instructors
            for ic in profile.instructor_courses.all()
            for q in ic.obe_questions.all()
        ]
        marks_by_question = {}
        for m in OBEStudentMark.objects.filter(question_id__in=all_question_ids):
            marks_by_question.setdefault(m.question_id, []).append(m.score)

        result = []
        for profile in instructors:
            courses_data = []
            for ic in profile.instructor_courses.all():
                clo_attainments = []
                all_qs_cohort = list(ic.obe_questions.all())
                clo_qs_cohort = ic.clos.all()
                for clo in clo_qs_cohort:
                    questions = [q for q in all_qs_cohort if clo.code in (q.mapped_clos or [])]
                    total_p = sum(q.max_marks * len(marks_by_question.get(q.pk, [])) for q in questions)
                    total_o = sum(sum(marks_by_question.get(q.pk, [])) for q in questions)
                    pct = round(total_o / total_p * 100, 1) if total_p > 0 else 0
                    clo_attainments.append(pct)

                avg = round(sum(clo_attainments) / len(clo_attainments), 1) if clo_attainments else 0
                courses_data.append({
                    'courseCode':        ic.code,
                    'courseTitle':       ic.title,
                    'semester':          ic.semester,
                    'academicYear':      ic.academic_year,
                    'avgCLOAttainment':  avg,
                    'belowThreshold':    avg < ATTAINMENT_THRESHOLD,
                })

            below_count = sum(1 for c in courses_data if c['belowThreshold'])
            result.append({
                'employeeId':       profile.employee_id,
                'name':             profile.user.get_full_name() or profile.user.username,
                'designation':      profile.designation,
                'totalCourses':     len(courses_data),
                'coursesBelowThreshold': below_count,
                'courses':          courses_data,
            })

        return Response({'departmentId': dept_id, 'instructors': result})


class CohortComparisonView(APIView):
    """
    GET /api/reports/cohort-comparison/?programId=bscs&gaId=GA-1

    Compares GA attainment across academic years/batches.
    Requires InstructorCourse.academic_year to be populated.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        ga_id      = request.query_params.get('gaId', '').strip()

        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        ga = None
        if ga_id:
            try:
                ga = GraduateAttribute.objects.get(ga_id=ga_id)
            except GraduateAttribute.DoesNotExist:
                return Response({'error': f'GA "{ga_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        if ga:
            courses = InstructorCourse.objects.filter(
                program=program, clos__mapped_ga=ga
            ).prefetch_related('clos', 'obe_questions').distinct()
        else:
            courses = InstructorCourse.objects.filter(
                program=program
            ).prefetch_related('clos', 'obe_questions')

        courses = list(courses)

        # Perf fix: same pattern as POAttainmentView/InstructorPerformanceView —
        # was one OBEStudentMark query per (course, CLO) pair. Batch once.
        all_question_ids = [q.pk for ic in courses for q in ic.obe_questions.all()]
        marks_by_question = {}
        for m in OBEStudentMark.objects.filter(question_id__in=all_question_ids):
            marks_by_question.setdefault(m.question_id, []).append(m.score)

        # Group by academic_year
        by_year = {}
        for ic in courses:
            year = ic.academic_year or 'Unknown'
            if year not in by_year:
                by_year[year] = {'total_possible': 0, 'total_obtained': 0}

            clo_qs = [c for c in ic.clos.all() if (c.mapped_ga_id == ga.id if ga else True)]
            for clo in clo_qs:
                questions = [q for q in ic.obe_questions.all() if clo.code in (q.mapped_clos or [])]
                for q in questions:
                    scores = marks_by_question.get(q.pk, [])
                    by_year[year]['total_possible'] += q.max_marks * len(scores)
                    by_year[year]['total_obtained']  += sum(scores)

        cohorts = []
        for year in sorted(by_year.keys()):
            tp = by_year[year]['total_possible']
            to = by_year[year]['total_obtained']
            cohorts.append({
                'academicYear':      year,
                'attainmentPercent': round(to / tp * 100, 1) if tp > 0 else 0,
            })

        return Response({
            'programId': program.code.lower(),
            'gaId':      ga_id,
            'gaName':    ga.name if ga else None,
            'cohorts':   cohorts,
        })


class AtRiskStudentsView(APIView):
    """
    GET /api/reports/at-risk-students/?programId=bscs&semester=6th

    Students below attainment threshold on 2+ CLOs across enrolled courses.
    For dept_admin and admission early intervention.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        semester   = request.query_params.get('semester', '').strip()

        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        ic_qs = InstructorCourse.objects.filter(program=program)
        if semester:
            ic_qs = ic_qs.filter(semester=semester)

        # Map regNo → list of failed CLOs
        student_failures = {}

        for ic in ic_qs.prefetch_related('students__obe_marks__question', 'clos', 'obe_questions'):
            # Build mark lookup dict once per course — avoids N×M×P×Q DB queries
            # Structure: { (student_pk, question_pk): score }
            all_questions = list(ic.obe_questions.all())
            mark_lookup   = {}
            for student in ic.students.prefetch_related('obe_marks__question').all():
                for obe_mark in student.obe_marks.all():
                    mark_lookup[(student.pk, obe_mark.question_id)] = obe_mark.score

            for student in ic.students.all():
                for clo in ic.clos.all():
                    questions = [q for q in all_questions if clo.code in (q.mapped_clos or [])]
                    total_p   = sum(q.max_marks for q in questions)
                    total_o   = sum(mark_lookup.get((student.pk, q.pk), 0) for q in questions)
                    pct       = round(total_o / total_p * 100, 1) if total_p > 0 else 0

                    if pct < ATTAINMENT_THRESHOLD:
                        key = student.reg_no
                        if key not in student_failures:
                            student_failures[key] = {
                                'regNo':      student.reg_no,
                                'name':       student.name,
                                'failedCLOs': [],
                            }
                        student_failures[key]['failedCLOs'].append({
                            'courseCode': ic.code,
                            'cloCode':    clo.code,
                            'attainment': pct,
                        })

        at_risk = [
            v for v in student_failures.values()
            if len(v['failedCLOs']) >= 2
        ]
        at_risk.sort(key=lambda x: len(x['failedCLOs']), reverse=True)

        return Response({
            'programId':   program.code.lower(),
            'semester':    semester or 'all',
            'threshold':   ATTAINMENT_THRESHOLD,
            'atRiskCount': len(at_risk),
            'students':    at_risk,
        })


class GapAnalysisView(APIView):
    """
    GET /api/reports/gap-analysis/?programId=bscs

    Which GAs have zero or low course coverage in this program.
    Tells QA where curriculum gaps exist.

    Response per GA:
    {
      "gaId": "GA-6",
      "gaName": "Individual and Team Work",
      "mappedCoursesCount": 0,
      "activeCLOsCount": 0,
      "avgAttainment": 0,
      "status": "No Coverage"
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        gas = list(GraduateAttribute.objects.filter(department=program.department))
        result = []

        # Perf fix: was 2 queries per GA (mapped_courses, active_clos) plus an
        # OBEStudentMark query per CLO inside — for a department with several
        # GAs this added up fast on a report page QA is likely to load often.
        # Fetch every relevant CLO across all GAs once, with its course's
        # questions prefetched, then batch every OBEStudentMark query into one.
        all_active_clos = list(
            CLO.objects.filter(course__program=program, mapped_ga__in=gas)
            .select_related('mapped_ga')
            .prefetch_related('course__obe_questions')
        )
        clos_by_ga = {}
        for clo in all_active_clos:
            clos_by_ga.setdefault(clo.mapped_ga_id, []).append(clo)

        questions_by_clo = {}
        all_question_ids = set()
        for clo in all_active_clos:
            matched = [q for q in clo.course.obe_questions.all() if clo.code in (q.mapped_clos or [])]
            questions_by_clo[clo.id] = matched
            all_question_ids.update(q.pk for q in matched)

        marks_by_question = {}
        for m in OBEStudentMark.objects.filter(question_id__in=all_question_ids):
            marks_by_question.setdefault(m.question_id, []).append(m.score)

        for ga in gas:
            mapped_courses = Course.objects.filter(program=program, mapped_gas=ga)
            active_clos    = clos_by_ga.get(ga.id, [])

            total_p = 0
            total_o = 0
            for clo in active_clos:
                for q in questions_by_clo.get(clo.id, []):
                    scores   = marks_by_question.get(q.pk, [])
                    total_p += q.max_marks * len(scores)
                    total_o += sum(scores)

            avg_att = round(total_o / total_p * 100, 1) if total_p > 0 else 0
            courses_count = mapped_courses.count()
            clos_count    = len(active_clos)

            if courses_count == 0:
                gap_status = 'No Coverage'
            elif clos_count == 0:
                gap_status = 'Mapped but No CLOs'
            elif avg_att < ATTAINMENT_THRESHOLD:
                gap_status = 'Low Attainment'
            else:
                gap_status = 'Adequate'

            result.append({
                'gaId':               ga.ga_id,
                'gaName':             ga.name,
                'mappedCoursesCount': courses_count,
                'activeCLOsCount':    clos_count,
                'avgAttainment':      avg_att,
                'status':             gap_status,
            })

        critical = sum(1 for r in result if r['status'] in ('No Coverage', 'Mapped but No CLOs'))

        return Response({
            'programId':     program.code.lower(),
            'programName':   program.name,
            'totalGAs':      len(result),
            'criticalGaps':  critical,
            'attributes':    result,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# TEACHER ONBOARDING (Dept Admin)
# ═══════════════════════════════════════════════════════════════════════════════

class TeacherOnboardingView(APIView):
    """
    POST /api/admin/teachers/
    Create a new instructor account. Dept Admin only.

    Payload:
    {
      "name":        "Dr. Ahmed Ali",
      "email":       "ahmed.ali@iqra.edu.pk",
      "employeeId":  "INS-CS-005",
      "designation": "Assistant Professor",
      "departmentId": "computing"
    }

    - Creates User with role='instructor', temp password = employeeId
    - Sets must_change_password = True
    - Creates InstructorProfile linked to the user
    - Returns the teacher object + mustChangePassword flag

    DELETE /api/admin/teachers/<employee_id>/
    Remove a teacher. Cannot delete if they have active InstructorCourse records.
    """
    permission_classes = [IsDeptAdmin]

    def post(self, request):
        ws = TeacherWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d           = ws.validated_data
        name        = d['name']
        email       = d['email'].lower()
        employee_id = d['employeeId']
        designation = d.get('designation', '')
        dept_id     = d['departmentId']

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {'error': f'An account with email "{email}" already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if InstructorProfile.objects.filter(employee_id=employee_id).exists():
            return Response(
                {'error': f'Employee ID "{employee_id}" is already registered'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use email as username — email is unique so username is unique
        from django.contrib.auth.hashers import make_password
        from django.conf import settings as _settings
        user = User.objects.create(
            username=email,
            email=email,
            first_name=name.split()[0] if name else '',
            last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else '',
            role='instructor',
            password=make_password(_settings.DEFAULT_TEMP_PASSWORD),
            must_change_password=True,
            is_active=True,
        )

        profile = InstructorProfile.objects.create(
            user=user,
            employee_id=employee_id,
            designation=designation,
            department=department,
        )

        return Response({
            'employeeId':         profile.employee_id,
            'name':               user.get_full_name() or name,
            'email':              user.email,
            'designation':        profile.designation,
            'departmentId':       department.dept_id,
            'departmentName':     department.name,
            'mustChangePassword': True,
            'message':            f'Account created. Default password is: {_settings.DEFAULT_TEMP_PASSWORD}',
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, employee_id=None):
        if not employee_id:
            return Response({'error': 'employeeId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = InstructorProfile.objects.select_related('user').get(
                employee_id=employee_id
            )
        except InstructorProfile.DoesNotExist:
            return Response(
                {'error': f'Instructor "{employee_id}" not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Block deletion if they have active courses with student data
        active_courses = InstructorCourse.objects.filter(
            instructor=profile
        ).filter(students__isnull=False).distinct()

        if active_courses.exists():
            return Response({
                'error': f'Cannot delete — instructor has {active_courses.count()} active course(s) with enrolled students. Remove course assignments first.',
            }, status=status.HTTP_409_CONFLICT)

        user = profile.user
        profile.delete()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Change Password ───────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    Authenticated. Used on first login or voluntary password change.

    Payload: { "currentPassword": "...", "newPassword": "..." }

    On success, clears must_change_password flag.
    """
    permission_classes = [IsAuthenticated]
    # Requires a valid access token already, so the attack surface is smaller
    # than login, but still guards against brute-forcing currentPassword with
    # a stolen/leaked token. 10/min per IP.
    throttle_scope = 'change_password'

    def post(self, request):
        data             = request.data
        current_password = data.get('currentPassword', '')
        new_password     = data.get('newPassword', '').strip()

        if not current_password or not new_password:
            return Response(
                {'error': 'currentPassword and newPassword are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 6:
            return Response(
                {'error': 'New password must be at least 6 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        if not user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        return Response({'message': 'Password changed successfully'})


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT ENROLLMENT (Dept Admin)
# ═══════════════════════════════════════════════════════════════════════════════

class StudentEnrollmentView(APIView):
    """
    POST /api/admin/enroll/
    Dept Admin enrolls students into an instructor's course.

    Payload:
    {
      "courseId": "course-assigned-CMC111-INCSLK3-bscs",  // InstructorCourse frontend_id
      "students": [
        { "regNo": "FA22-BSCS-0012", "name": "Ahmed Khan" },
        ...
      ]
    }

    Creates CourseStudent records for each student.
    Idempotent — safe to call multiple times.

    DELETE /api/admin/enroll/
    Remove a student from a course.
    Payload: { "courseId": "...", "regNo": "FA22-BSCS-0012" }
    """
    permission_classes = [IsDeptAdmin]

    def post(self, request):
        admin_dept = get_admin_department(request.user)
        if not admin_dept:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)

        data      = request.data
        course_id = data.get('courseId', '').strip()
        students  = data.get('students', [])

        if not course_id:
            return Response({'error': 'courseId is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(students, list):
            return Response({'error': 'students must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ic = InstructorCourse.objects.get(frontend_id=course_id)
        except InstructorCourse.DoesNotExist:
            return Response(
                {'error': f'Course "{course_id}" not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # A dept_admin may only enroll students into courses that belong
        # to their own managed department.
        if ic.department_id != admin_dept.id:
            return Response(
                {'error': f'You can only manage enrollment for courses in your own department ({admin_dept.name}).'},
                status=status.HTTP_403_FORBIDDEN
            )

        # True sync / idempotent overwrite:
        # The incoming list IS the desired roster. Add new students, remove
        # students no longer in the list (but preserve their marks data).
        incoming_reg_nos = set()
        for s in students:
            reg_no = s.get('regNo', '').strip().upper()
            if reg_no:
                incoming_reg_nos.add(reg_no)

        # Empty list = clear all enrollments (admin removed everyone)
        if not incoming_reg_nos:
            removed = CourseStudent.objects.filter(course=ic).delete()[0]
            return Response({
                'courseId': course_id,
                'enrolled': [],
                'removed':  removed,
                'message':  'All students removed from course',
            })

        # Add new students
        enrolled = []
        for s in students:
            reg_no = s.get('regNo', '').strip().upper()
            name   = s.get('name', '').strip()
            if not reg_no:
                continue
            _, created = CourseStudent.objects.get_or_create(
                course=ic, reg_no=reg_no,
                defaults={'name': name or reg_no}
            )
            if created:
                enrolled.append(reg_no)

        # Remove students no longer in the list (preserves marks for remaining)
        removed_qs = CourseStudent.objects.filter(course=ic).exclude(reg_no__in=incoming_reg_nos)
        removed    = list(removed_qs.values_list('reg_no', flat=True))
        removed_qs.delete()

        return Response({
            'courseId': course_id,
            'enrolled': enrolled,
            'removed':  removed,
            'total':    len(incoming_reg_nos),
            'message':  f'{len(enrolled)} added, {len(removed)} removed, {len(incoming_reg_nos)} total enrolled',
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        admin_dept = get_admin_department(request.user)
        if not admin_dept:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)

        data      = request.data
        course_id = data.get('courseId', '').strip()
        reg_no    = data.get('regNo', '').strip().upper()

        if not course_id or not reg_no:
            return Response(
                {'error': 'courseId and regNo are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        deleted, _ = CourseStudent.objects.filter(
            course__frontend_id=course_id, reg_no=reg_no,
            course__department=admin_dept,   # scoped — can't touch other depts
        ).delete()

        if not deleted:
            return Response({'error': 'Enrollment not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ═══════════════════════════════════════════════════════════════════════════════
# SEMESTER CLOSING / FINALIZATION
# ═══════════════════════════════════════════════════════════════════════════════
#
# Solves: "when a semester ends, results should be locked and a teacher
# switching subjects should not wipe out the previous course's data."
#
# Flow:
#   1. Dept Admin (or QA) reviews a course's marks at semester end
#   2. POST /api/admin/finalize-course/ — snapshots final grades into
#      FinalResult (permanent transcript table) and marks the
#      InstructorCourse as 'closed'
#   3. Closed courses become read-only — InstructorCourseView.post() will
#      reject any further mark edits to a closed course
#   4. If the same teacher is later assigned the same course again for a
#      NEW term, a fresh InstructorCourse is created (frontend_id includes
#      academic_year) — the closed one is never touched or reused
# ───────────────────────────────────────────────────────────────────────────────

from .models import FinalResult


class FinalizeCourseView(APIView):
    """
    POST /api/admin/finalize-course/
    Body: { "courseId": "course-assigned-CMC111-INS-CS-001-bscs-fall2024" }

    Dept Admin or QA only. Permanently closes a course:
      - Computes each student's final grade + CLO attainments
      - Snapshots them into FinalResult (survives any future changes)
      - Sets InstructorCourse.status = 'closed'
      - Course becomes read-only — instructor can no longer edit marks

    Cannot be undone via API (deliberately — closing is a final action).
    If a genuine correction is needed, QA/admin must use Django admin directly.
    """
    def get_permissions(self):
        return [IsDeptAdminOrQA()] if self.request.method == 'POST' else [IsAuthenticated()]

    def post(self, request):
        course_id = request.data.get('courseId', '').strip()
        if not course_id:
            return Response({'error': 'courseId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ic = InstructorCourse.objects.select_related(
                'instructor__user', 'department', 'program'
            ).prefetch_related(
                'students__marks__unit_item__category',
                'students__obe_marks__question',
                'obe_questions',
            ).get(frontend_id=course_id)
        except InstructorCourse.DoesNotExist:
            return Response({'error': f'Course "{course_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        # Department scoping — a dept_admin may only close courses that
        # belong to their own managed department. Without this check, any
        # dept_admin could close (and permanently lock grades on) any
        # course in any department in the entire university.
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept:
                return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)
            if ic.department_id != admin_dept.id:
                return Response(
                    {'error': f'You can only close courses in your own department ({admin_dept.name}).'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if ic.status == 'closed':
            return Response(
                {'error': 'This course is already closed', 'closedAt': ic.closed_at},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Validation gate ──────────────────────────────────────────────────
        # Closing is irreversible via API — once FinalResult rows are written
        # and the course is locked, there is no API path back. So we refuse
        # to close (and write nothing) if the course's grading structure is
        # internally inconsistent. The frontend enforces these same rules in
        # its UI, but the backend must never trust that and must re-verify
        # before permanently committing a grade.
        validation_errors = []

        categories = list(ic.categories.all())
        if not categories:
            validation_errors.append('Course has no marks categories defined.')
        else:
            cat_total = round(sum(c.percentage for c in categories), 2)
            if cat_total != 100:
                validation_errors.append(
                    f'Category percentages sum to {cat_total}%, not 100%.'
                )

            for cat in categories:
                units = list(cat.unit_items.all())
                if cat.percentage > 0 and not units:
                    validation_errors.append(
                        f'Category "{cat.name}" has {cat.percentage}% weight but no units defined.'
                    )
                elif units:
                    unit_total = round(sum(u.weightage for u in units), 2)
                    if unit_total != 100:
                        validation_errors.append(
                            f'Category "{cat.name}" unit weightages sum to {unit_total}%, not 100%.'
                        )

        if not ic.students.exists():
            validation_errors.append('Course has no enrolled students to finalize.')

        if validation_errors:
            return Response(
                {
                    'error': 'Course cannot be closed — grading structure is invalid.',
                    'details': validation_errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        questions = list(ic.obe_questions.all())
        instructor_name = ic.instructor.user.get_full_name() or ic.instructor.user.email

        results_created = []
        for student in ic.students.all():
            pct = _student_total_percentage(student)
            grade_letter, grade_points = _get_grade(pct, ic)
            clo_attainments = _clo_attainments_for_student(student, questions)

            result, _ = FinalResult.objects.update_or_create(
                student_reg_no=student.reg_no,
                course_code=ic.code,
                academic_year=ic.academic_year,
                defaults=dict(
                    student_name=student.name,
                    course_title=ic.title,
                    instructor_name=instructor_name,
                    department=ic.department,
                    program=ic.program,
                    semester=ic.semester,
                    credit_hours=ic.credit_hours,
                    final_percentage=pct,
                    grade_letter=grade_letter,
                    grade_points=grade_points,
                    clo_attainments=clo_attainments,
                    source_course=ic,
                )
            )
            results_created.append({
                'regNo': student.reg_no, 'grade': grade_letter, 'percentage': pct
            })

        # Lock the course
        ic.status    = 'closed'
        ic.closed_at = timezone.now()
        ic.closed_by = request.user
        ic.save()

        return Response({
            'courseId':        course_id,
            'courseCode':      ic.code,
            'status':          'closed',
            'closedAt':        ic.closed_at,
            'studentsFinalized': len(results_created),
            'results':         results_created,
        })


class FinalResultsView(APIView):
    """
    GET /api/reports/final-results/?regNo=FA22-BSCS-0012
    GET /api/reports/final-results/?courseCode=CMC111&academicYear=Fall-2024

    Read permanent transcript records. Used for official report cards
    once a semester is closed — never affected by later teacher reassignments
    or course edits.

    Students can ONLY read their own results. Their regNo is forced from
    their own Student profile regardless of what was passed in the query
    string — prevents one student from reading another student's transcript
    by guessing or enumerating regNo values.

    QA, instructor, dept_admin and admin roles may query any regNo or
    courseCode freely, since they have legitimate institutional need to
    view records outside their own.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reg_no        = request.query_params.get('regNo', '').strip()
        course_code   = request.query_params.get('courseCode', '').strip().upper()
        academic_year = request.query_params.get('academicYear', '').strip()

        # Students can only ever see their own results — override whatever
        # regNo was passed in, and ignore courseCode-only lookups entirely
        # (those would expose a whole course's roster of grades).
        if request.user.role == 'student':
            try:
                own_reg_no = request.user.student_profile.reg_no
            except Exception:
                return Response(
                    {'error': 'Student profile not found'},
                    status=status.HTTP_403_FORBIDDEN
                )
            reg_no      = own_reg_no
            course_code = ''   # force regNo-only lookup, never a full roster

        qs = FinalResult.objects.all()
        if reg_no:
            qs = qs.filter(student_reg_no__iexact=reg_no)
        if course_code:
            qs = qs.filter(course_code__iexact=course_code)
        if academic_year:
            qs = qs.filter(academic_year__iexact=academic_year)

        if not reg_no and not course_code:
            return Response(
                {'error': 'regNo or courseCode is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = [{
            'regNo':           r.student_reg_no,
            'studentName':     r.student_name,
            'courseCode':      r.course_code,
            'courseTitle':     r.course_title,
            'instructorName':  r.instructor_name,
            'academicYear':    r.academic_year,
            'semester':        r.semester,
            'creditHours':     r.credit_hours,
            'finalPercentage': r.final_percentage,
            'grade':           r.grade_letter,
            'gradePoints':     r.grade_points,
            'cloAttainments':  r.clo_attainments,
            'finalizedAt':     r.finalized_at,
        } for r in qs.order_by('-finalized_at')]

        return Response({'results': results, 'count': len(results)})
