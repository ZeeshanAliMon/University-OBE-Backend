from django.contrib.auth import authenticate

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


# ─── Graduate Attributes — Create
class GraduateAttributeCreateView(APIView):
    """
    POST /api/gas/
    Body: { id, name, description, departmentId, programId? }
    QA only — called when a new program is created and its GAs are seeded.
    """
    permission_classes = [IsQA]

    def post(self, request):
        data    = request.data
        ga_id   = data.get('id', '').strip()
        name    = data.get('name', '').strip()
        dept_id = data.get('departmentId', '').strip()
        prog_id = data.get('programId', '')

        if not ga_id or not name or not dept_id:
            return Response(
                {'error': 'id, name and departmentId are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if GraduateAttribute.objects.filter(ga_id=ga_id).exists():
            # Return existing — idempotent
            ga = GraduateAttribute.objects.get(ga_id=ga_id)
            return Response(GraduateAttributeSerializer(ga).data, status=status.HTTP_200_OK)

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({'error': f'Department "{dept_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)

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

