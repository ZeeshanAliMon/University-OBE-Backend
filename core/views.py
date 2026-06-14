from django.contrib.auth import authenticate
from django.utils.text import slugify

from rest_framework             import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response    import Response
from rest_framework.views       import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models      import Department, Program, GraduateAttribute, Course, InstructorCourse
from .serializers import (
    LoginSerializer, UserSerializer,
    DepartmentSerializer, ProgramSerializer,
    GraduateAttributeSerializer, CourseSerializer,
    InstructorCourseSerializer,
)
from .permissions import IsQA, IsInstructor


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def get_instructor_profile(user):
    try:
        return user.instructor_profile
    except Exception:
        return None


def make_unique_slug(base_slug, model_class, exclude_pk=None):
    """
    Generates a unique slug from base_slug.
    If 'bscs' is taken it tries 'bscs-2', 'bscs-3', etc.
    """
    slug = slugify(base_slug)
    qs   = model_class.objects.filter(slug=slug)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if not qs.exists():
        return slug
    counter = 2
    while True:
        candidate = f"{slug}-{counter}"
        qs = model_class.objects.filter(slug=candidate)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return candidate
        counter += 1


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if user is None:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return Response({'error': 'Account is disabled'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({**get_tokens_for_user(user), 'user': UserSerializer(user).data})


# ─── Departments ──────────────────────────────────────────────────────────────

class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Department.objects.all().order_by('name')
        return Response(DepartmentSerializer(qs, many=True).data)


class DepartmentDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsQA()]

    def _get(self, slug):
        try:
            return Department.objects.get(slug=slug)
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
        """
        POST /api/programs/
        Frontend sends: { id, name, code, departmentId, vision, mission, pos[], slug? }
        slug is optional — if not sent or empty we auto-generate from code.
        """
        data        = request.data
        name        = data.get('name', '').strip()
        code        = data.get('code', '').strip()
        dept_id     = data.get('departmentId', '').strip()
        vision      = data.get('vision', '')
        mission     = data.get('mission', '')
        raw_slug    = data.get('slug', '') or data.get('id', '')

        if not name or not code or not dept_id:
            return Response(
                {'error': 'name, code and departmentId are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            department = Department.objects.get(slug=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Auto-generate slug if not provided or empty
        slug_base = raw_slug if raw_slug else code
        slug      = make_unique_slug(slug_base, Program)

        if Program.objects.filter(code=code).exists():
            return Response(
                {'error': f'Program with code "{code}" already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        program = Program.objects.create(
            slug=slug, name=name, code=code,
            department=department, vision=vision, mission=mission
        )
        return Response(ProgramSerializer(program).data, status=status.HTTP_201_CREATED)


class ProgramDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsQA()]

    def _get(self, slug):
        try:
            return Program.objects.select_related('department').prefetch_related(
                'objectives__ga_mappings__graduate_attribute'
            ).get(slug=slug)
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GraduateAttribute.objects.select_related(
            'department', 'program'
        ).all().order_by('ga_id')
        return Response(GraduateAttributeSerializer(qs, many=True).data)


# ─── Courses ──────────────────────────────────────────────────────────────────

class CourseListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Course.objects.select_related(
            'department', 'program'
        ).prefetch_related('mapped_gas').all().order_by('code')
        return Response(CourseSerializer(qs, many=True).data)

    def post(self, request):
        """
        POST /api/courses/
        Frontend sends: { id, code, title, type, departmentId, programId,
                          mappedGAs[], credit_hours, slug? }
        slug is optional — auto-generated from id or code if not sent.
        """
        data       = request.data
        code       = data.get('code', '').strip()
        title      = data.get('title', '').strip()
        dept_id    = data.get('departmentId', '').strip()
        program_id = data.get('programId', '')
        course_type= data.get('type', 'core')
        mapped_gas = data.get('mappedGAs', [])
        credit_hrs = data.get('credit_hours', 3)
        raw_slug   = data.get('slug', '') or data.get('id', '')

        if not code or not title or not dept_id:
            return Response(
                {'error': 'code, title and departmentId are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            department = Department.objects.get(slug=dept_id)
        except Department.DoesNotExist:
            return Response(
                {'error': f'Department "{dept_id}" not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        program = None
        if program_id:
            try:
                program = Program.objects.get(slug=program_id)
            except Program.DoesNotExist:
                pass

        # Auto-generate slug if not provided
        slug_base = raw_slug if raw_slug else code
        slug      = make_unique_slug(slug_base, Course)

        course = Course.objects.create(
            slug=slug, code=code, title=title,
            type=course_type, department=department,
            program=program, credit_hours=credit_hrs
        )

        if mapped_gas:
            gas = GraduateAttribute.objects.filter(ga_id__in=mapped_gas)
            course.mapped_gas.set(gas)

        course.refresh_from_db()
        return Response(
            CourseSerializer(
                Course.objects.select_related('department','program')
                              .prefetch_related('mapped_gas')
                              .get(pk=course.pk)
            ).data,
            status=status.HTTP_201_CREATED
        )


class CourseDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsQA()]

    def _get(self, slug):
        try:
            return Course.objects.select_related(
                'department', 'program'
            ).prefetch_related('mapped_gas').get(slug=slug)
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


# ─── Instructor Courses ───────────────────────────────────────────────────────

class InstructorCourseView(APIView):
    permission_classes = [IsInstructor]

    def get(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response(
                {'error': 'Instructor profile not found for this user'},
                status=status.HTTP_403_FORBIDDEN
            )
        qs = InstructorCourse.objects.select_related(
            'department', 'program'
        ).filter(instructor=profile).order_by('created_at')
        return Response(InstructorCourseSerializer(qs, many=True).data)

    def post(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response(
                {'error': 'Instructor profile not found for this user'},
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
                department = Department.objects.get(slug=dept_id)
            except Department.DoesNotExist:
                errors.append({'index': idx, 'error': f'Department "{dept_id}" not found'})
                continue

            program = None
            if program_id:
                try:
                    program = Program.objects.get(slug=program_id)
                except Program.DoesNotExist:
                    pass

            obj, _ = InstructorCourse.objects.update_or_create(
                instructor=profile,
                frontend_id=frontend_id,
                defaults=dict(
                    code          = c.get('code', ''),
                    title         = c.get('title', ''),
                    department    = department,
                    program       = program,
                    credit_hours  = c.get('creditHours', 3),
                    categories    = c.get('categories', []),
                    units_data    = c.get('unitsData', {}),
                    students      = c.get('students', []),
                    obe_questions = c.get('obeQuestions', []),
                    obe_marks     = c.get('obeMarks', {}),
                )
            )
            saved.append(obj)

        if errors and not saved:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        result = InstructorCourseSerializer(saved, many=True).data
        if errors:
            return Response(
                {'courses': result, 'errors': errors},
                status=status.HTTP_207_MULTI_STATUS
            )
        return Response(result, status=status.HTTP_200_OK)
