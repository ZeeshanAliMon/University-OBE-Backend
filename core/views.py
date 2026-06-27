from django.contrib.auth import authenticate
from django.db import models

from rest_framework             import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response    import Response
from rest_framework.views       import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models      import (
    Department, Program, GraduateAttribute, Course,
    InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)
from .serializers import (
    LoginSerializer, UserSerializer,
    DepartmentSerializer, ProgramSerializer,
    GraduateAttributeSerializer, CourseSerializer,
    InstructorCourseSerializer,
)
from .permissions import IsQA, IsQAOrReadOnly, IsInstructor, IsAdmission, IsDeptAdmin


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def get_instructor_profile(user):
    try:
        return user.instructor_profile
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

    def post(self, request):
        s = LoginSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(
            username=s.validated_data['username'],
            password=s.validated_data['password'],
        )
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
        data    = request.data
        name    = data.get('name', '').strip()
        code    = data.get('code', '').strip()
        dept_id = data.get('departmentId', '').strip()

        if not name or not code or not dept_id:
            return Response(
                {'error': 'name, code and departmentId are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if Program.objects.filter(code__iexact=code).exists():
            return Response(
                {'error': f'Program with code "{code}" already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        program = Program.objects.create(
            name=name, code=code, department=department,
            vision=data.get('vision', ''), mission=data.get('mission', '')
        )
        # Also process POs if sent on creation
        pos_data = data.get('pos', [])
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
        data    = request.data
        ga_id   = data.get('id', '').strip()
        name    = data.get('name', '').strip()
        dept_id = data.get('departmentId', '').strip()
        prog_id = data.get('programId', '')
        if not ga_id or not name or not dept_id:
            return Response({'error': 'id, name and departmentId are required'}, status=status.HTTP_400_BAD_REQUEST)
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
            ga_id=ga_id, name=name,
            description=data.get('description', ''),
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
        data       = request.data
        code       = data.get('code', '').strip()
        title      = data.get('title', '').strip()
        dept_id    = data.get('departmentId', '').strip()
        program_id = data.get('programId', '')
        mapped_gas = data.get('mappedGAs', [])

        if not code or not title or not dept_id:
            return Response(
                {'error': 'code, title and departmentId are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
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
            code=code, title=title,
            type=data.get('type', 'core'),
            department=department, program=program,
            credit_hours=data.get('credit_hours', 3)
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

            try:
                department = Department.objects.get(dept_id=dept_id)
            except Department.DoesNotExist:
                errors.append({'index': idx, 'error': f'Department "{dept_id}" not found'})
                continue

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

from .models      import AdmissionStudent
from .serializers import AdmissionStudentSerializer


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
            reg_no     = data.get('regNo', '').strip().upper()
            name       = data.get('name', '').strip()
            dept_id    = data.get('departmentId', '').strip()
            program_id = data.get('programId', '').strip()
            batch      = data.get('batch', 'Fall')
            semester   = data.get('semester', '1st')

            if not reg_no or not name or not dept_id or not program_id:
                errors.append({'index': idx, 'regNo': reg_no, 'error': 'regNo, name, departmentId and programId are required'})
                continue
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

            student, _ = AdmissionStudent.objects.update_or_create(
                reg_no=reg_no,
                defaults=dict(name=name, department=department, program=program, batch=batch, semester=semester)
            )
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
                student.department = Department.objects.get(slug=data['departmentId'])
            except Department.DoesNotExist:
                return Response(
                    {'error': f'Department "{data["departmentId"]}" not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if 'programId' in data:
            try:
                student.program = Program.objects.get(slug=data['programId'])
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

from .models import CourseAssignment, DeptAdminProfile


class CourseAssignmentView(APIView):
    """
    GET    /api/admin/course-assignments/
    POST   /api/admin/course-assignments/   { teacherId, courseCode, programId }
    DELETE /api/admin/course-assignments/   { teacherId, courseCode, programId }
    Dept admin assigns an instructor to a course+program combination.
    """
    permission_classes = [IsDeptAdmin]

    def get(self, request):
        qs = CourseAssignment.objects.select_related(
            'instructor__user', 'course', 'program'
        ).all()
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
        data        = request.data
        teacher_id  = data.get('teacherId', '').strip()
        course_code = data.get('courseCode', '').strip().upper()
        program_id  = data.get('programId', '').strip()

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

        program = None
        if program_id:
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)

        dept_admin = None
        try:
            dept_admin = request.user.dept_admin_profile
        except Exception:
            pass

        assignment, created = CourseAssignment.objects.get_or_create(
            instructor=instructor, course=course, program=program,
            defaults={'assigned_by': dept_admin}
        )
        return Response({
            'teacherId':  assignment.instructor.employee_id,
            'courseCode': assignment.course.code,
            'programId':  assignment.program.code.lower() if assignment.program else None,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        data        = request.data
        teacher_id  = data.get('teacherId', '').strip()
        course_code = data.get('courseCode', '').strip().upper()
        program_id  = data.get('programId', '').strip()

        qs = CourseAssignment.objects.filter(
            instructor__employee_id=teacher_id,
            course__code__iexact=course_code
        )
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)
        deleted, _ = qs.delete()
        if not deleted:
            return Response({'error': 'Assignment not found'}, status=status.HTTP_404_NOT_FOUND)
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
            'username':     request.user.username,
            'user_type':    'dept_admin',
            'departmentId': profile.department.dept_id,
            'departmentName': profile.department.name,
            'employeeId':   profile.employee_id,
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

    def _get_admin_dept(self, user):
        try:
            return user.dept_admin_profile.department
        except Exception:
            return None

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        dept = self._get_admin_dept(request.user)
        if not dept:
            return Response({'error': 'Profile not found'}, status=status.HTTP_403_FORBIDDEN)

        qs = SemesterPlan.objects.select_related('program')
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)
        else:
            qs = qs.filter(program__department=dept)

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
        dept = self._get_admin_dept(request.user)
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
        dept = self._get_admin_dept(request.user)
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

        # Try to get reg_no from Student profile
        # Fall back to username (App.tsx passes username as studentRegNo)
        try:
            student_profile = request.user.student_profile
            reg_no = student_profile.roll_number
        except Exception:
            # No Student profile — use username as reg_no
            reg_no = request.user.username

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
            all_students.extend(
                list(ic.students.prefetch_related('obe_marks__question', 'marks__unit_item__category').all())
            )
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

        # Build CLO → first GA mapping (best effort for display)
        clo_to_ga = {}
        if catalog_course:
            ga_list = list(catalog_course.mapped_gas.all())
            for q in all_questions:
                for clo in q.mapped_clos:
                    if clo not in clo_to_ga and ga_list:
                        clo_to_ga[clo] = ga_list[0].ga_id   # first GA as default

        clos_result = []
        for clo in sorted(clo_scores_all.keys()):
            scores         = clo_scores_all[clo]
            class_avg      = round(sum(scores) / len(scores), 2) if scores else 0.0
            passed_count   = sum(1 for s in scores if s >= ATTAINMENT_THRESHOLD)
            attain_pct     = round((passed_count / len(scores) * 100), 2) if scores else 0.0
            mapped_q_count = sum(1 for q in all_questions if clo in q.mapped_clos)
            clos_result.append({
                'code':                clo,
                'description':         clo,    # placeholder until CLO table added
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
