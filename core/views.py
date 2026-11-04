from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.conf import settings as django_settings
from django.db import models
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import datetime
import logging
import traceback
import re
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
    SemesterPlan, AdmissionStudent, FinalResult,
    admission_term_index, current_term_index, semester_label, term_index,
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
from .surveys import SURVEY_KPI, batch_code, graduation_years, indirect_ga, indirect_po
from .permissions import IsQA, IsQAOrReadOnly, IsInstructor, IsAdmission, IsDeptAdmin, IsDeptAdminOrQA, IsStaffReport, IsInstructorOrStaffReport

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def get_instructor_profile(user):
    try:
        return user.instructor_profile
    except Exception:
        return None


def _course_student_has_marks(course_student):
    """True if this roster row has any unit or per-question mark. Such rows are
    never deleted by roster syncs -- deleting them would delete the marks."""
    return course_student.marks.exists() or course_student.obe_marks.exists()


_TERM_SEASON_RANK = {'spring': 1, 'summer': 2, 'fall': 3, 'autumn': 3}


def _term_sort_key(term):
    """Chronological sort key for academic years like "Fall-2024" / "spring 2023"."""
    m = re.search(r'([a-z]+)\W*(\d{4})', str(term or '').lower())
    if not m:
        return (0, 0, str(term or ''))
    return (int(m.group(2)), _TERM_SEASON_RANK.get(m.group(1), 0), str(term))


def _plan_semester(program_id, course_code, _cache=None):
    """Curriculum semester ('1st'..'8th') of a course, from its program's
    semester plan. Offerings are created with a blank semester, so without
    this every course looked like it belonged to the same semester."""
    if not program_id or not course_code:
        return ''
    if _cache is None:
        _cache = {}
    if program_id not in _cache:
        _cache[program_id] = {
            str(code).strip().upper(): plan.semester
            for plan in SemesterPlan.objects.filter(program_id=program_id)
            for code in (plan.course_codes or [])
        }
    return _cache[program_id].get(str(course_code).strip().upper(), '')


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



def _marks_with_question():
    """Each student's OBE marks with their question joined in. Prefetching
    'students__obe_marks__question' instead sends every question id in one
    IN (...), which SQLite rejects ("Expression tree is too large") once a query
    covers a few terms of a program."""
    return models.Prefetch('students__obe_marks', queryset=OBEStudentMark.objects.select_related('question'))


def _marks_with_unit():
    """Each student's unit marks with unit and category joined in, for the same reason."""
    return models.Prefetch('students__marks', queryset=StudentMark.objects.select_related('unit_item__category'))


def _offerings_in_semester(qs, program, semester):
    """Offerings of one curriculum semester. They are created with a blank
    semester, so a blank one is looked up in the program's semester plan."""
    plan = SemesterPlan.objects.filter(program=program, semester=semester).first()
    return qs.filter(
        models.Q(semester=semester) |
        models.Q(semester='', code__in=plan.course_codes if plan else [])
    )


def prefetch_instructor_course(qs):
    """Standard prefetch set for InstructorCourse querysets.

    MarksCategory/UnitItem/OBEQuestion for the marking structure live on the
    catalog Course now (shared across instructors/terms teaching the same
    course — see migration 0011), reached via InstructorCourse.catalog_course,
    NOT a direct 'categories' relation on InstructorCourse itself.
    """
    return qs.select_related('department', 'program', 'catalog_course').prefetch_related(
        'grade_scale',
        'catalog_course__markscategories__unit_items__questions',
        _marks_with_unit(),
        _marks_with_question(),
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
                # Current semester, from the reg number and date; the dashboard used to
                # guess it from the batch in the reg number.
                admitted = AdmissionStudent.objects.filter(
                    reg_no__iexact=user.student_profile.reg_no
                ).first()
                if admitted:
                    user_data['semester'] = admitted.current_semester
                    user_data['batch']    = admitted.batch
                # Without this the student dashboard could never resolve the
                # student's program, and fell back to hardcoded text
                # ("Bachelor of Science", "BS (Computer Science)") for everyone.
                if user.student_profile.program_id:
                    user_data['programId'] = user.student_profile.program.code.lower()
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
    # Was a blanket IsAuthenticated covering POST too — any logged-in user,
    # including a student, could create a new Program. ProgramDetailView
    # right below correctly splits GET (anyone) vs PATCH (QA only) via
    # get_permissions() — this view just never got the same treatment.
    # Reproduced before fixing: a student successfully created a program via
    # POST /api/programs/ with only their own login.
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsQA()]

    def get(self, request):
        qs = Program.objects.select_related('department').prefetch_related(
            'objectives__ga_mappings__graduate_attribute'
        ).all().order_by('name')
        dept_filter = request.query_params.get('department', '').strip()
        if dept_filter:
            qs = qs.filter(department__dept_id=dept_filter)
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
        qs = GraduateAttribute.objects.select_related('department', 'program')
        dept = request.query_params.get('department') or request.query_params.get('departmentId')
        if dept:
            qs = qs.filter(department__dept_id=dept)

        # Natural/numeric sort instead of lexicographic order_by('ga_id') —
        # plain string sort puts "GA-10" between "GA-1" and "GA-2". Mirrors
        # the naturalCompare() the frontend already applies for display;
        # fixing it here too so the API itself returns correct order for
        # any consumer that doesn't re-sort client-side (server-rendered
        # exports, future integrations, etc).
        #
        # NOTE: this helper must live at function level, NOT inside the
        # `if dept:` block above. It was previously nested there, so a
        # request with no ?department= param raised UnboundLocalError (500)
        # and the frontend's getAllData() silently received zero GAs.
        def _natural_key(ga):
            parts = re.split(r'(\d+)', ga.ga_id)
            return [int(p) if p.isdigit() else p.lower() for p in parts]

        items = sorted(qs, key=_natural_key)
        return Response(GraduateAttributeSerializer(items, many=True).data)

    def post(self, request):
        ws = GraduateAttributeWriteSerializer(data=request.data)
        if not ws.is_valid():
            return Response(ws.errors, status=status.HTTP_400_BAD_REQUEST)
        d       = ws.validated_data
        ga_id   = d['id']
        dept_id = d['departmentId']
        prog_id = d.get('programId', '')

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({"error": f'Department "{dept_id}" not found'}, status=status.HTTP_400_BAD_REQUEST)

        # An unknown programId used to be swallowed (`except DoesNotExist: pass`)
        # and the GA saved with NO program. The frontend posted a new program's
        # GAs before creating the program, so every seeded GA silently became
        # department-wide and appeared under every program in the department.
        # A GA asked for a specific program must actually get that program.
        program = None
        if prog_id:
            program = Program.objects.filter(code__iexact=prog_id).first()
            if not program:
                return Response(
                    {"error": f'Program "{prog_id}" not found — create the program before its Graduate Attributes.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if program.department_id != department.id:
                return Response(
                    {"error": f'Program "{prog_id}" does not belong to department "{dept_id}".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        existing = GraduateAttribute.objects.filter(ga_id__iexact=ga_id).first()
        if existing:
            # Used to return the stored record untouched, so a changed name or
            # description was ignored and a GA left without its program (above)
            # could never be linked to it.
            if existing.department_id != department.id:
                # ga_id is globally unique; never let one department overwrite
                # another department's attribute.
                return Response(
                    {"error": f'GA "{ga_id}" already exists in another department.'},
                    status=status.HTTP_409_CONFLICT,
                )
            existing.name = d['name']
            # The write serializer defaults description to '', so only apply it
            # when the client actually sent one — otherwise it would be blanked.
            if 'description' in request.data:
                existing.description = d.get('description', '')
            if program is not None:
                existing.program = program
            existing.save()
            return Response(GraduateAttributeSerializer(existing).data, status=status.HTTP_200_OK)

        ga = GraduateAttribute.objects.create(
            ga_id=ga_id, name=d['name'],
            description=d.get('description', ''),
            department=department, program=program
        )
        return Response(GraduateAttributeSerializer(ga).data, status=status.HTTP_201_CREATED)


# ─── Courses ──────────────────────────────────────────────────────────────────

class CourseListView(APIView):
    # CORRECTION to my earlier fix: I'd restricted POST to IsQA based on the
    # original handoff doc categorizing /api/courses/ under "QA" endpoints.
    # That was wrong — DeptAdminDashboard.tsx also legitimately calls
    # createCourse(), and this broke that in production (dept_admin got a
    # real 403 trying to add a course, reported as "course doesn't show up
    # in backend" since the frontend didn't surface the error). Checked the
    # frontend properly this time before fixing: createCourse is called from
    # both QADashboard.tsx and DeptAdminDashboard.tsx. createProgram, by
    # contrast, actually is QA-only (only QADashboard.tsx calls it) — that
    # one wasn't affected and doesn't need the same fix.
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [IsDeptAdminOrQA()]

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

        # SECURITY: dept_admin can only create courses in their own department
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or department.id != admin_dept.id:
                return Response(
                    {'error': 'You can only create courses in your own department.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        program = None
        if program_id:
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                pass

        try:
            with transaction.atomic():
                course = Course.objects.create(
                    code=d['code'], title=d['title'],
                    type=d.get('type', 'core'),
                    subtype=d.get('subtype', 'theory'),
                    department=department, program=program,
                    credit_hours=d.get('creditHours', 3)
                )
        except IntegrityError:
            return Response(
                {'error': f'Course "{d["code"]}" already exists for this department and program'},
                status=status.HTTP_400_BAD_REQUEST
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
        if self.request.method == 'GET':

            return [IsAuthenticated()]
        if self.request.method == 'DELETE':
            # Dept admin can delete courses from their own department.
            # Frontend (DeptAdminDashboard) already calls deleteCourse() —
            # this was the only thing blocking it from working.
            # PATCH (editing course title/mappedGAs etc.) stays QA-only.
            return [IsDeptAdminOrQA()]
        return [IsDeptAdminOrQA()]

    def _get(self, request, slug):
        program_code = (
            request.query_params.get("programId")
            or request.query_params.get("program_id")
        )
        qs = Course.objects.select_related(
            "department", "program"
        ).prefetch_related("mapped_gas")

        if program_code:
            qs = qs.filter(code__iexact=slug, program__code__iexact=program_code)
        else:
            qs = qs.filter(code__iexact=slug)

        return qs.first()  # returns None instead of raising if not found


    def get(self, request, slug):
        obj = self._get(request,slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CourseSerializer(obj).data)

    def patch(self, request, slug):
        obj = self._get(request, slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        # SECURITY: dept_admin can only edit courses in their own department
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or obj.department_id != admin_dept.id:
                return Response(
                    {'error': 'You can only edit courses in your own department.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        data = request.data.copy()
        if 'mappedGAs' in data:
            data['mappedGAs_write'] = data.pop('mappedGAs')
        # Map any of the frontend subtype field names to the model field 'subtype'.
        # Always normalise to lowercase: the model's choices are ('theory', 'lab')
        # but the frontend sends the display form ('Theory' / 'Lab'). This used to
        # lowercase only when 'subtype' was absent, which was harmless while the
        # serializer ignored subtype entirely — now that it is writable, an
        # un-normalised 'Theory' would fail ChoiceField validation and 400 the
        # whole request.
        raw_subtype = (
            data.get('subtype')
            or data.get('course_subtype')
            or data.get('courseSubtype')
            or data.get('courseType')
        )
        if raw_subtype:
            data['subtype'] = str(raw_subtype).lower()
        else:
            data.pop('subtype', None)
        s = CourseSerializer(obj, data=data, partial=True)
        if s.is_valid():
            s.save()
            obj.refresh_from_db()
            return Response(CourseSerializer(obj).data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug):
        obj = self._get(request,slug)
        if not obj:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        # Dept admin can only delete courses belonging to their own department.
        # QA (and admin role) can delete any course.
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or obj.department_id != admin_dept.id:
                return Response(
                    {'error': 'You can only delete courses in your own department.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # DATA-INTEGRITY FIX: InstructorCourse has no FK to Course (only a
        # loose code/department/program match — see the auto-create logic
        # in InstructorCourseView), so deleting a Course here previously did
        # NOT cascade to or even check for InstructorCourse records already
        # created from it. A dept_admin deleting a catalog entry while a
        # teacher has an active InstructorCourse for it (real students,
        # grades, CLOs already entered) would silently orphan that teaching
        # record: grades are NOT lost, but the course vanishes from every
        # catalog/admin view while still being actively taught — the same
        # "in progress, but now invisible" gap TeacherOnboardingView.delete
        # already guards against for instructors. Applying the same guard.
        conflicting = InstructorCourse.objects.filter(
            code=obj.code, department=obj.department, program=obj.program,
        ).filter(students__isnull=False).distinct()

        if conflicting.exists():
            return Response({
                'error': f'Cannot delete — {conflicting.count()} instructor course record(s) '
                         f'for "{obj.code}" already have enrolled students. Remove those '
                         f'course assignments first.',
            }, status=status.HTTP_409_CONFLICT)

        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Instructor Courses ───────────────────────────────────────────────────────

import re as _re

def _parse_percent_range_min(pct_str: str) -> float:
    """
    Mirrors frontend parsePercentRange() in InstructorDashboard.tsx exactly,
    but only returns the MIN bound (what GradeScale.min_percentage needs).
    Frontend always sends a range string like "88% - 100%" or "Below 60%",
    never a plain number — this must stay in sync with that function.
    """
    if not pct_str:
        return 0.0
    clean = pct_str.replace('%', '').strip()
    if 'below' in clean.lower():
        # "Below 60%" -> min is 0 (frontend: { min: 0, max: val })
        return 0.0
    parts = re.split(r'[-\u2013]|to', clean)
    if len(parts) >= 2:
        try:
            return float(parts[0].strip())
        except ValueError:
            return 0.0
    try:
        return float(clean)
    except ValueError:
        return 0.0


class InstructorCourseView(APIView):
    def get_permissions(self):
        # GET is shared: instructors read their own courses, QA/dept_admin/
        # admission read the full roster for analytics. Write operations
        # (POST/PATCH/DELETE, handled elsewhere on this view) stay
        # instructor-only via IsInstructor.
        if self.request.method == 'GET':
            return [IsInstructorOrStaffReport()]
        return [IsInstructor()]



    def get(self, request, frontend_id=None):
        try:

            role = request.user.role


            # ---------------- STAFF PATH ----------------
            if role in ('qa', 'dept_admin', 'admission', 'admin'):

                qs = InstructorCourse.objects.all()

                if role == 'dept_admin':
                    admin_dept = get_admin_department(request.user)

                    qs = qs.filter(department=admin_dept) if admin_dept else qs.none()

                dept_id = request.query_params.get('departmentId', '').strip()
                if dept_id:
                    qs = qs.filter(department__dept_id=dept_id)

                program_id = request.query_params.get('programId', '').strip()
                if program_id:
                    qs = qs.filter(program__code__iexact=program_id)

                academic_year = request.query_params.get('academicYear', '').strip()
                if academic_year:
                    qs = qs.filter(academic_year__iexact=academic_year)

                qs = prefetch_instructor_course(qs.order_by('created_at'))

                data = InstructorCourseSerializer(qs, many=True).data

                return Response(data)

            # ---------------- INSTRUCTOR PATH ----------------

            profile = get_instructor_profile(request.user)

            if not profile:
                return Response(
                    {'error': 'Instructor profile not found'},
                    status=status.HTTP_403_FORBIDDEN
                )

            assignments = CourseAssignment.objects.filter(
                instructor=profile
            ).select_related('course', 'program')


            for assignment in assignments:

                course = assignment.course
                program = assignment.program
                term = assignment.academic_year

                prog_suffix = program.code.lower() if program else 'all'
                # Normalise academic_year to match frontend format:
                # spaces → dashes, first letter capitalised (e.g. "Fall-2024")
                if term:
                    term_norm = term.replace(' ', '-')
                    term_norm = term_norm[0].upper() + term_norm[1:] if term_norm else term_norm
                    term_suffix = f"-{term_norm}"
                else:
                    term_suffix = ''
                frontend_id = (
                    f"course-assigned-{course.code}-"
                    f"{profile.employee_id}-{prog_suffix}{term_suffix}"
                )


                existing_closed = InstructorCourse.objects.filter(
                    instructor=profile,
                    frontend_id=frontend_id,
                    status='closed'
                ).exists()


                if existing_closed:
                    continue

                already_exists = InstructorCourse.objects.filter(
                    instructor=profile,
                    code=course.code,
                    program=program
                ).exclude(frontend_id=frontend_id).exclude(is_historical=True).exists()


                if already_exists:
                    continue

                # Map catalogue subtype ('theory'/'lab') to InstructorCourse
                # course_type ('Theory'/'Lab'). Fallback to 'Theory' if unset.
                subtype_map = {'lab': 'Lab', 'theory': 'Theory'}
                ic_course_type = subtype_map.get(
                    getattr(course, 'subtype', 'theory'), 'Theory'
                )

                obj, created = InstructorCourse.objects.get_or_create(
                    instructor=profile,
                    frontend_id=frontend_id,
                    defaults=dict(
                        code=course.code,
                        title=course.title,
                        course_type=ic_course_type,
                        department=course.department,
                        program=program,
                        credit_hours=course.credit_hours,
                        academic_year=term,
                        catalog_course=course,
                    )
                )

                # Backfill course_type on existing rows where it defaulted to
                # Theory but the catalogue says Lab (or vice-versa).
                if not created and obj.course_type != ic_course_type:
                    obj.course_type = ic_course_type
                    obj.save(update_fields=['course_type'])

                # Backfill catalog_course on rows created before this field
                # existed, so categories/units resolve for them too.
                if not created and obj.catalog_course_id is None:
                    obj.catalog_course = course
                    obj.save(update_fields=['catalog_course'])


            # Every course not handed in yet, whatever its term: an unfinished
            # course stays when a new term starts, and a submitted one goes
            # (see InstructorPastCoursesView).
            all_ics = InstructorCourse.objects.filter(
                instructor=profile, status='active', submitted_at__isnull=True, is_historical=False
            )

            qs = prefetch_instructor_course(all_ics.order_by('created_at'))

            data = InstructorCourseSerializer(qs, many=True).data


            return Response(data)

        except Exception:
            traceback.print_exc()
            raise

    def post(self, request, frontend_id=None):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response(
                {'error': 'Instructor profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )
        return self._save_courses(request.data.get('courses', []), profile, _teacher_lock_message)

    def _save_courses(self, courses_data, profile, lock_for):
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

            # Submitted and closed courses are read-only — reject any edit attempt
            existing = InstructorCourse.objects.filter(
                instructor=profile, frontend_id=frontend_id
            ).first()
            lock = lock_for(existing) if existing else None
            if lock:
                errors.append({'index': idx, 'error': lock})
                continue

            # Refuse an older copy: if the course was saved after the version
            # this client loaded (e.g. from another tab or computer), writing
            # this payload would put older marks back over newer ones.
            sent_version = parse_datetime(str(c.get('updatedAt') or ''))
            if existing and sent_version:
                if timezone.is_naive(sent_version):
                    sent_version = timezone.make_aware(sent_version, datetime.timezone.utc)
                if existing.updated_at > sent_version:
                    errors.append({
                        'index': idx,
                        'stale': True,
                        'error': f'Course "{existing.code}" was changed in another tab or on another computer. Reload the page to get the latest marks before editing.'
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
                    # academic_year must NOT be overwritten if the incoming value is blank
                    # — the frontend may not always send it, but the value was set at
                    # assignment time and must be preserved to keep semester filtering correct.
                    upsert_defaults = dict(
                        code                    = c.get('code', ''),
                        title                   = c.get('title', ''),
                        course_type             = c.get('courseType', 'Theory'),
                        department              = department,
                        program                 = program,
                        credit_hours            = c.get('creditHours', 3),
                        clo_count               = c.get('cloCount', 4),
                        selected_grading_system = c.get('selectedGradingSystem', 'ready1'),
                    )
                    incoming_year = c.get('academicYear', '').strip()
                    if incoming_year:
                        upsert_defaults['academic_year'] = incoming_year

                    # Resolve (or create) the catalog Course row this offering
                    # teaches. MarksCategory/OBEQuestion hang off Course now
                    # (migration 0011), shared across every instructor/term
                    # teaching the same course — so we must upsert the catalog
                    # entry too, not just the InstructorCourse header.
                    catalog_course, _ = Course.objects.get_or_create(
                        code=upsert_defaults['code'],
                        department=department,
                        program=program,
                        defaults={
                            'title':        upsert_defaults['title'],
                            'credit_hours': upsert_defaults['credit_hours'],
                        }
                    )
                    upsert_defaults['catalog_course'] = catalog_course

                    course, _ = InstructorCourse.objects.update_or_create(
                        instructor=profile,
                        frontend_id=frontend_id,
                        defaults=upsert_defaults,
                    )

                    # ── Sync GradeScale ───────────────────────────────────────────────
                    # CRITICAL: the frontend never sends a plain number for 'percentage' —
                    # it always sends a range STRING like "88% - 100%" or "Below 60%"
                    # (see DEFAULT_CUSTOM_GRADES / parsePercentRange in InstructorDashboard.tsx).
                    # float("88% - 100%") raises ValueError, which was being silently
                    # swallowed below — meaning EVERY GradeScale row failed to save for
                    # EVERY course using custom grading, while grade_scale.all().delete()
                    # still ran first, leaving the course with an empty custom scale.
                    # _get_grade() then silently fell back to READY1_SCALE for every
                    # student — wrong grades computed with zero error shown anywhere.
                    custom_grading = c.get('customGradingSystem', [])
                    course.grade_scale.all().delete()
                    for order, entry in enumerate(custom_grading):
                        try:
                            pct_raw = str(entry.get('percentage', 0))
                            min_pct = _parse_percent_range_min(pct_raw)
                            GradeScale.objects.create(
                                course         = course,
                                grade          = entry.get('grade', ''),
                                min_percentage = min_pct,
                                points         = float(entry.get('points', 0)),
                                order          = order,
                            )
                        except (ValueError, TypeError):
                            pass

                    # ── Sync Categories + UnitItems ───────────────────────────────────
                    # NOTE: these hang off catalog_course (the shared Course catalog
                    # entry), not the per-instructor InstructorCourse row — see
                    # migration 0011. Editing categories here affects every
                    # instructor/term teaching this same catalog course, which
                    # matches the frontend's mental model of "the course's marking
                    # structure" (frontend still sends/reads categories/unitsData
                    # nested under the InstructorCourse object, unchanged).
                    incoming_categories = c.get('categories', [])
                    incoming_units_data = c.get('unitsData', {})
                    # Ignore malformed rows instead of raising KeyError (500).
                    incoming_categories = [
                        cat for cat in incoming_categories
                        if isinstance(cat, dict) and cat.get('name')
                    ]
                    incoming_cat_names  = [cat['name'] for cat in incoming_categories]

                    # DATA-LOSS GUARD: never infer deletion from absence.
                    #
                    # This block used to run
                    #     markscategories.exclude(name__in=incoming_cat_names).delete()
                    # which treats whatever the client sent as the complete
                    # authoritative set and hard-deletes the remainder. Three things
                    # made that destructive:
                    #   1. MarksCategory -> UnitItem -> StudentMark all CASCADE, so
                    #      deleting a category silently destroys entered student marks.
                    #   2. These rows hang off the SHARED catalog Course (migration
                    #      0011), so the blast radius is every instructor and every
                    #      term teaching this course code.
                    #   3. The frontend auto-saves on every state change, and filters
                    #      categories by courseType (THEORY_CATEGORY_NAMES vs
                    #      LAB_CATEGORY_NAMES). A course with the wrong/flipped type
                    #      sends the other type's list, wiping the real one with no
                    #      click and no error.
                    # An empty/missing 'categories' wiped the entire structure.
                    #
                    # Now: an omitted category is only removed when it holds no marks
                    # (safe cleanup of an unused structure). Anything carrying student
                    # marks is preserved and must be deleted deliberately.
                    if incoming_cat_names:
                        for stale_cat in catalog_course.markscategories.exclude(
                            name__in=incoming_cat_names
                        ):
                            has_marks = StudentMark.objects.filter(
                                unit_item__category=stale_cat
                            ).exists()
                            if not has_marks:
                                stale_cat.delete()

                    cat_obj_map  = {}   # cat_name -> MarksCategory instance
                    unit_obj_map = {}   # (cat_name, unit_no) -> UnitItem instance

                    for order, cat_data in enumerate(incoming_categories):
                        cat_name = cat_data['name']
                        cat_obj, _ = MarksCategory.objects.update_or_create(
                            course=catalog_course, name=cat_name,
                            defaults={
                                'percentage': cat_data.get('percentage', 0),
                                'units':      cat_data.get('units', 0),
                                'order':      order,
                            }
                        )
                        cat_obj_map[cat_name] = cat_obj

                        incoming_units = [
                            u for u in incoming_units_data.get(cat_name, [])
                            if isinstance(u, dict) and u.get('unitNo') is not None
                        ]
                        incoming_unit_nos = [u['unitNo'] for u in incoming_units]
                        # Same guard as above: UnitItem -> StudentMark CASCADEs, so an
                        # omitted unit is only dropped when it carries no marks.
                        if incoming_unit_nos:
                            for stale_unit in cat_obj.unit_items.exclude(
                                unit_no__in=incoming_unit_nos
                            ):
                                if not stale_unit.student_marks.exists():
                                    stale_unit.delete()

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
                    incoming_questions = [
                        q for q in c.get('obeQuestions', [])
                        if isinstance(q, dict) and q.get('id')
                    ]
                    incoming_q_ids     = [q['id'] for q in incoming_questions]
                    # Same data-loss guard as the categories block above:
                    # OBEQuestion -> OBEStudentMark CASCADEs, so an omitted question
                    # is only removed when no student has a mark recorded against it.
                    if incoming_q_ids:
                        for stale_q in course.obe_questions.exclude(
                            frontend_id__in=incoming_q_ids
                        ):
                            if not stale_q.student_marks.exists():
                                stale_q.delete()

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
                    # IMPORTANT: The instructor POST must NEVER delete students.
                    # Roster management (add/remove students) is the exclusive
                    # responsibility of the Dept Admin via POST /api/admin/enroll/.
                    #
                    # Why: the instructor's React state is loaded once on login.
                    # If a dept admin enrolls a new student AFTER the instructor
                    # logged in, the instructor's state won't include that student.
                    # If we delete-then-sync from instructor state, the newly
                    # enrolled student gets wiped from the DB on the next auto-save.
                    #
                    # Instructor can only: update names & marks for existing students,
                    # and add students that appear in their payload but aren't yet in DB
                    # (e.g. students they added locally before backend sync).
                    incoming_students = c.get('students', [])

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
                            # key = '{categoryName}-{unitNo}' (aggregated unit total) OR
                            # 'q-{categoryName}-{unitNo}-{questionId}' (per-question breakdown,
                            # sent alongside the aggregate for UI granularity — not a real
                            # unit mark, must be skipped here or the parse below silently
                            # misfires whenever categoryName itself contains a dash e.g. "Mid-Term").
                            if key.startswith('q-'):
                                continue
                            # Match against known (cat_name, unit_no) pairs instead of blindly
                            # splitting on the last dash — a category renamed to include a dash
                            # (e.g. "Class-Work") would otherwise silently drop that unit's marks
                            # with no error, since int(key[last_dash+1:]) would raise ValueError
                            # and get swallowed by the except clause below.
                            unit_obj = None
                            for (cat_name, unit_no), candidate in unit_obj_map.items():
                                if key == f"{cat_name}-{unit_no}":
                                    unit_obj = candidate
                                    break
                            if unit_obj:
                                incoming_unit_pks.add(unit_obj.pk)
                                mark_rows.append((unit_obj, score))

                        # Delete marks for units no longer in payload. Limited to
                        # units this payload sent: categories/units omitted from it
                        # are preserved by the guard above, and so are their marks.
                        student.marks.filter(
                            unit_item__in=[u.pk for u in unit_obj_map.values()]
                        ).exclude(unit_item__in=incoming_unit_pks).delete()

                        for unit_obj, score in mark_rows:
                            StudentMark.objects.update_or_create(
                                student=student, unit_item=unit_obj,
                                defaults={'score': score}
                            )

                        # ── Sync OBE Marks ────────────────────────────────────────────
                    # Accept both camelCase (legacy frontend) and snake_case (new standard)
                    incoming_obe_marks = c.get('obe_marks') or c.get('obeMarks') or {}
                    for reg_no, q_marks in incoming_obe_marks.items():
                        try:
                            student = CourseStudent.objects.get(course=course, reg_no=reg_no)
                        except CourseStudent.DoesNotExist:
                            continue
                        for q_frontend_id, score in q_marks.items():
                            q_obj = q_obj_map.get(q_frontend_id)
                            if q_obj and score is None:   # the teacher cleared this cell
                                OBEStudentMark.objects.filter(student=student, question=q_obj).delete()
                            elif q_obj:
                                OBEStudentMark.objects.update_or_create(
                                    student=student, question=q_obj,
                                    defaults={'score': score}
                                )

                    saved.append(course)
            except (KeyError, ValueError, TypeError, AttributeError, IntegrityError) as e:
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

    def delete(self, request, frontend_id=None):
        """
        DELETE /api/instructor/courses/<frontend_id>/
        Instructor removes one of their own courses (only if it has no
        students enrolled and no marks entered — if it does, dept admin
        must unassign the course instead, which preserves gradebook data).
        """
        if not frontend_id:
            return Response({'error': 'frontend_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_instructor_profile(request.user)
        if not profile:
            return Response({'error': 'Instructor profile not found'}, status=status.HTTP_403_FORBIDDEN)

        try:
            ic = InstructorCourse.objects.get(frontend_id=frontend_id, instructor=profile, is_historical=False)
        except InstructorCourse.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        if ic.status == 'closed' or ic.submitted_at:
            return Response(
                {'error': 'Cannot delete a submitted or finalized course.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Don't delete courses that have real marks data — preserves
        # gradebook integrity even if the instructor wants to remove it.
        if ic.students.exists():
            return Response(
                {'error': 'Cannot delete a course with enrolled students. Ask your dept admin to unassign it instead.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ic.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Instructor Profile ────────────────────────────────────────────────────────
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

                # Auto-create or update the login User + Student profile.
                # Wrapped in atomic so that if StudentProfile.update_or_create
                # fails after User.create succeeds, the orphaned User is rolled
                # back automatically — otherwise the email is permanently taken
                # and every retry attempt errors with "account already exists".
                from .models import Student as StudentProfile
                _email_conflict = False
                with transaction.atomic():
                    user_obj = User.objects.filter(email__iexact=email).first()
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
                            password=make_password(django_settings.DEFAULT_TEMP_PASSWORD),
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
                            _email_conflict = True
                        else:
                            # Update name if changed
                            name_parts = name.split()
                            user_obj.first_name = name_parts[0] if name_parts else ''
                            user_obj.last_name  = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                            user_obj.save()

                    if not _email_conflict:
                        # Link Student profile (reg_no is the bridge)
                        StudentProfile.objects.update_or_create(
                            user=user_obj,
                            defaults=dict(reg_no=reg_no, department=department, program=program)
                        )

                if _email_conflict:
                    continue

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

        # AdmissionStudent has no FK to User — they're linked only by the
        # reg_no string. Without this extra step, deleting the AdmissionStudent
        # row leaves the User account and Student login profile intact, meaning
        # the student can still log in after being "deleted" from the registry.
        # Deleting the User cascades to Student automatically (Student.user is
        # OneToOneField with on_delete=CASCADE), so we only need to delete User.
        from .models import Student as StudentProfile
        linked = StudentProfile.objects.filter(reg_no=student.reg_no).select_related('user').first()
        if linked:
            linked.user.delete()  # cascades → Student profile deleted automatically

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
        import traceback


        admin_dept = get_admin_department(request.user)

        if not admin_dept:
            return Response(
                {'error': 'Admin profile not found'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            qs = CourseAssignment.objects.select_related(
                'instructor__user',
                'course',
                'program'
            ).filter(
                course__department=admin_dept
            )


            data = []

            # Each assignment's gradebook is the InstructorCourse whose
            # frontend_id is built exactly as in post() below. Return that id,
            # the term, the open/closed state and the enrolled students, so the
            # admin screen can enroll into the REAL course after a re-login.
            # Without these the frontend had to guess the id (defaulting the
            # term to Fall-2024 and the program to the catalog's), which missed
            # the real course, got a 404, and "self-healed" by creating a
            # bogus duplicate assignment and enrolling students into THAT —
            # so enrollments appeared to vanish after logout.
            assignments = list(qs)
            def _frontend_id(a):
                prog_suffix = a.program.code.lower() if a.program else 'all'
                term_suffix = (
                    f'-{a.academic_year.lower().replace(" ", "")}'
                    if a.academic_year else ''
                )
                return (
                    f'course-assigned-{a.course.code}-'
                    f'{a.instructor.employee_id}-{prog_suffix}{term_suffix}'
                )

            ids = [_frontend_id(a) for a in assignments]
            ic_by_id = {
                ic.frontend_id.lower(): ic
                for ic in InstructorCourse.objects.filter(
                    frontend_id__in=ids
                ).prefetch_related('students')
            }

            for a, fid in zip(assignments, ids):
                ic = ic_by_id.get(fid.lower())
                data.append({
                    'id': fid,
                    'courseId': fid,
                    'teacherId': a.instructor.employee_id,
                    'teacherName': a.instructor.user.get_full_name() or a.instructor.user.username,
                    'courseCode': a.course.code,
                    'courseTitle': a.course.title,
                    'programId': a.program.code.lower() if a.program else None,
                    'programName': a.program.name if a.program else None,
                    'academicYear': a.academic_year or '',
                    'status': ic.status if ic else 'active',
                    'submittedAt': ic.submitted_at if ic else None,
                    'submissionWarnings': ic.submission_warnings if ic else [],
                    'students': [
                        {'regNo': st.reg_no, 'name': st.name}
                        for st in (ic.students.all() if ic else [])
                    ],
                })

            return Response(data)

        except Exception as e:
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    def post(self, request):
        import traceback

        try:
            admin_dept = get_admin_department(request.user)
            if not admin_dept:
                return Response(
                    {'error': 'Admin profile not found'},
                    status=status.HTTP_403_FORBIDDEN
                )

            data = request.data
            teacher_id = data.get('teacherId', '').strip()
            course_code = data.get('courseCode', '').strip().upper()
            program_id = data.get('programId', '').strip()
            academic_year = data.get('academicYear', '').strip()


            if not teacher_id or not course_code:
                return Response(
                    {'error': 'teacherId and courseCode are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            instructor = InstructorProfile.objects.get(
                employee_id=teacher_id
            )

            program = None
            if program_id:
                program = Program.objects.get(
                    code__iexact=program_id
                )

            if program_id:
                course = Course.objects.get(
                    code__iexact=course_code,
                    program__code__iexact=program_id
                )
            else:
                course = Course.objects.filter(code__iexact=course_code).first()
                if not course:
                    return Response(
                        {'error': f'Course "{course_code}" not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            if course.department_id != admin_dept.id:
                return Response(
                    {
                        'error': f'Course "{course_code}" does not belong to your department ({admin_dept.name}).'
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            dept_admin = request.user.dept_admin_profile

            assignment, created = CourseAssignment.objects.get_or_create(
                instructor=instructor,
                course=course,
                program=program,
                academic_year=academic_year,
                defaults={
                    'assigned_by': dept_admin
                }
            )

            prog_suffix = program.code.lower() if program else 'all'
            term_suffix = (
                f'-{academic_year.lower().replace(" ", "")}'
                if academic_year else ''
            )

            frontend_id = (
                f'course-assigned-{course.code}-'
                f'{instructor.employee_id}-{prog_suffix}{term_suffix}'
            )

            _subtype_map = {'lab': 'Lab', 'theory': 'Theory'}
            _ic_course_type = _subtype_map.get(
                getattr(course, 'subtype', 'theory'), 'Theory'
            )

            InstructorCourse.objects.get_or_create(
                instructor=instructor,
                frontend_id=frontend_id,
                defaults=dict(
                    code=course.code,
                    title=course.title,
                    course_type=_ic_course_type,
                    department=course.department,
                    program=program,
                    credit_hours=course.credit_hours or 3,
                    clo_count=0,
                    selected_grading_system='ready1',
                    semester='',
                    academic_year=academic_year,
                    catalog_course=course,
                )
            )

            return Response(
                {
                    'teacherId': assignment.instructor.employee_id,
                    'courseCode': assignment.course.code,
                    'programId': assignment.program.code.lower() if assignment.program else None,
                    'academicYear': academic_year,
                    'courseId': frontend_id,
                    'id': frontend_id,
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )

        except (InstructorProfile.DoesNotExist, Program.DoesNotExist, Course.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
        if academic_year:
            qs = qs.filter(academic_year__iexact=academic_year)
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
    # Was IsAuthenticated — any logged-in user, including students, could
    # pull every instructor's name/email/employeeId university-wide, despite
    # the docstring saying this is a dept_admin tool. Checked the frontend:
    # only DeptAdminDashboard.tsx calls this endpoint, so tightening it here
    # doesn't remove any legitimate access. Also modest defense-in-depth for
    # the employee_id exposure specifically, since employee_id feeds directly
    # into InstructorCourse.frontend_id (see the CLO authorization fix).
    permission_classes = [IsDeptAdmin]

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

        # SECURITY FIX (Zeeshan): previously, when programId was provided, this
        # skipped department scoping — any dept_admin could read another dept's
        # semester plan by guessing a programId. Reproduced before fixing.
        # Always scope to own department regardless of query params supplied.
        qs = SemesterPlan.objects.select_related('program').filter(
            program__department=dept
        )
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
        "categories":  [
            {
                "name":       "Assignments",
                "percentage": 10,     ← category weight in total grade (0-100)
                "units":      2       ← number of units in this category
            }
        ],
        "unitsData": {
            "Assignments": [
                {
                    "unitNo":     1,
                    "totalMarks": 10,   ← max marks for this unit
                    "weightage":  50,   ← unit weight within category (0-100, sums to 100 per cat)
                    "passing":    5,
                    "obtainedMarks": 8  ← student's raw score
                }
            ]
        },
        "student_marks": { "Assignments-1": 8, "Assignments-2": 5 },  ← unit-level scores (snake_case)
        "weightedMarks": {
            "Assignments-1": {
                "obtained":     8,     ← raw score
                "totalMarks":   10,    ← max for this unit
                "weightage":    50,    ← unit weight within category
                "catPercentage":10,    ← category weight in total
                "contribution": 4.0    ← actual contribution to final grade
                                       ← formula: (8/10) * (50/100) * 10 = 4.0%
            }
        },
        "totalPercentage": 88.0,       ← backend-calculated final grade (USE THIS!)
        "grade":           "A-",       ← backend-calculated letter grade (USE THIS!)
        "gradePoints":     3.67,       ← backend-calculated GPA points (USE THIS!)
        "obeQuestions": [
            {
                "id":         "1784046977475_1",
                "questionName": "Question 1",
                "maxMarks":   5,
                "categoryName": "Assignments",
                "unitNo":     1,
                "mappedCLOs": ["CLO-1"]
            }
        ],
        "obe_marks": {
            "1784046977475_1": 5.0     ← student's score for this specific question
        },
        "cloAttainments": [
            {
                "code":       "CLO-1",
                "percentage": 100.0,   ← (student_score / max_score) * 100
                "attained":   true     ← percentage >= 50%
            }
        ]
    }

    HOW MARKS WORK:
    ─────────────────────────────────────────────────────────────
    There are TWO types of marks in the system:

    1. StudentMark (Regular Marks) — stored per unit
       - Key: "{CategoryName}-{unitNo}" e.g. "Assignments-1"
       - Value: raw score e.g. 8.0
       - Total: unit.total_marks e.g. 10.0
       - These are what show in the marks grid

    2. OBEStudentMark (OBE Marks) — stored per question
       - Key: question.frontend_id e.g. "1784046977475_1"
       - Value: raw score e.g. 5.0
       - Total: question.max_marks e.g. 5.0
       - These are used for CLO attainment calculation

    HOW TOTAL PERCENTAGE IS CALCULATED:
    ─────────────────────────────────────────────────────────────
    For each StudentMark:
        contribution = (score / unit.total_marks)    ← 0-1 scale (how well student did)
                     * (unit.weightage / 100)         ← 0-1 scale (unit's share of category)
                     * category.percentage            ← 0-100 scale (category's share of total)

    Example:
        Assignments Unit 1: (8/10) * (50/100) * 10 = 4.0%
        Assignments Unit 2: (5/5)  * (50/100) * 10 = 5.0%
        Quizzes Unit 1:     (4/5)  * (100/100) * 10 = 8.0%
        Mid Term Unit 1:    (7/10) * (100/100) * 30 = 21.0%
        Final Unit 1:       (5/5)  * (100/100) * 50 = 50.0%
        ──────────────────────────────────────────────────────
        TOTAL = 88.0%  → Grade: A-

    !! DO NOT RECALCULATE THIS ON FRONTEND !!
    Use totalPercentage, grade, and gradePoints from this response directly.

    HOW CLO ATTAINMENT IS CALCULATED:
    ─────────────────────────────────────────────────────────────
    For each CLO, find all questions mapped to it:
        CLO-1 questions: [Q1(max=5, score=5)]
        CLO-1 attainment = (5/5) * 100 = 100%

        CLO-2 questions: [Q2(max=5, score=3), Q1-unit2(max=5, score=5), Q2-mid(max=5, score=3), Q1-final(max=5, score=5)]
        CLO-2 attainment = (3+5+3+5)/(5+5+5+5) * 100 = 16/20 * 100 = 80%

    !! DO NOT RECALCULATE CLOs ON FRONTEND !!
    Use cloAttainments from /api/reports/student-summary/ directly.

    HOW MARKS DISPLAY SHOULD WORK ON FRONTEND:
    ─────────────────────────────────────────────────────────────
    The student dashboard "Assessment Marks Breakdown" section should show:
        Category    | Obtained | Total | Weight%
        Assignments |    9.0   |  10   |  10%     ← use weightedMarks contributions sum
        Quizzes     |    8.0   |  10   |  10%
        Mid Term    |   21.0   |  30   |  30%
        Final       |   50.0   |  50   |  50%
        ─────────────────────────────────────────
        TOTAL       |   88.0   | 100   | 100%

    The "obtained" here is the WEIGHTED contribution, NOT the raw score.
    "Assignments obtained = 9.0" means 9 out of 10 possible percentage points.

    Requires: User.role == 'student'
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'student':
            return Response(
                {'error': 'Only students can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            reg_no = request.user.student_profile.reg_no
        except Exception:
            reg_no = request.user.email.split('@')[0]

        enrollments = CourseStudent.objects.filter(
            reg_no__iexact=reg_no
        ).exclude(course__is_historical=True, course__status='active').select_related(
            'course__department',
            'course__program',
            'course__instructor',
            'course__catalog_course',
        ).prefetch_related(
            'marks__unit_item__category',
            'course__catalog_course__markscategories__unit_items',
            'course__obe_questions',
            'course__clos__mapped_ga',
            'obe_marks__question',
        )

        result = []
        plan_cache = {}
        for enrollment in enrollments:
            ic = enrollment.course

            # ── 1. Raw marks dict (legacy format, kept for backward compat) ──
            student_marks = {
                f"{m.unit_item.category.name}-{m.unit_item.unit_no}": m.score
                for m in enrollment.marks.all()
            }

            # ── 2-4. Totals, units, grade, breakdown ─────────────────────────
            # All from _sheet_course_total — the same calculation as the
            # instructor's mark sheet. This used to be a separate formula (unit
            # weightage, unit-level marks only), so the student could be shown a
            # different grade from the sheet. Response field names are unchanged.
            sheet = _sheet_course_total(enrollment)
            exact_total = sheet['total']
            total_percentage = round(exact_total, 2)

            # Grade the exact total, as the sheet does.
            grade_letter, grade_points = _get_grade(exact_total, ic)

            weighted_marks = {}
            units_data = {}
            for (cat_name, unit_no), info in sheet['units'].items():
                ui = info['unitItem']
                cat_pct = sheet['categories'][cat_name]['total']
                key = f"{cat_name}-{unit_no}"
                has_unit_mark = ui is not None and key in student_marks
                if has_unit_mark or info['obtained'] > 0:
                    weighted_marks[key] = {
                        'obtained':      info['obtained'],
                        'totalMarks':    info['totalMarks'],
                        'weightage':     ui.weightage if ui else 0,
                        'catPercentage': cat_pct,
                        'contribution':  round(info['contribution'], 4),
                    }
                # EVERY unit, with its questions. This used to list only units
                # that already had a mark, and no questions, so the student
                # dashboard recomputed from partial data (a missing unit
                # defaulted to "out of 10").
                units_data.setdefault(cat_name, []).append({
                    'unitNo':        unit_no,
                    'totalMarks':    ui.total_marks if ui else 10,
                    'weightage':     ui.weightage if ui else 0,
                    'passing':       ui.passing if ui else 0,
                    'obtainedMarks': info['obtained'],
                    'contribution':  round(info['contribution'], 4),
                    'questions': [
                        {'id': q.frontend_id, 'name': q.question_name,
                         'maxMarks': q.max_marks, 'mappedCLOs': q.mapped_clos or []}
                        for q in info['questions']
                    ],
                })

            category_breakdown = {
                name: {'obtained': round(c['obtained'], 2), 'total': c['total'], 'weight': c['total']}
                for name, c in sheet['categories'].items()
            }

            # ── 5. OBE Questions ─────────────────────────────────────────────
            all_obe_questions = list(ic.obe_questions.all())
            obe_questions = [
                {
                    'id':           q.frontend_id,
                    'questionName': q.question_name,
                    'maxMarks':     q.max_marks,
                    'categoryName': q.category_name,
                    'unitNo':       q.unit_no,
                    'mappedCLOs':   q.mapped_clos or [],
                }
                for q in all_obe_questions
            ]

            # Build a lookup: (categoryName, unitNo) → set of CLO codes
            # so we can attach mappedCLOs to each unitsData entry
            unit_clo_map = {}
            for q in all_obe_questions:
                key = (q.category_name, q.unit_no)
                for clo in (q.mapped_clos or []):
                    unit_clo_map.setdefault(key, set()).add(clo)

            # Enrich unitsData entries with mappedCLOs
            for cat_name, unit_list in units_data.items():
                for unit_entry in unit_list:
                    key = (cat_name, unit_entry['unitNo'])
                    unit_entry['mappedCLOs'] = sorted(unit_clo_map.get(key, []))

            # ── 6. OBE Marks (student's scores per question) ─────────────────
            obe_marks = {
                om.question.frontend_id: om.score
                for om in enrollment.obe_marks.all()
                if om.question
            }

            # ── 7. CLO Attainments with GA mapping and description ───────────
            questions_qs = all_obe_questions
            clo_pcts     = _clo_attainments_for_student(enrollment, questions_qs)

            # Build CLO record lookup: code → { ga, description }
            clo_meta = {
                clo.code: {
                    'description': clo.description or '',
                    'mappedGA': {
                        'gaId':    clo.mapped_ga.ga_id,
                        'gaTitle': clo.mapped_ga.name,
                    } if clo.mapped_ga else None,
                }
                for clo in ic.clos.select_related('mapped_ga').all()
            }

            clo_attainments = [
                {
                    'code':        clo,
                    'description': clo_meta.get(clo, {}).get('description', ''),
                    'percentage':  pct,
                    'attained':    pct >= ATTAINMENT_THRESHOLD,   # bool (backwards compat)
                    'status':      'Attained' if pct >= ATTAINMENT_THRESHOLD else 'Not Attained',
                    'mappedGA':    clo_meta.get(clo, {}).get('mappedGA'),  # { gaId, gaTitle } or None
                }
                for clo, pct in sorted(clo_pcts.items())
            ]

            # ── 8. Categories list ───────────────────────────────────────────
            categories = [
                {'name': c.name, 'percentage': c.percentage, 'units': c.units}
                for c in (
                    ic.catalog_course.markscategories.order_by('order').all()
                    if ic.catalog_course_id else []
                )
            ]

            # grade_letter is always a string from _get_grade (e.g. 'F' when 0%).
            # Return null instead of 'F' when the student genuinely has no marks,
            # so the frontend can distinguish "no data yet" from a real F grade.
            # Per-question (OBE) marks count too — a student marked only at
            # question level used to be reported as having no marks at all.
            has_any_marks = bool(student_marks) or enrollment.obe_marks.exists()
            final_grade   = grade_letter if has_any_marks else None
            final_points  = grade_points if has_any_marks else None
            final_pct     = total_percentage if has_any_marks else None
            if enrollment.result_status == 'withdrawn':
                final_grade, final_points = 'W', 0.0

            result.append({
                'id':                ic.frontend_id,
                'code':              ic.code,
                # Plain course title. The program code used to be appended
                # ("Programming Fundamentals (BSCS)") on every student screen and
                # transcript; the program is shown once, in the header, instead.
                'title':             ic.title,
                'programId':         ic.program.code.lower() if ic.program else None,
                'academicYear':      ic.academic_year,
                'semester':          ic.semester or _plan_semester(ic.program_id, ic.code, plan_cache),
                'creditHours':       ic.credit_hours,
                'is_finalized':      ic.is_locked,  # True once course is closed/finalized
                'categories':        categories,

                # ── Standardized mark keys (snake_case) ──────────────────────
                'student_marks':     student_marks,      # { "Cat-Unit": score }
                'obe_marks':         obe_marks,           # { questionId: score } per student

                # ── Backend-calculated results (USE THESE, never recalculate) ─
                'weightedMarks':     weighted_marks,     # full per-unit context
                'unitsData':         units_data,         # grouped by category
                'categoryBreakdown': category_breakdown, # for display table
                'totalPercentage':   final_pct,          # Float or null (never recalculate!)
                'grade':             final_grade,         # String or null (never "-")
                'gradePoints':       final_points,        # Float or null
                'obeQuestions':      obe_questions,       # questions with CLO mappings
                'cloAttainments':    clo_attainments,    # CLO % (never recalculate!)
                'gaAttainments':     _student_ga_attainments(enrollment),  # GA by questions passed
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

# ── Grading Scales ────────────────────────────────────────────────────────────
# These MUST match exactly what the frontend shows in the grading system UI.
# If these don't match, students see wrong grades.

# System 1: Iqra Standard (ready1) — 6-tier
# Frontend shows: A=88-100, B+=81-87, B=74-80, C+=67-73, C=60-66, F=Below 60
READY1_SCALE = [
    ('A',   88.0, 4.00),
    ('B+',  81.0, 3.50),
    ('B',   74.0, 3.00),
    ('C+',  67.0, 2.50),
    ('C',   60.0, 2.00),
    ('F',    0.0, 0.00),
]

# System 2: Plus/Minus (ready2) — 10-tier
# Frontend shows: A+=90-100, A=85-89, A-=80-84, B+=75-79, B=70-74,
#                 B-=65-69, C+=60-64, C=55-59, D=50-54, F=Below 50
READY2_SCALE = [
    ('A+',  90.0, 4.00),
    ('A',   85.0, 4.00),
    ('A-',  80.0, 3.70),
    ('B+',  75.0, 3.30),
    ('B',   70.0, 3.00),
    ('B-',  65.0, 2.70),
    ('C+',  60.0, 2.30),
    ('C',   55.0, 2.00),
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


def _sheet_course_total(course_student) -> dict:
    """
    A student's weighted course total, computed EXACTLY as the instructor's
    official mark sheet computes it (frontend utils/grading.ts,
    computeCourseAggregate). The two are kept line-for-line equivalent.

    The backend used to use a different formula — each unit weighted by its
    Unit Weightage %, counting only unit-level StudentMark rows and ignoring
    per-question OBE marks — so the grade a student saw (and the grade written
    to the transcript at finalisation) could differ from the mark sheet the
    instructor signed: e.g. "B" on the sheet, "C+" for the student.

    Per category (weight > 0, units > 0), over units 1..category.units:
      - unit with questions: each question adds its maxMarks to the maximum;
        obtained = the question's mark if it is > 0, else (single-question unit)
        the unit-level mark, else the question's mark or 0
      - unit without questions: maximum = unit total_marks (10 if the unit row
        doesn't exist); obtained = the unit-level mark
      contribution = obtained / maximum * category percentage
    total = sum of contributions (0-100). Not rounded — round only for display,
    so grading uses the exact value as the sheet does.

    Returns {'total': float,
             'categories': {name: {'obtained': float, 'total': percentage}},
             'units': {(cat_name, unit_no): {'totalMarks', 'obtained', 'contribution',
                                              'unitItem', 'questions'}}}
    """
    ic = course_student.course
    result = {'total': 0.0, 'categories': {}, 'units': {}}
    if not ic.catalog_course_id:
        return result

    unit_marks = {m.unit_item_id: m.score for m in course_student.marks.all()}
    question_marks = {om.question_id: om.score for om in course_student.obe_marks.all()}

    # MarksCategory.Meta.ordering is ['order']; plain .all() keeps that order
    # and, unlike .order_by(), can use SHEET_TOTAL_PREFETCH.
    for cat in ic.catalog_course.markscategories.all():
        if not (cat.percentage > 0):
            continue
        max_sum = 0.0
        obtained_sum = 0.0
        per_unit = []
        if cat.units > 0:
            units_by_no = {ui.unit_no: ui for ui in cat.unit_items.all()}
            for u in range(1, cat.units + 1):
                ui = units_by_no.get(u)
                # Only THIS offering's questions. Units hang off the shared catalog
                # course, so a course taught in several terms/sections has every
                # offering's questions on the same unit; counting the others would
                # add their marks to this student's maximum (totals roughly halved).
                questions = sorted(
                    (q for q in ui.questions.all() if q.course_id == ic.id),
                    key=lambda q: (q.order, q.id),
                ) if ui else []
                unit_max = 0.0
                unit_got = 0.0
                if questions:
                    for q in questions:
                        unit_max += q.max_marks or 0
                        val = question_marks.get(q.id)
                        if val is not None and float(val) > 0:
                            unit_got += float(val)
                        elif len(questions) == 1:
                            unit_got += float(unit_marks.get(ui.id, 0) or 0)
                        else:
                            unit_got += float(val or 0)
                else:
                    unit_max += ui.total_marks if ui else 10
                    unit_got += float(unit_marks.get(ui.id, 0) or 0) if ui else 0.0
                max_sum += unit_max
                obtained_sum += unit_got
                per_unit.append((u, ui, unit_max, unit_got, questions))

        contribution = (obtained_sum / max_sum) * cat.percentage if max_sum > 0 else 0.0
        result['total'] += contribution
        result['categories'][cat.name] = {'obtained': contribution, 'total': cat.percentage}
        for u, ui, unit_max, unit_got, questions in per_unit:
            result['units'][(cat.name, u)] = {
                'totalMarks':   unit_max,
                'obtained':     unit_got,
                # this unit's share of the category contribution; sums to it exactly
                'contribution': (unit_got / max_sum) * cat.percentage if max_sum > 0 else 0.0,
                'unitItem':     ui,
                'questions':    questions,
            }
    return result


# Everything _sheet_course_total reads, for an InstructorCourse queryset. Without
# it every student re-queries their marks and the course's categories/units/
# questions — tens of thousands of queries per program report.
SHEET_TOTAL_PREFETCH = (
    'students__marks',
    'students__obe_marks',
    'catalog_course__markscategories__unit_items__questions',
)


def _student_total_percentage(course_student) -> float:
    """
    Weighted total percentage — the mark sheet's calculation, rounded to 2dp
    for display and averaging. Grade from _sheet_course_total(...)['total']
    instead, so a total like 73.996 isn't rounded up into the next grade.
    """
    return round(_sheet_course_total(course_student)['total'], 2)


def _clo_attainments_for_student(course_student, questions_qs):
    """Returns dict: { 'CLO-1': percentage_float, ... }"""
    obe_marks = {m.question_id: m.score for m in course_student.obe_marks.all()}
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

        # A course's score is the percentage of its students who attain the GA
        # (by questions passed); the GA's result is the average of its course
        # scores; the KPI is the share of mapped courses that attain it.
        best, titles = _course_ga_best(_program_offerings(program))
        ga_courses = _direct_ga_courses(best, titles)
        program_reg_nos = {reg for per_ga in best.values() for per_student in per_ga.values() for reg in per_student}

        attributes = []
        for ga in gas:
            contributing = ga_courses.get(ga.ga_id, [])
            summary = _direct_ga_summary(contributing)
            attributes.append({
                'id':                  ga.ga_id,
                'title':               ga.name,
                'description':         ga.description,
                **summary,
                'attainmentStatus':    'Passed' if summary['kpiMet'] else 'Failed',
                'contributingCourses': contributing,
            })

        return Response({
            'programId':          program.code.lower(),
            'programName':        program.name,
            'programCode':        program.code.upper(),
            'departmentName':     program.department.name,
            'studentCount':       len(program_reg_nos),
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'attributes':         attributes,
        })


# ── 1b. Program GA Attainment, broken down by curriculum semester ────────────

class ProgramGAAttainmentBySemesterView(APIView):
    """
    GET /api/reports/program-ga-attainment-by-semester/?programId=bscs

    Same computation as ProgramGAAttainmentView (questions passed via
    question -> CLO -> GA), but grouped by curriculum semester (1st..8th)
    instead of flattened across the whole program. "Semester" here means the
    SemesterPlan curriculum slot a course belongs to (e.g. CMC111 is a
    1st-semester course) — NOT InstructorCourse.academic_year, which is
    the calendar term (e.g. "Fall-2026") a particular offering ran in.
    A course can be taught across many academic_years; this view pools
    every InstructorCourse offering of that course together, same as
    ProgramGAAttainmentView already does.

    Only semesters with a SemesterPlan actually configured for this
    program are included — dept_admin sets these up via
    POST /api/admin/semester-plans/.

    Response (chart-ready: X-axis = semester, grouped bars = GA):
    {
      "programId": "bscs",
      "programName": "...",
      "attainmentThreshold": 50.0,
      "semesters": [
        {
          "semester": "1st",
          "courseCodes": ["CMC111", "GER141"],
          "attributes": [
            { "id": "GA-1", "title": "...", "averageAttainment": 72.5, "contributingCoursesCount": 2, "attainmentStatus": "Passed" }
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

        best, titles = _course_ga_best(_program_offerings(program))

        semester_plans = SemesterPlan.objects.filter(program=program)
        # Preserve curriculum order (1st..8th), only including configured semesters.
        semester_order = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th']
        plans_by_semester = {sp.semester: sp.course_codes for sp in semester_plans}

        semesters_out = []
        for sem in semester_order:
            if sem not in plans_by_semester:
                continue
            ga_courses = _direct_ga_courses(best, titles, codes=set(plans_by_semester[sem]))

            attributes = []
            for ga in gas:
                summary = _direct_ga_summary(ga_courses.get(ga.ga_id, []))
                attributes.append({
                    'id':                       ga.ga_id,
                    'title':                    ga.name,
                    **summary,
                    'attainmentStatus':         'Passed' if summary['kpiMet'] else 'Failed',
                })

            semesters_out.append({
                'semester':    sem,
                'courseCodes': plans_by_semester[sem],
                'attributes':  attributes,
            })

        return Response({
            'programId':           program.code.lower(),
            'programName':         program.name,
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'semesters':           semesters_out,
        })


# ── 1c. Batch GA Attainment ───────────────────────────────────────────────────

class BatchGAAttainmentView(APIView):
    """
    GET /api/reports/batch-ga-attainment/?batch=sp23&departmentId=computing[&programId=bscs]

    GA attainment for one admitted batch/cohort (e.g. all SP23 students),
    identified by the batch code embedded in AdmissionStudent.reg_no
    (e.g. "SP23-BSCS-014" -> batch "sp23"). Same questions-passed
    computation as ProgramGAAttainmentView, but filtered to students in
    this batch instead of grouped by program.

    programId is optional — omit it to see the batch across every program
    in the department (matches "all sp23 students" as literally requested,
    not just one program's sp23 cohort).

    Response (chart-ready: one bar per GA):
    {
      "batch": "sp23",
      "departmentId": "computing",
      "studentCount": 42,
      "attainmentThreshold": 50.0,
      "attributes": [
        { "id": "GA-1", "title": "...", "averageAttainment": 68.4, "assessedCount": 40, "passedCount": 27, "attainmentStatus": "Passed" }
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        batch      = request.query_params.get('batch', '').strip().lower()
        dept_id    = request.query_params.get('departmentId', '').strip()
        program_id = request.query_params.get('programId', '').strip()

        if not batch:
            return Response({'error': 'batch is required (e.g. "sp23")'}, status=status.HTTP_400_BAD_REQUEST)
        if not dept_id:
            return Response({'error': 'departmentId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({'error': f'Department "{dept_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        program = None
        if program_id:
            try:
                program = Program.objects.get(code__iexact=program_id)
            except Program.DoesNotExist:
                return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        # The batch code is a "-"-separated segment of reg_no. Two layouts are
        # in use: "<BATCH>-<PROGRAM>-<NUM>" (e.g. "SP23-BSCS-014") and the
        # university format "<CAMPUS>-<BATCH>-<NUM>" (e.g. "052-SP23-22144").
        # A batch at the end ("22144-SP23") counts too.
        # A plain startswith only handled the first, so the second matched zero
        # students even though the frontend's batch picker offered "SP23".
        students_qs = AdmissionStudent.objects.filter(
            models.Q(reg_no__istartswith=batch) | models.Q(reg_no__icontains=f'-{batch}-') |
            models.Q(reg_no__iendswith=f'-{batch}'),
            department=department,
        )
        if program:
            students_qs = students_qs.filter(program=program)
        # Uppercase-normalized set for comparison against CourseStudent.reg_no
        # below — CourseStudent.reg_no is free-text (instructor-entered or
        # Excel-imported, no FK to AdmissionStudent), so casing can differ.
        # Matches the reg_no__iexact / .upper() normalization convention
        # already used everywhere else in this file for the same
        # AdmissionStudent <-> CourseStudent cross-reference.
        reg_nos = set(r.upper() for r in students_qs.values_list('reg_no', flat=True))

        if not reg_nos:
            return Response({
                'batch': batch, 'departmentId': dept_id, 'studentCount': 0,
                'attainmentThreshold': ATTAINMENT_THRESHOLD, 'attributes': [], 'students': [],
            })

        gas_qs = GraduateAttribute.objects.filter(department=department)
        if program:
            gas_qs = gas_qs.filter(models.Q(program__isnull=True) | models.Q(program=program))
        gas = gas_qs.order_by('ga_id')

        # Pull every InstructorCourse in this department (optionally scoped
        # to one program) and score this batch's students by questions passed.
        ic_qs = _report_offerings(InstructorCourse.objects.filter(department=department))
        if program:
            ic_qs = ic_qs.filter(program=program)
        ic_qs = ic_qs.select_related('catalog_course').prefetch_related(*GA_QUESTION_PREFETCH)

        # reg_no -> ga_id -> {course code: percent}, for the framework's student rule.
        best, _titles = _course_ga_best(ic_qs, reg_nos=reg_nos)
        student_ga = {}
        for code, per_ga in best.items():
            for g, per_student in per_ga.items():
                for reg, pct in per_student.items():
                    student_ga.setdefault(reg, {}).setdefault(g, {})[code] = pct

        ga_overall = {}   # ga_id -> [each assessed student's overall result]
        students_data = []
        for adm in students_qs.select_related('program').order_by('reg_no'):
            per_ga = {g: _student_overall_ga(courses) for g, courses in student_ga.get(adm.reg_no.upper(), {}).items()}
            for g, overall in per_ga.items():
                ga_overall.setdefault(g, []).append(overall)
            students_data.append({
                'regNo':       adm.reg_no,
                'name':        adm.name,
                'programCode': adm.program.code.upper() if adm.program else '',
                'programName': adm.program.name if adm.program else '',
                'gaScores':    {ga.ga_id: per_ga[ga.ga_id]['percent'] if ga.ga_id in per_ga else None for ga in gas},
                'gaAttained':  {ga.ga_id: per_ga[ga.ga_id]['attained'] if ga.ga_id in per_ga else None for ga in gas},
            })

        attributes = []
        for ga in gas:
            overall = ga_overall.get(ga.ga_id, [])
            assessed_count = len(overall)
            passed_count   = sum(1 for o in overall if o['attained'])
            avg_attainment = round(sum(o['percent'] for o in overall) / assessed_count, 2) if assessed_count > 0 else 0.0
            attributes.append({
                'id':                ga.ga_id,
                'title':             ga.name,
                'averageAttainment': avg_attainment,
                'assessedCount':     assessed_count,
                'passedCount':       passed_count,
                'attainmentStatus':  'Passed' if avg_attainment >= ATTAINMENT_THRESHOLD else 'Failed',
            })

        return Response({
            'batch':               batch,
            'departmentId':        dept_id,
            'programId':           program.code.lower() if program else None,
            'programName':         program.name if program else None,
            'departmentName':      department.name,
            'studentCount':        len(reg_nos),
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'attributes':          attributes,
            'students':            students_data,
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

        # SECURITY: force student's own regNo — any logged-in student could
        # read another student's GA attainment by passing a different regNo.
        # regNo follows a predictable pattern (FA22-BSCS-0012).
        if request.user.role == 'student':
            try:
                reg_no = request.user.student_profile.reg_no
            except Exception:
                return Response(
                    {'error': 'Student profile not found'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif not reg_no:
            return Response({'error': 'regNo is required'}, status=status.HTTP_400_BAD_REQUEST)

        admission_student = AdmissionStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('program').first()

        student_name    = admission_student.name    if admission_student else reg_no
        student_program = admission_student.program if admission_student else None

        course_students = CourseStudent.objects.filter(
            reg_no__iexact=reg_no
        ).exclude(course__is_historical=True, course__status='active').exclude(result_status='withdrawn').select_related('course__program').prefetch_related(
            'obe_marks__question',
            'marks__unit_item__category',
            'course__obe_questions',
            'course__clos__mapped_ga',
        )

        if not course_students.exists():
            return Response({
                'regNo':       reg_no,
                'studentName': student_name,
                'programId':   student_program.code.lower() if student_program else None,
                'attainments': [],
            })

        # Same rules as the other GA reports: the questions-passed rule in each
        # course, the best attempt at a repeated course, the framework's overall rule.
        ga_info, ga_courses, titles = {}, {}, {}
        by_code = {}
        for cs in course_students:
            by_code.setdefault(cs.course.code, []).append(cs)
        for code, attempts in by_code.items():
            cs = _best_attempt(attempts)
            ga_items, ga_objs = _ga_question_items(cs.course)[:2]
            titles[code] = cs.course.title
            for g, items in ga_items.items():
                ga_info[g] = ga_objs[g].name
                ga_courses.setdefault(g, {})[code] = round(_ga_questions_passed(cs, items, ATTAINMENT_THRESHOLD) / len(items) * 100, 1)

        attainments = []
        for ga_id in sorted(ga_courses, key=CourseGAStudentAttainmentView._ga_sort_key):
            overall = _student_overall_ga(ga_courses[ga_id])
            attainments.append({
                'gaId':               ga_id,
                'gaTitle':            ga_info[ga_id],
                'score':              overall['percent'],
                'passed':             overall['attained'],
                'coursesAttained':    overall['coursesAttained'],
                'courseCount':        overall['courseCount'],
                'contributingCourses': [
                    {'code': code, 'title': titles[code], 'score': pct} for code, pct in sorted(ga_courses[ga_id].items())
                ],
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

        # Every offering of the course (term + instructor), before narrowing —
        # the frontend fills its Term / Instructor pickers from this.
        offerings = [
            {
                'id':           ic.pk,
                'academicYear': ic.academic_year,
                'instructorId': ic.instructor_id,
                'instructor':   ic.instructor.user.get_full_name() or ic.instructor.user.username,
            }
            for ic in qs.select_related('instructor__user').order_by('academic_year', 'pk')
        ]
        if request.query_params.get('offeringsOnly'):
            return Response({'courseCode': course_code, 'offerings': offerings})

        academic_year = request.query_params.get('academicYear', '').strip()
        instructor_id = request.query_params.get('instructorId', '').strip()
        if academic_year:
            qs = qs.filter(academic_year__iexact=academic_year)
        if instructor_id.isdigit():
            qs = qs.filter(instructor_id=int(instructor_id))
        if not qs.exists():
            return Response(
                {'error': f'No offering of "{course_code}" for the selected term / instructor'},
                status=status.HTTP_404_NOT_FOUND
            )

        all_students  = []
        all_questions = []
        course_title  = ''
        prog_id_out   = program_id.lower() if program_id else None
        clo_scores_all = {}   # clo code -> {reg no: %}: a repeated course counts once, at its best attempt
        attempts_by_student = {}   # reg no -> [(attempt, its questions)]
        instructors    = []   # offering instructors, in order, de-duplicated
        academic_years = []
        program_obj    = None

        for ic in qs.select_related('instructor__user', 'program__department').prefetch_related(
            _marks_with_question(),
            _marks_with_unit(),
            'obe_questions',
        ):
            course_title = ic.title
            program_obj  = program_obj or ic.program
            inst_name    = ic.instructor.user.get_full_name() or ic.instructor.user.username
            if inst_name not in instructors:
                instructors.append(inst_name)
            if ic.academic_year and ic.academic_year not in academic_years:
                academic_years.append(ic.academic_year)
            if not prog_id_out and ic.program:
                prog_id_out = ic.program.code.lower()
            ic_questions = list(ic.obe_questions.all())
            all_questions.extend(ic_questions)
            # Score every student against THEIR OWN section's questions only.
            # A course can have several sections (one InstructorCourse each);
            # pooling every section's questions into one denominator made a
            # student who earned 58% on their section read as 29%, i.e. CLO
            # attainment was divided by the number of sections.
            for student in _graded_students(ic):
                attempts_by_student.setdefault(_reg_key(student.reg_no), []).append((student, ic_questions))

        for reg, attempts in attempts_by_student.items():
            questions_of = {student.pk: questions for student, questions in attempts}
            chosen = _best_attempt([student for student, _questions in attempts])
            for clo, pct in _clo_attainments_for_student(chosen, questions_of[chosen.pk]).items():
                clo_scores_all.setdefault(clo, {})[reg] = pct

        class_size = len(attempts_by_student)

        # CLO max marks (total across all questions mapped to that CLO)
        clo_max_marks = {}
        for q in all_questions:
            for clo in q.mapped_clos:
                clo_max_marks.setdefault(clo, 0.0)
                clo_max_marks[clo] += q.max_marks

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
            scores         = list(clo_scores_all[clo].values())
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
            'programName':         program_obj.name if program_obj else None,
            'programCode':         program_obj.code.upper() if program_obj else None,
            'departmentName':      program_obj.department.name if program_obj else None,
            'instructors':         instructors,
            'academicYears':       academic_years,
            'offerings':           offerings,
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

        # SECURITY: force student's own regNo — any logged-in student could
        # read another student's GA attainment by passing a different regNo.
        # regNo follows a predictable pattern (FA22-BSCS-0012).
        if request.user.role == 'student':
            try:
                reg_no = request.user.student_profile.reg_no
            except Exception:
                return Response(
                    {'error': 'Student profile not found'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif not reg_no:
            return Response({'error': 'regNo is required'}, status=status.HTTP_400_BAD_REQUEST)

        admission_student = AdmissionStudent.objects.filter(
            reg_no__iexact=reg_no
        ).select_related('program').first()

        student_name    = admission_student.name    if admission_student else reg_no
        student_program = admission_student.program if admission_student else None

        course_students = CourseStudent.objects.filter(
            reg_no__iexact=reg_no
        ).exclude(course__is_historical=True, course__status='active').select_related('course').prefetch_related(
            'marks__unit_item__category',
            'obe_marks__question',
            'course__grade_scale',
        )

        enrolled_courses      = []
        total_credit_points   = 0.0
        total_credits         = 0

        for cs in course_students:
            ic          = cs.course
            exact_pct   = _sheet_course_total(cs)['total']
            student_pct = round(exact_pct, 2)
            grade_letter, grade_points = _get_grade(exact_pct, ic)
            withdrawn = cs.result_status == 'withdrawn'
            if withdrawn:
                grade_letter, grade_points = 'W', 0.0


            questions = list(ic.obe_questions.all())
            clo_pcts = _clo_attainments_for_student(cs, questions)

            # Build CLO meta (description + GA) for this course
            clo_meta_summary = {
                clo_obj.code: {
                    'description': clo_obj.description or '',
                    'mappedGA': {
                        'gaId':    clo_obj.mapped_ga.ga_id,
                        'gaTitle': clo_obj.mapped_ga.name,
                    } if clo_obj.mapped_ga else None,
                }
                for clo_obj in ic.clos.select_related('mapped_ga').all()
            }

            clo_attainments = [
                {
                    'code':        clo,
                    'description': clo_meta_summary.get(clo, {}).get('description', ''),
                    'percentage':  pct,
                    'attained':    pct >= ATTAINMENT_THRESHOLD,
                    'status':      'Attained' if pct >= ATTAINMENT_THRESHOLD else 'Not Attained',
                    'mappedGA':    clo_meta_summary.get(clo, {}).get('mappedGA'),
                }
                for clo, pct in sorted(clo_pcts.items())
            ]

            credit_hours         = ic.credit_hours
            if not withdrawn:   # W is on the record but not in the GPA
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

def _resolve_ga(ga_identifier, course=None):
    """
    Resolve a GA identifier to a GraduateAttribute, scoped to `course`.

    `course` is the InstructorCourse the CLO belongs to. When given, only GAs
    from that course's department (and program, where the GA has one) are
    eligible, so a CLO can never be mapped to another program's or another
    department's attribute.

    The previous version fell back to matching on the digits alone: 'GA1-CS'
    became '1' and resolved to 'BSCS1' — a different program's GA — and when
    several matched it tried a fixed prefix list and finally returned
    *whichever row came first*, even from another department. Attainment
    reports then credited the wrong GA with no error anywhere.

    Resolution order:
      1. Exact ga_id match (case-insensitive), within scope.
      2. Legacy shorthand ('GA-8', 'GA8', '8') -> the attribute numbered 8 in
         this course's own program/department — but ONLY if exactly one such
         attribute exists. Ambiguity returns None instead of guessing.
    """
    if not ga_identifier:
        return None
    ga_id = str(ga_identifier).strip()
    if not ga_id:
        return None

    scope = GraduateAttribute.objects.all()
    if course is not None:
        scope = scope.filter(department_id=course.department_id)
        if getattr(course, 'program_id', None):
            # GAs tied to this program, plus department-wide ones with no program.
            scope = scope.filter(
                models.Q(program_id=course.program_id) | models.Q(program__isnull=True)
            )

    # 1. Exact match within scope.
    exact = scope.filter(ga_id__iexact=ga_id).first()
    if exact:
        return exact

    # 2. Legacy numeric shorthand — only meaningful with a course to scope it,
    #    and only when the identifier is a single number ('GA-8', 'GA8', '8').
    #    A multi-number id such as 'GA1-CS2' is not shorthand; don't mangle it.
    if course is None:
        return None
    # If this is a real GA id that simply belongs to another program or
    # department, refuse it — reinterpreting its number as "this program's
    # GA n" is exactly the wrong-attribute mapping this function exists to stop.
    if GraduateAttribute.objects.filter(ga_id__iexact=ga_id).exists():
        return None
    numbers = re.findall(r'\d+', ga_id)
    if len(numbers) != 1:
        return None
    digits = numbers[0].lstrip('0') or '0'
    candidates = [
        g for g in scope
        if (re.findall(r'\d+', g.ga_id) or [None])[-1] is not None
        and (re.findall(r'\d+', g.ga_id)[-1].lstrip('0') or '0') == digits
    ]
    return candidates[0] if len(candidates) == 1 else None


class CLOListView(APIView):
    """
    GET  /api/instructor/courses/<frontend_id>/clos/
         Returns all CLOs for a specific instructor course.

    POST /api/instructor/courses/<frontend_id>/clos/
         Create a new CLO.
         Body: { code, description, mappedGA, order }
         mappedGA: GA id string e.g. "GA-1" or null
    """
    permission_classes = [IsAuthenticated]

    def _get_course(self, request, frontend_id):
        """
        Instructors can only access their own courses (ownership check).
        QA / dept_admin / admin can access any course for oversight.
        """
        role = getattr(request.user, 'role', '')

        # Staff roles: unrestricted access
        if role in ('qa', 'dept_admin', 'admin'):
            try:
                return InstructorCourse.objects.get(frontend_id=frontend_id)
            except InstructorCourse.DoesNotExist:
                return None

        # Instructor: must own the course
        if role == 'instructor':
            profile = get_instructor_profile(request.user)
            if not profile:
                return None
            try:
                # Exact ownership match. InstructorCourse.instructor is non-null,
                # so there is no "unassigned course" case to fall back to.
                return InstructorCourse.objects.get(frontend_id=frontend_id, instructor=profile)
            except InstructorCourse.DoesNotExist:
                return None

        return None

    def get(self, request, frontend_id):
        course = self._get_course(request, frontend_id)
        if not course:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        clos = course.clos.select_related('mapped_ga').all()
        return Response(CLOSerializer(clos, many=True).data)

    def post(self, request, frontend_id):
        course = self._get_course(request, frontend_id)
        if not course:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == 'instructor' and _teacher_lock_message(course):
            return Response({'error': _teacher_lock_message(course)}, status=status.HTTP_400_BAD_REQUEST)

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
            ga = _resolve_ga(ga_id, course=course)
            if not ga:
                # Log and continue with no GA rather than blocking the instructor.
                # The instructor can remap later once GAs are added.
                logger.warning(
                    f'CLO POST: Graduate Attribute "{ga_id}" not found — '
                    f'CLO will be saved without GA mapping. '
                    f'Add the Graduate Attributes for this program first.'
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
    permission_classes = [IsAuthenticated]

    def _get(self, request, frontend_id, clo_id):
        """
        Same logic as CLOListView._get_course but also resolves the CLO record.
        Staff roles (qa/dept_admin/admin) get unrestricted access.
        Instructors get access to their own course's CLOs, with fallback
        for newly assigned courses where the instructor FK may not be set.
        """
        role = getattr(request.user, 'role', '')

        if role in ('qa', 'dept_admin', 'admin'):
            try:
                return CLO.objects.select_related('mapped_ga', 'course').get(
                    pk=clo_id, course__frontend_id=frontend_id
                )
            except CLO.DoesNotExist:
                return None

        if role == 'instructor':
            profile = get_instructor_profile(request.user)
            if not profile:
                return None
            # Primary: ownership match
            try:
                return CLO.objects.select_related('mapped_ga', 'course').get(
                    pk=clo_id, course__frontend_id=frontend_id, course__instructor=profile
                )
            except CLO.DoesNotExist:
                return None

        return None

    def get(self, request, frontend_id, clo_id):
        clo = self._get(request, frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CLOSerializer(clo).data)

    def patch(self, request, frontend_id, clo_id):
        clo = self._get(request, frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == 'instructor' and _teacher_lock_message(clo.course):
            return Response({'error': _teacher_lock_message(clo.course)}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        if 'description' in data:
            clo.description = data['description'].strip()
        if 'order' in data:
            clo.order = data['order']
        if 'mappedGA' in data:
            ga_id = data.get('mappedGA') or data.get('mapped_ga') or ''
            if ga_id:
                ga = _resolve_ga(ga_id, course=clo.course)
                if ga:
                    clo.mapped_ga = ga
                else:
                    import logging
                    logging.getLogger(__name__).warning(
                        f'CLO PATCH: Graduate Attribute "{ga_id}" not found — '
                        f'GA mapping unchanged. '
                        f'Add the Graduate Attributes for this program first.'
                    )
            else:
                clo.mapped_ga = None
        clo.save()
        return Response(CLOSerializer(clo).data)

    def delete(self, request, frontend_id, clo_id):
        clo = self._get(request, frontend_id, clo_id)
        if not clo:
            return Response({'error': 'CLO not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == 'instructor' and _teacher_lock_message(clo.course):
            return Response({'error': _teacher_lock_message(clo.course)}, status=status.HTTP_400_BAD_REQUEST)
        clo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Additional OBE Reports ───────────────────────────────────────────────────

ATTAINMENT_THRESHOLD = 50.0


def _ga_question_items(ic):
    """
    Graded questions of one offering grouped by the GA of their CLO
    (question -> first mapped CLO -> CLO.mapped_ga). Only the offering's own
    questions on units of weighted assessment categories count, as on the
    mark sheet. Returns (ga_items, ga_objs, ga_clos, graded_count, unmapped)
    where ga_items[ga_id] = [(unit_item, question, questions_in_unit), ...].
    """
    # .all() + Python filters (same rows/order: Meta orderings are 'order' and
    # 'unit_no') so GA_QUESTION_PREFETCH is used instead of per-unit queries.
    clo_ga = {c.code.strip().upper(): c.mapped_ga for c in ic.clos.all()}
    graded = []
    if ic.catalog_course_id:
        for cat in ic.catalog_course.markscategories.all():
            if not (cat.percentage > 0):
                continue
            for ui in cat.unit_items.all():
                if ui.unit_no > cat.units:
                    continue
                own = sorted((q for q in ui.questions.all() if q.course_id == ic.id), key=lambda q: (q.order, q.id))
                for q in own:
                    graded.append((ui, q, len(own)))
    ga_items, ga_objs, ga_clos = {}, {}, {}
    unmapped = 0
    for ui, q, n in graded:
        clo = (q.mapped_clos or [None])[0]
        ga = clo_ga.get(str(clo).strip().upper()) if clo else None
        if ga is None:
            unmapped += 1
            continue
        ga_items.setdefault(ga.ga_id, []).append((ui, q, n))
        ga_objs[ga.ga_id] = ga
        ga_clos.setdefault(ga.ga_id, set()).add(str(clo).strip().upper())
    return ga_items, ga_objs, ga_clos, len(graded), unmapped


def _ga_questions_passed(course_student, items, threshold):
    """How many of `items` the student passed (score >= threshold% of the question)."""
    unit_marks = {m.unit_item_id: m.score for m in course_student.marks.all()}
    q_marks = {om.question_id: om.score for om in course_student.obe_marks.all()}
    passed = 0
    for ui, q, n in items:
        val = q_marks.get(q.id)
        if (val is None or float(val) <= 0) and n == 1:
            val = unit_marks.get(ui.id, val)   # single-question unit: unit mark, as the sheet does
        val = float(val or 0)
        if (q.max_marks or 0) > 0 and (val / q.max_marks) * 100 >= threshold:
            passed += 1
    return passed


# Everything _ga_question_items / _ga_questions_passed read, for an
# InstructorCourse queryset.
GA_QUESTION_PREFETCH = (
    'students__marks',
    'students__obe_marks',
    'clos__mapped_ga',
    'catalog_course__markscategories__unit_items__questions',
)


def _offering_ga_student_pcts(ic, students, threshold=None):
    """
    GA attainment of each student of one offering, by questions passed
    (question -> CLO -> GA; same rule as the QA "GA by Course" report).
    Returns {ga_id: [percent per student]}. Students with no marks at all in
    this offering are left out, so unmarked rosters don't pull averages to 0.
    """
    threshold = ATTAINMENT_THRESHOLD if threshold is None else threshold
    ga_items = _ga_question_items(ic)[0]
    marked = [s for s in students if list(s.marks.all()) or list(s.obe_marks.all())]
    out = {}
    for g, items in ga_items.items():
        if marked:
            out[g] = [round(_ga_questions_passed(s, items, threshold) / len(items) * 100, 1) for s in marked]
    return out


def _student_ga_attainments(course_student, threshold=None):
    """
    One student's GA attainment in one course by questions passed -- the same
    rule as the QA "GA by Course" / "GA by Student" reports. Returns
    [{gaId, gaTitle, passed, total, percent, attained}], sorted by GA.
    """
    threshold = ATTAINMENT_THRESHOLD if threshold is None else threshold
    ga_items, ga_objs = _ga_question_items(course_student.course)[:2]
    out = []
    for g in sorted(ga_items, key=CourseGAStudentAttainmentView._ga_sort_key):
        items = ga_items[g]
        passed = _ga_questions_passed(course_student, items, threshold)
        pct = round(passed / len(items) * 100, 1)
        out.append({'gaId': g, 'gaTitle': ga_objs[g].name, 'passed': passed,
                    'total': len(items), 'percent': pct, 'attained': pct >= threshold})
    return out


def _report_offerings(qs):
    """Offerings reports count: a past course still being entered is a draft."""
    return qs.exclude(is_historical=True, status='active')


def _reg_key(reg_no):
    return str(reg_no or '').strip().upper()


def _best_attempt(attempts):
    """
    The attempt reports count for a student who took a course more than once:
    the whole attempt with the highest course total, the latest if tied. Its CLO
    and GA results are used together, never mixed with another attempt's.
    """
    if len(attempts) == 1:
        return attempts[0]
    return max(attempts, key=lambda s: (_sheet_course_total(s)['total'], _term_sort_key(s.course.academic_year)))


def _course_ga_best(offerings, reg_nos=None):
    """
    Each student's GA percent in each course code: {code: {ga_id: {reg_no: percent}}}.
    A student with several attempts at a course counts once, at their best attempt.
    reg_nos (upper case) limits it to those students. Also returns course titles.
    """
    attempts, titles = {}, {}
    for ic in offerings:
        for s in _graded_students(ic):
            key = _reg_key(s.reg_no)
            if (reg_nos is None or key in reg_nos) and (list(s.marks.all()) or list(s.obe_marks.all())):
                attempts.setdefault((ic.code, key), []).append(s)
                titles[ic.code] = ic.title

    best = {}
    ga_items_of = {}
    for (code, key), rows in attempts.items():
        s = _best_attempt(rows)
        ga_items = ga_items_of.setdefault(s.course_id, _ga_question_items(s.course)[0])
        for g, items in ga_items.items():
            best.setdefault(code, {}).setdefault(g, {})[key] = round(
                _ga_questions_passed(s, items, ATTAINMENT_THRESHOLD) / len(items) * 100, 1)
    return best, titles


def _course_ga_score(per_student):
    """A course's GA score: the percentage of its students who attain the GA."""
    attained = sum(1 for p in per_student.values() if p >= ATTAINMENT_THRESHOLD)
    return round(attained / len(per_student) * 100, 2) if per_student else 0.0, attained


def _direct_ga_courses(best, titles, codes=None):
    """{ga_id: [one row per course]} from _course_ga_best, optionally for some course codes only."""
    out = {}
    for code in sorted(best):
        if codes is not None and code not in codes:
            continue
        for g, per_student in best[code].items():
            score, attained = _course_ga_score(per_student)
            out.setdefault(g, []).append({
                'code':             code,
                'title':            titles.get(code, code),
                'score':            score,
                'studentsAttained': attained,
                'studentCount':     len(per_student),
                'attained':         score >= ATTAINMENT_THRESHOLD,
            })
    return out


def _direct_ga_summary(courses):
    """
    The direct GA result: the average of its course scores, for the 80/20 rule.
    The KPI is the framework's: at least 50% of the mapped courses attain the GA.
    """
    attained = sum(1 for c in courses if c['attained'])
    average = round(sum(c['score'] for c in courses) / len(courses), 2) if courses else 0.0
    return {
        'averageAttainment':        average,
        'contributingCoursesCount': len(courses),
        'coursesAttained':          attained,
        'kpiMet':                   bool(courses) and attained / len(courses) * 100 >= ATTAINMENT_THRESHOLD,
    }


def _student_overall_ga(course_percents):
    """
    A student's overall GA from {course code: percent}. The framework's rule: the
    GA must be attained in at least 50% of its mapped courses, with an average
    score of at least 50%.
    """
    values = list(course_percents.values())
    attained = sum(1 for p in values if p >= ATTAINMENT_THRESHOLD)
    average = round(sum(values) / len(values), 1) if values else 0.0
    return {
        'percent':         average,
        'courseCount':     len(values),
        'coursesAttained': attained,
        'attained':        bool(values) and attained / len(values) * 100 >= ATTAINMENT_THRESHOLD and average >= ATTAINMENT_THRESHOLD,
    }


def _program_offerings(program):
    return _report_offerings(InstructorCourse.objects.filter(program=program)).select_related(
        'catalog_course').prefetch_related(*GA_QUESTION_PREFETCH)


def _graduated_batches(program):
    """
    {batch code: {reg numbers}} of the program's graduated batches: a batch has
    graduated once all its 8th semester courses are finalized.
    """
    batches = {}
    for adm in AdmissionStudent.objects.filter(program=program):
        code = batch_code(adm.reg_no)
        if code:
            batches.setdefault(code, set()).add(_reg_key(adm.reg_no))
    final_semester = _offerings_in_semester(
        _report_offerings(InstructorCourse.objects.filter(program=program)), program, '8th'
    ).prefetch_related('students')
    final_offerings = [(ic.status == 'closed', {_reg_key(s.reg_no) for s in ic.students.all()}) for ic in final_semester]
    out = {}
    for code, reg_nos in batches.items():
        own = [closed for closed, roster in final_offerings if roster & reg_nos]
        if own and all(own):
            out[code] = reg_nos
    return out


class CourseGAStudentAttainmentView(APIView):
    """
    GET /api/reports/course-ga-students/?courseCode=CMC111&programId=bscs

    READ-ONLY. GA attainment of the students of one course, built from the
    question -> CLO -> GA chain:
      * every graded question (own questions of the offering, on the units of
        weighted assessment categories) counts towards the GA of its CLO;
      * a student PASSES a question when they score >= 50% of its marks
        (a single-question unit with no question mark falls back to the unit
        mark, exactly as the mark sheet does);
      * a student's GA attainment = questions passed / questions for that GA;
      * a student ATTAINS the GA when that is >= 50%.
    One block per offering (term / section) that has students.
    """
    permission_classes = [IsStaffReport]

    @staticmethod
    def _ga_sort_key(ga_id):
        import re as _re
        m = _re.search(r'\d+', ga_id or '')
        return (int(m.group()) if m else 9999, ga_id or '')

    def get(self, request):
        course_code = request.query_params.get('courseCode', '').strip()
        program_id  = request.query_params.get('programId', '').strip()
        if not course_code:
            return Response({'error': 'courseCode is required'}, status=status.HTTP_400_BAD_REQUEST)

        qs = InstructorCourse.objects.filter(code__iexact=course_code).select_related(
            'program', 'instructor__user', 'catalog_course')
        if program_id:
            qs = qs.filter(program__code__iexact=program_id)
        if not qs.exists():
            return Response({'error': f'No course offering found for "{course_code}"'},
                            status=status.HTTP_404_NOT_FOUND)

        threshold = ATTAINMENT_THRESHOLD
        offerings = []
        course_title = ''
        for ic in qs.order_by('-academic_year', 'id'):
            students = list(ic.students.exclude(result_status='withdrawn').prefetch_related('marks', 'obe_marks').order_by('reg_no'))
            if not students:
                continue
            course_title = course_title or ic.title

            ga_items, ga_objs, ga_clos, graded_count, unmapped = _ga_question_items(ic)

            # GAs QA mapped to the course but with no questions yet are listed too.
            if ic.catalog_course_id:
                for g in ic.catalog_course.mapped_gas.all():
                    ga_objs.setdefault(g.ga_id, g)

            ga_ids = sorted(ga_objs.keys(), key=self._ga_sort_key)
            attained_count = {g: 0 for g in ga_ids}
            pct_sum = {g: 0.0 for g in ga_ids}
            student_rows = []
            for st in students:
                row = {}
                for g in ga_ids:
                    items = ga_items.get(g, [])
                    if not items:
                        row[g] = None
                        continue
                    passed = _ga_questions_passed(st, items, threshold)
                    pct = round(passed / len(items) * 100, 1)
                    ok = pct >= threshold
                    row[g] = {'passed': passed, 'total': len(items), 'percent': pct, 'attained': ok}
                    pct_sum[g] += pct
                    if ok:
                        attained_count[g] += 1
                student_rows.append({'regNo': st.reg_no, 'name': st.name, 'gas': row})

            n_students = len(students)
            gas_out = []
            for g in ga_ids:
                n_q = len(ga_items.get(g, []))
                gas_out.append({
                    'id': g,
                    'title': ga_objs[g].name,
                    'questionCount': n_q,
                    'clos': sorted(ga_clos.get(g, [])),
                    'studentsAttained': attained_count[g] if n_q else 0,
                    'studentCount': n_students,
                    'percentStudentsAttained': round(attained_count[g] / n_students * 100, 1) if (n_q and n_students) else None,
                    'averageAttainment': round(pct_sum[g] / n_students, 1) if (n_q and n_students) else None,
                })

            offerings.append({
                'id': ic.frontend_id,
                'academicYear': ic.academic_year,
                'status': ic.status,
                'instructor': ic.instructor.user.get_full_name() or ic.instructor.user.username,
                'studentCount': n_students,
                'questionCount': graded_count,
                'unmappedQuestionCount': unmapped,
                'gas': gas_out,
                'students': student_rows,
            })

        return Response({
            'courseCode': course_code.upper(),
            'courseTitle': course_title,
            'programId': program_id.lower() or None,
            'questionPassThreshold': threshold,
            'gaAttainmentThreshold': threshold,
            'offerings': offerings,
        })


class StudentGAQuestionAttainmentView(APIView):
    """
    GET /api/reports/student-ga-questions/?regNo=052-FA23-22040

    READ-ONLY. One student's GA attainment across ALL their courses, with the
    same rule as the course report: a question is passed at >= 50% of its
    marks; GA attainment = questions passed / questions for that GA (summed
    over every course); the GA is attained at >= 50%. Also per course.

    A student gets only their own record and only finalized courses: this is
    their transcript, and a running course's half-entered marks would show as
    failed. A finalized course shows the grade on its permanent FinalResult.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reg_no = request.query_params.get('regNo', '').strip()
        is_student = request.user.role == 'student'
        if is_student:
            try:
                reg_no = request.user.student_profile.reg_no
            except Exception:
                return Response({'error': 'Student profile not found'}, status=status.HTTP_403_FORBIDDEN)
        elif not IsStaffReport().has_permission(request, self):
            return Response({'error': 'You do not have permission to view this report.'}, status=status.HTTP_403_FORBIDDEN)
        if not reg_no:
            return Response({'error': 'regNo is required'}, status=status.HTTP_400_BAD_REQUEST)
        enrolment_qs = CourseStudent.objects.filter(reg_no__iexact=reg_no).exclude(course__is_historical=True, course__status='active').exclude(result_status='withdrawn')
        if is_student:
            enrolment_qs = enrolment_qs.filter(course__status='closed')
        enrolments = list(enrolment_qs
                          .select_related('course__instructor__user', 'course__program', 'course__catalog_course')
                          .prefetch_related('marks', 'obe_marks')
                          .order_by('course__academic_year', 'course__code'))
        adm = AdmissionStudent.objects.filter(reg_no__iexact=reg_no).select_related('program', 'department').first()
        if not enrolments and not adm:
            return Response({'error': f'Student "{reg_no}" not found'}, status=status.HTTP_404_NOT_FOUND)

        official_grades = dict(FinalResult.objects.filter(student_reg_no__iexact=reg_no, source_course__isnull=False)
                               .values_list('source_course_id', 'grade_letter'))
        threshold = ATTAINMENT_THRESHOLD
        totals = {}      # ga_id -> {'passed', 'total', 'courses': {code: percent}, 'title'}
        courses_out = []
        by_code = {}
        for cs in enrolments:
            by_code.setdefault(cs.course.code, []).append(cs)
        counted = {_best_attempt(attempts).pk for attempts in by_code.values()}   # a repeated course counts at its best attempt
        for cs in enrolments:
            ic = cs.course
            ga_items, ga_objs, _clos, graded_count, unmapped = _ga_question_items(ic)
            per_ga = {}
            for g, items in ga_items.items():
                passed = _ga_questions_passed(cs, items, threshold)
                pct = round(passed / len(items) * 100, 1)
                per_ga[g] = {'passed': passed, 'total': len(items), 'percent': pct, 'attained': pct >= threshold}
                if cs.pk not in counted:
                    continue
                t = totals.setdefault(g, {'passed': 0, 'total': 0, 'courses': {}, 'title': ga_objs[g].name})
                t['passed'] += passed
                t['total'] += len(items)
                t['courses'][ic.code] = pct
            courses_out.append({
                'courseCode': ic.code, 'courseTitle': ic.title, 'academicYear': ic.academic_year,
                'status': ic.status,
                'instructor': ic.instructor.user.get_full_name() or ic.instructor.user.username,
                'creditHours': ic.credit_hours,
                'grade': official_grades.get(ic.id) or _get_grade(_sheet_course_total(cs)['total'], ic)[0],
                'questionCount': graded_count, 'unmappedQuestionCount': unmapped,
                'gas': per_ga,
            })

        gas_out = []
        for g in sorted(totals.keys(), key=CourseGAStudentAttainmentView._ga_sort_key):
            t = totals[g]
            gas_out.append({'id': g, 'title': t['title'], 'passed': t['passed'], 'total': t['total'],
                            **_student_overall_ga(t['courses'])})

        return Response({
            'regNo': adm.reg_no if adm else (enrolments[0].reg_no if enrolments else reg_no),
            'name': adm.name if adm else (enrolments[0].name if enrolments else ''),
            'programId': adm.program.code.lower() if adm and adm.program_id else None,
            'programCode': (adm.program.code.upper() if adm and adm.program_id
                            else (enrolments[0].course.program.code.upper() if enrolments and enrolments[0].course.program else '')),
            'programName': (adm.program.name if adm and adm.program_id
                            else (enrolments[0].course.program.name if enrolments and enrolments[0].course.program else '')),
            'departmentName': (adm.department.name if adm and adm.department_id
                               else (enrolments[0].course.department.name if enrolments else '')),
            'batch': adm.batch if adm else '',
            'questionPassThreshold': threshold,
            'gaAttainmentThreshold': threshold,
            'gas': gas_out,
            'courses': courses_out,
        })


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

        ic_qs = _report_offerings(InstructorCourse.objects.filter(program=program)).prefetch_related(
            'clos__mapped_ga',
            'students__obe_marks',
            'obe_questions',
        )
        if semester:
            ic_qs = _offerings_in_semester(ic_qs, program, semester)
        # Also support filtering by academicYear query param
        academic_year_param = request.query_params.get('academicYear', '').strip()
        if academic_year_param:
            ic_qs = ic_qs.filter(academic_year__iexact=academic_year_param)

        courses_data = []
        for ic in ic_qs:
            # A CLO is Met when at least 50% of the students attain it (framework KPI).
            all_questions = list(ic.obe_questions.all())
            students = [s for s in _graded_students(ic) if list(s.obe_marks.all())]
            student_pcts = [_clo_attainments_for_student(s, all_questions) for s in students]

            clos_data = []
            for clo in ic.clos.all():
                pcts = [p[clo.code] for p in student_pcts if clo.code in p]
                attained = sum(1 for p in pcts if p >= ATTAINMENT_THRESHOLD)
                pct = round(attained / len(pcts) * 100, 1) if pcts else 0

                clos_data.append({
                    'code':              clo.code,
                    'description':       clo.description,
                    'mappedGA':          clo.mapped_ga.ga_id if clo.mapped_ga else None,
                    'attainmentPercent': pct,
                    'studentsAttained':  attained,
                    'studentCount':      len(pcts),
                    'classAverage':      round(sum(pcts) / len(pcts), 1) if pcts else 0,
                    'status':            'Met' if pct >= ATTAINMENT_THRESHOLD else 'Not Met',
                })

            courses_data.append({
                'courseCode':   ic.code,
                'courseTitle':  ic.title,
                'semester':     ic.semester,
                'academicYear': ic.academic_year,
                'clos':         clos_data,
            })

        courses_data.sort(key=lambda c: (_term_sort_key(c['academicYear']), c['courseCode']))
        return Response({
            'programId': program.code.lower(),
            'semester':  semester or 'all',
            'courses':   courses_data,
        })


class POAttainmentView(APIView):
    """
    GET /api/reports/po-attainment/?programId=bscs[&graduationYear=2026]

    Program Outcome attainment, two separate figures that are never combined:
      - direct: the average of the direct results of the GAs mapped to the PO
      - indirect: the employer and alumni surveys, the only tools the framework
        lists for PO. graduationYear limits them to those graduates.
    Survey data, so QA and department admins only.
    """
    permission_classes = [IsDeptAdminOrQA]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            program = Program.objects.get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        graduation_year = request.query_params.get('graduationYear', '').strip()
        graduation_year = int(graduation_year) if graduation_year.isdigit() else None

        best, titles = _course_ga_best(_program_offerings(program))
        ga_courses = _direct_ga_courses(best, titles)
        indirect, response_counts = indirect_po(program, graduation_year=graduation_year)

        def met(value):
            return 'Met' if value >= ATTAINMENT_THRESHOLD else 'Not Met'

        pos_data = []
        for po in program.objectives.prefetch_related('ga_mappings__graduate_attribute').all():
            contributing_gas = []
            for mapping in po.ga_mappings.all():
                ga = mapping.graduate_attribute
                contributing_gas.append({
                    'gaId':              ga.ga_id,
                    'gaName':            ga.name,
                    'attainmentPercent': _direct_ga_summary(ga_courses.get(ga.ga_id, []))['averageAttainment'],
                })
            direct = (round(sum(g['attainmentPercent'] for g in contributing_gas) / len(contributing_gas), 1)
                      if contributing_gas else 0)
            survey = indirect.get(po.code)
            pos_data.append({
                'id':              po.code,
                'text':            po.description,
                'directPercent':   direct,
                'directStatus':    met(direct),
                'contributingGAs': contributing_gas,
                'indirectPercent': survey['percent'] if survey else None,
                'indirectStatus':  met(survey['percent']) if survey else None,
                'questions':       survey['questions'] if survey else [],
            })

        return Response({
            'programId':       program.code.lower(),
            'programName':     program.name,
            'graduationYear':  graduation_year,
            'graduationYears': graduation_years(program),
            'responseCounts':  response_counts,
            'pos':             pos_data,
        })


class InstructorPerformanceView(APIView):
    """
    GET /api/reports/instructor-performance/?departmentId=computing

    Shows per-instructor: which courses are below attainment threshold.
    For dept_admin and QA use.
    """
    # SECURITY: was IsAuthenticated only — any logged-in student could pull
    # instructor names and their per-course performance breakdown. A prior
    # commit (5927da4) claimed to apply IsStaffReport here but the string
    # replace silently didn't match and this was left unfixed — verified
    # and actually applied now.
    permission_classes = [IsStaffReport]

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
        result = []
        plan_cache = {}
        for profile in instructors:
            courses_data = []
            # Only report on active (current) courses, not historical closed ones.
            # Closed courses are already finalized — their data is in FinalResult.
            for ic in profile.instructor_courses.filter(status='active', is_historical=False).select_related('program').prefetch_related('students__obe_marks'):
                # Each CLO's figure: the percentage of students who attain it.
                clo_attainments = []
                questions = list(ic.obe_questions.all())
                student_pcts = [_clo_attainments_for_student(s, questions) for s in _graded_students(ic) if list(s.obe_marks.all())]
                for clo in ic.clos.all():
                    pcts = [p[clo.code] for p in student_pcts if clo.code in p]
                    clo_attainments.append(round(sum(1 for p in pcts if p >= ATTAINMENT_THRESHOLD) / len(pcts) * 100, 1) if pcts else 0)

                avg = round(sum(clo_attainments) / len(clo_attainments), 1) if clo_attainments else 0
                courses_data.append({
                    'courseCode':        ic.code,
                    'courseTitle':       ic.title,
                    'programCode':       ic.program.code if ic.program else '',
                    'semester':          ic.semester or _plan_semester(ic.program_id, ic.code, plan_cache),
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


class CLOCQIReportView(APIView):
    """
    GET /api/reports/clo-cqi/?departmentId=ee&programId=bsee&academicYear=Fall-2025&semester=3rd

    CLO CQI (Continuous Quality Improvement) report — instructor-wise.
    One entry per course offering with the number of students who passed /
    failed each CLO (a student passes a CLO when their attainment on the
    questions mapped to it is >= ATTAINMENT_THRESHOLD).

    ?yearsOnly=1 returns just the academic years (for the term picker).

    Response:
    {
      "departmentId": "ee",
      "attainmentThreshold": 50.0,
      "academicYears": ["Spring-2025", "Fall-2025", ...],
      "courses": [
        {
          "courseCode": "EE-102", "courseTitle": "Linear Circuit Analysis",
          "courseType": "Theory", "instructor": "Dr. ...",
          "semester": "1st", "academicYear": "Fall-2025", "programCode": "BSEE",
          "totalStudents": 27, "hasData": true,
          "clos": [{ "code": "CLO-1", "description": "...", "passed": 18, "failed": 9 }]
        }
      ]
    }
    """
    permission_classes = [IsStaffReport]

    def get(self, request):
        dept_id       = request.query_params.get('departmentId', '').strip()
        program_id    = request.query_params.get('programId', '').strip()
        academic_year = request.query_params.get('academicYear', '').strip()
        semester      = request.query_params.get('semester', '').strip()

        if not dept_id:
            return Response({'error': 'departmentId is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            department = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return Response({'error': f'Department "{dept_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        base_qs = InstructorCourse.objects.filter(department=department)
        if program_id:
            base_qs = base_qs.filter(program__code__iexact=program_id)

        def term_key(term):
            # 'Spring-2025' < 'Fall-2025' < 'Spring-2026'; unknown formats sort last.
            m = re.match(r'(spring|summer|fall)\D*(\d{4})', term, re.I)
            return (int(m.group(2)), ['spring', 'summer', 'fall'].index(m.group(1).lower())) if m else (9999, 0)

        academic_years = sorted({y for y in base_qs.values_list('academic_year', flat=True) if y}, key=term_key)
        if request.query_params.get('yearsOnly'):
            return Response({'departmentId': dept_id, 'academicYears': academic_years})

        ic_qs = base_qs
        if academic_year:
            ic_qs = ic_qs.filter(academic_year__iexact=academic_year)

        offerings = list(
            ic_qs.select_related('instructor__user', 'program')
                 .prefetch_related('clos', 'obe_questions', 'students')
                 .order_by('code', 'course_type')
        )

        # Offerings are created with a blank semester, so it comes from the plan.
        plan_cache = {}
        semester_of = {ic.pk: ic.semester or _plan_semester(ic.program_id, ic.code, plan_cache) for ic in offerings}
        if semester:
            offerings = [ic for ic in offerings if semester_of[ic.pk] == semester]

        # One query for every mark of every offering: { (student_pk, question_pk): score }
        all_question_ids = [q.pk for ic in offerings for q in ic.obe_questions.all()]
        score_of = {
            (m.student_id, m.question_id): m.score
            for m in OBEStudentMark.objects.filter(question_id__in=all_question_ids).exclude(student__result_status='withdrawn')
        }

        def natural_key(code):
            return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(code))]

        courses_data = []
        for ic in offerings:
            questions = list(ic.obe_questions.all())
            students  = _graded_students(ic)
            descriptions = {c.code: c.description for c in ic.clos.all()}

            clo_codes = set(descriptions)
            for q in questions:
                clo_codes.update(q.mapped_clos or [])

            has_data = bool(questions) and any(
                (st.pk, q.pk) in score_of for st in students for q in questions
            )

            clos_data = []
            for code in sorted(clo_codes, key=natural_key):
                clo_qs = [q for q in questions if code in (q.mapped_clos or [])]
                total_max = sum(q.max_marks for q in clo_qs)
                passed = failed = 0
                if total_max > 0:
                    for st in students:
                        obtained = sum(score_of.get((st.pk, q.pk), 0.0) for q in clo_qs)
                        if obtained / total_max * 100 >= ATTAINMENT_THRESHOLD:
                            passed += 1
                        else:
                            failed += 1
                clos_data.append({
                    'code':        code,
                    'description': descriptions.get(code, ''),
                    'passed':      passed,
                    'failed':      failed,
                    'assessed':    total_max > 0,
                })

            user = ic.instructor.user
            courses_data.append({
                'id':            ic.pk,
                'courseCode':    ic.code,
                'courseTitle':   ic.title,
                'courseType':    ic.course_type,
                'instructor':    user.get_full_name() or user.username,
                'semester':      semester_of[ic.pk],
                'academicYear':  ic.academic_year,
                'programCode':   ic.program.code.upper() if ic.program else '',
                'programName':   ic.program.name if ic.program else '',
                'totalStudents': len(students),
                'hasData':       has_data,
                'clos':          clos_data,
            })

        return Response({
            'departmentId':        dept_id,
            'departmentName':      department.name,
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'academicYears':       academic_years,
            'courses':             courses_data,
        })


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

        # Each term's figure uses the same rule as the direct GA result: the average
        # of the courses' scores, a score being the percentage of students attaining.
        offerings = _program_offerings(program)
        if ga:
            offerings = offerings.filter(clos__mapped_ga=ga).distinct()

        by_year = {}
        for ic in offerings:
            scores = by_year.setdefault(ic.academic_year or 'Unknown', [])
            students = [s for s in _graded_students(ic) if list(s.marks.all()) or list(s.obe_marks.all())]
            if not students:
                continue
            for g, pcts in _offering_ga_student_pcts(ic, students).items():
                if not ga or g == ga.ga_id:
                    scores.append(sum(1 for p in pcts if p >= ATTAINMENT_THRESHOLD) / len(pcts) * 100)

        cohorts = []
        for year in sorted(by_year.keys(), key=_term_sort_key):
            scores = by_year[year]
            cohorts.append({
                'academicYear':      year,
                'attainmentPercent': round(sum(scores) / len(scores), 1) if scores else 0,
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
    # SECURITY: was IsAuthenticated only — any logged-in student could see
    # classmates flagged as at-risk by name. Same silent-replace-failure
    # issue as InstructorPerformanceView above — verified and actually
    # applied now.
    permission_classes = [IsStaffReport]

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
            ic_qs = _offerings_in_semester(ic_qs, program, semester)
        academic_year_param = request.query_params.get('academicYear', '').strip()
        if academic_year_param:
            ic_qs = ic_qs.filter(academic_year__iexact=academic_year_param)

        # Map regNo → list of failed CLOs
        student_failures = {}

        for ic in ic_qs.prefetch_related(_marks_with_question(), 'clos', 'obe_questions'):
            # Build mark lookup dict once per course — avoids N×M×P×Q DB queries
            # Structure: { (student_pk, question_pk): score }
            all_questions = list(ic.obe_questions.all())
            mark_lookup   = {}
            for student in ic.students.all():
                for obe_mark in student.obe_marks.all():
                    mark_lookup[(student.pk, obe_mark.question_id)] = obe_mark.score

            for student in _graded_students(ic):
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

        gas = list(GraduateAttribute.objects.filter(
            models.Q(department=program.department, program__isnull=True) |
            models.Q(program=program)
        ))
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

        best, titles = _course_ga_best(_program_offerings(program))
        ga_courses = _direct_ga_courses(best, titles)

        for ga in gas:
            mapped_courses = Course.objects.filter(program=program, mapped_gas=ga)
            active_clos    = clos_by_ga.get(ga.id, [])
            avg_att = _direct_ga_summary(ga_courses.get(ga.ga_id, []))['averageAttainment']
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

class CohortLevelGAView(APIView):
    """
    GET /api/reports/cohort-ga/?programId=bscs

    Cohort Level GA Attainment for the program's graduated batches: the direct
    result from marks, the indirect result from the internship and exit surveys,
    and combined by the department's weights (80% direct + 20% indirect unless
    QA changes them). Combined needs every result with a weight above 0.
    Survey data, so QA and department admins only.
    """
    permission_classes = [IsDeptAdminOrQA]

    def get(self, request):
        program_id = request.query_params.get('programId', '').strip()
        if not program_id:
            return Response({'error': 'programId is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            program = Program.objects.select_related('department').get(code__iexact=program_id)
        except Program.DoesNotExist:
            return Response({'error': f'Program "{program_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        direct_weight = program.department.direct_weight
        indirect_weight = 100 - direct_weight
        graduated = _graduated_batches(program)
        reg_nos = set().union(*graduated.values()) if graduated else set()
        best, titles = _course_ga_best(_program_offerings(program), reg_nos=reg_nos)
        ga_courses = _direct_ga_courses(best, titles)
        indirect, response_counts = indirect_ga(program, batches=list(graduated))

        gas = sorted(
            GraduateAttribute.objects.filter(
                models.Q(department=program.department, program__isnull=True) | models.Q(program=program)),
            key=lambda g: CourseGAStudentAttainmentView._ga_sort_key(g.ga_id),
        )
        attributes = []
        for ga in gas:
            courses = ga_courses.get(ga.ga_id, [])
            summary = _direct_ga_summary(courses)
            survey = indirect.get(ga.ga_id, {})
            has_direct = bool(courses)
            has_indirect = 'indirect' in survey
            combined = None
            if (has_direct or not direct_weight) and (has_indirect or not indirect_weight):
                combined = round((summary['averageAttainment'] * direct_weight + survey.get('indirect', 0) * indirect_weight) / 100, 2)
            attributes.append({
                'id':              ga.ga_id,
                'title':           ga.name,
                'direct':          summary['averageAttainment'] if has_direct else None,
                'mappedCourses':   summary['contributingCoursesCount'],
                'coursesAttained': summary['coursesAttained'],
                'directKpiMet':    summary['kpiMet'],
                'internship':      survey['internship']['percent'] if 'internship' in survey else None,
                'internshipResponses': survey['internship']['responses'] if 'internship' in survey else 0,
                'exit':            survey['exit']['percent'] if 'exit' in survey else None,
                'exitResponses':   survey['exit']['responses'] if 'exit' in survey else 0,
                'indirect':        survey.get('indirect'),
                'indirectKpiMet':  has_indirect and survey['indirect'] >= SURVEY_KPI,
                'combined':        combined,
                'attained':        combined is not None and combined >= ATTAINMENT_THRESHOLD,
                'courses':         courses,
            })

        return Response({
            'programId':           program.code.lower(),
            'programName':         program.name,
            'programCode':         program.code.upper(),
            'departmentName':      program.department.name,
            'graduatedBatches':    sorted(graduated),
            'directWeight':        direct_weight,
            'indirectWeight':      indirect_weight,
            'studentCount':        len(reg_nos),
            'responseCounts':      response_counts,
            'attainmentThreshold': ATTAINMENT_THRESHOLD,
            'attributes':          attributes,
        })


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

        # SECURITY: dept_admin can only onboard into their own department
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or department.id != admin_dept.id:
                return Response(
                    {'error': 'You can only onboard instructors into your own department.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Use email as username — email is unique so username is unique
        # Wrap User + InstructorProfile in atomic — if profile creation fails
        # after User is saved, the orphaned User rolls back automatically.
        # Without this, a crash here leaves a User with no profile and a taken
        # email that blocks any retry.
        with transaction.atomic():
            user = User.objects.create(
                username=email,
                email=email,
                first_name=name.split()[0] if name else '',
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else '',
                role='instructor',
                password=make_password(django_settings.DEFAULT_TEMP_PASSWORD),
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
            'message':            f'Account created. Default password is: {django_settings.DEFAULT_TEMP_PASSWORD}',
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

        # SECURITY: dept_admin can only delete instructors in their own department
        # This is the more dangerous half — deletion is irreversible
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or profile.department_id != admin_dept.id:
                return Response(
                    {'error': 'You can only remove instructors in your own department.'},
                    status=status.HTTP_403_FORBIDDEN
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

        if len(new_password) < 8:
            return Response(
                {'error': 'New password must be at least 8 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        if not user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if current_password == new_password:
            return Response(
                {'error': 'New password must be different from current password'},
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

        # The id may differ only in letter case from the stored one (the admin
        # screen used to send "...-Fall-2024" while the stored id is
        # "...-fall-2024"), and BOTH spellings can exist as separate rows.
        # .get(frontend_id__iexact=...) raised MultipleObjectsReturned for
        # that (an uncaught 500, surfaced as "Enrollment sync failed"), so
        # prefer the exact id, else the oldest case-insensitive match.
        candidates = InstructorCourse.objects.filter(frontend_id__iexact=course_id)
        ic = candidates.filter(frontend_id=course_id).first() or candidates.order_by('id').first()
        if ic is None:
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

        # A closed/finalized course's roster must never change — FinalResult
        # snapshots were already taken for exactly the students enrolled at
        # close time. Reproduced before fixing: this endpoint let an admin
        # both add a brand-new student AND remove 3 already-graded students
        # from a closed course's live roster in one call — the removed
        # students' FinalResult rows (their permanent transcript) stayed
        # intact and orphaned, while the live CourseStudent roster silently
        # stopped reflecting who was actually graded. Same guard
        # InstructorCourseView.post() already applies to mark edits.
        if ic.status == 'closed':
            return Response(
                {'error': f'Course "{course_id}" is closed (finalized {ic.closed_at}) — enrollment cannot be changed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if ic.submitted_at:
            return Response(
                {'error': f'Final marks for "{course_id}" have been submitted — send the course back before changing enrollment.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # True sync / idempotent overwrite:
        # The incoming list IS the desired roster. Add new students, remove
        # students no longer in the list -- except anyone who already has
        # marks: a missing or mistyped list must never delete marks, so those
        # students are kept and reported back in 'kept'.
        # Reg numbers are matched ignoring case and surrounding spaces, so an
        # existing row stored as "fa24-..." is reused, not duplicated+deleted.
        def _norm(r):
            return str(r or '').strip().upper()

        existing = {}
        for cs in CourseStudent.objects.filter(course=ic):
            existing.setdefault(_norm(cs.reg_no), cs)

        incoming_reg_nos = set()
        enrolled = []
        for s in students:
            if not isinstance(s, dict):
                continue
            reg_no = _norm(s.get('regNo'))
            name   = str(s.get('name') or '').strip()
            if not reg_no or reg_no in incoming_reg_nos:
                continue
            incoming_reg_nos.add(reg_no)
            if reg_no not in existing:
                # get_or_create: two identical requests at once used to 500 here.
                existing[reg_no], created = CourseStudent.objects.get_or_create(
                    course=ic, reg_no=reg_no, defaults={'name': name or reg_no}
                )
                if created:
                    enrolled.append(reg_no)

        removed = []
        kept    = []
        for key, cs in existing.items():
            if key in incoming_reg_nos:
                continue
            if _course_student_has_marks(cs):
                kept.append(cs.reg_no)
            else:
                removed.append(cs.reg_no)
                cs.delete()

        return Response({
            'courseId': course_id,
            'enrolled': enrolled,
            'removed':  removed,
            'kept':     kept,
            'total':    len(incoming_reg_nos) + len(kept),
            'message':  (
                f'{len(enrolled)} added, {len(removed)} removed, '
                f'{len(incoming_reg_nos) + len(kept)} total enrolled'
                + (f' ({len(kept)} kept because they have marks)' if kept else '')
            ),
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

        # Same case-insensitive lookup as post() so an id that enrolled a
        # student can also remove them.
        candidates = InstructorCourse.objects.filter(frontend_id__iexact=course_id, department=admin_dept)
        ic = candidates.filter(frontend_id=course_id).first() or candidates.order_by('id').first()
        if ic is None:
            return Response({'error': f'Course "{course_id}" not found'}, status=status.HTTP_404_NOT_FOUND)

        if ic.status == 'closed':
            return Response(
                {'error': f'Course "{course_id}" is closed (finalized {ic.closed_at}) — enrollment cannot be changed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if ic.submitted_at:
            return Response(
                {'error': f'Final marks for "{course_id}" have been submitted — send the course back before changing enrollment.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rows = [cs for cs in CourseStudent.objects.filter(course=ic, reg_no__iexact=reg_no)]
        if not rows:
            return Response({'error': 'Enrollment not found'}, status=status.HTTP_404_NOT_FOUND)
        if any(_course_student_has_marks(cs) for cs in rows):
            return Response(
                {'error': f'{reg_no} already has marks in this course, so they cannot be removed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        for cs in rows:
            cs.delete()
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

        ic = None
        try:
            ic = InstructorCourse.objects.select_related(
                'instructor__user', 'department', 'program'
            ).prefetch_related(
                _marks_with_unit(),
                _marks_with_question(),
                'obe_questions',
            ).get(frontend_id=course_id)
        except InstructorCourse.DoesNotExist:
            # Auto-create InstructorCourse if instructor hasn't logged in yet
            # This allows Dept Admins to finalize courses before instructor initialization
            try:
                # Parse frontend_id: "course-assigned-{CODE}-{PROG}-{SEM}-{YEAR}"
                parts = course_id.split('-')
                if len(parts) < 4 or parts[0] != 'course' or parts[1] != 'assigned':
                    return Response(
                        {'error': f'Invalid course ID format: "{course_id}"'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                course_code = parts[2]
                program_code = parts[3]
                semester = parts[4] if len(parts) > 4 else '1st'
                academic_year = '-'.join(parts[5:]) if len(parts) > 5 else '2024'
                
                # Find the course and instructor from existing assignments
                course = Course.objects.get(code__iexact=course_code)
                program = Program.objects.filter(code__icontains=program_code).first()
                if not program:
                    program = Program.objects.filter(name__icontains=program_code).first()
                
                if not program:
                    return Response(
                        {'error': f'Program "{program_code}" not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Find instructor assigned to this course
                from core.models import CourseAssignment
                assignment = CourseAssignment.objects.select_related(
                    'instructor__user'
                ).filter(
                    course=course,
                    program=program
                ).first()
                
                if not assignment:
                    return Response(
                        {'error': f'No instructor assigned to {course_code} in {program_code}'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Create InstructorCourse with defaults
                ic, _ = InstructorCourse.objects.get_or_create(
                    frontend_id=course_id,
                    defaults={
                        'instructor': assignment.instructor,
                        'code': course.code,
                        'title': course.title,
                        'catalog_course': course,
                        'program': program,
                        'department': program.department,
                        'credit_hours': course.credit_hours or 3,
                        'semester': semester,
                        'academic_year': academic_year,
                        'status': 'active'
                    }
                )
                
                # Reload with relations
                ic = InstructorCourse.objects.select_related(
                    'instructor__user', 'department', 'program', 'catalog_course'
                ).prefetch_related(
                    _marks_with_unit(),
                    _marks_with_question(),
                    'obe_questions',
                    'catalog_course__markscategories__unit_items',
                ).get(id=ic.id)
                
            except Course.DoesNotExist:
                return Response(
                    {'error': f'Course "{course_code}" not found in database'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {'error': f'Failed to auto-initialize course: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

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

        # The admin must say so explicitly to close a course the teacher hasn't
        # handed in (e.g. a teacher who has left). Marks may be incomplete.
        if not ic.submitted_at and request.data.get('overrideNotSubmitted') is not True:
            return Response(
                {'error': 'The teacher has not submitted final marks for this course.', 'code': 'not_submitted'},
                status=status.HTTP_409_CONFLICT
            )

        # ── Validation gate ──────────────────────────────────────────────────
        # Closing is irreversible via API — once FinalResult rows are written
        # and the course is locked, there is no API path back. So we refuse
        # to close (and write nothing) if the course's grading structure is
        # internally inconsistent. The frontend enforces these same rules in
        # its UI, but the backend must never trust that and must re-verify
        # before permanently committing a grade.
        validation_errors = _grading_structure_errors(ic)

        if validation_errors:
            return Response(
                {
                    'error': 'Course cannot be closed — grading structure is invalid.',
                    'details': validation_errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        results_created = _finalize_offering(ic, request.user)

        return Response({
            'courseId':        course_id,
            'courseCode':      ic.code,
            'status':          'closed',
            'closedAt':        ic.closed_at,
            'studentsFinalized': len(results_created),
            'results':         results_created,
        })


def _finalize_offering(ic, user):
    """Writes one course's grades to FinalResult and locks it. Returns the grades written."""
    questions = list(ic.obe_questions.all())
    instructor_name = ic.instructor.user.get_full_name() or ic.instructor.user.email

    # Pre-build CLO meta (description + GA) once for all students
    clo_meta_final = {
        clo_obj.code: {
            'description': clo_obj.description or '',
            'mappedGA': {
                'gaId':    clo_obj.mapped_ga.ga_id,
                'gaTitle': clo_obj.mapped_ga.name,
            } if clo_obj.mapped_ga else None,
        }
        for clo_obj in ic.clos.select_related('mapped_ga').all()
    }

    # Wrap the entire finalization in a single atomic transaction.
    # Without this, a crash or DB error partway through the student loop
    # leaves some FinalResult rows written and others not — but the course
    # remains 'active', so instructors can keep editing marks that are now
    # out of sync with the already-committed transcript rows.
    # More critically: if the loop completes but ic.save() fails, ALL
    # FinalResult rows exist permanently but the course is never locked —
    # instructors can keep editing marks forever against a transcript that
    # already exists. Atomic makes it all-or-nothing: either every
    # FinalResult is written AND the course is locked, or none of it is.
    results_created = []
    with transaction.atomic():
        for student in ic.students.all():
            exact_pct = _sheet_course_total(student)['total']
            pct = round(exact_pct, 2)
            grade_letter, grade_points = _get_grade(exact_pct, ic)
            clo_pcts_raw = _clo_attainments_for_student(student, questions)

            # Store enriched CLO blob so FinalResultsView returns the same
            # shape as StudentCoursesView — description, status, GA all included
            clo_attainments = [
                {
                    'code':        clo,
                    'description': clo_meta_final.get(clo, {}).get('description', ''),
                    'percentage':  pct_val,
                    'attained':    pct_val >= ATTAINMENT_THRESHOLD,
                    'status':      'Attained' if pct_val >= ATTAINMENT_THRESHOLD else 'Not Attained',
                    'mappedGA':    clo_meta_final.get(clo, {}).get('mappedGA'),
                }
                for clo, pct_val in sorted(clo_pcts_raw.items())
            ]
            if student.result_status == 'withdrawn':
                # On the record as W, without a grade or attainment.
                grade_letter, grade_points, clo_attainments = 'W', 0.0, []

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
                    semester=ic.semester or _plan_semester(ic.program_id, ic.code),
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

        # Lock the course — inside atomic so this and FinalResult rows
        # either all commit together or all roll back together.
        ic.status    = 'closed'
        ic.closed_at = timezone.now()
        ic.closed_by = user
        ic.save()

    return results_created


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

        plan_cache = {}
        results = [{
            'regNo':           r.student_reg_no,
            'studentName':     r.student_name,
            'courseCode':      r.course_code,
            'courseTitle':     r.course_title,
            'instructorName':  r.instructor_name,
            'academicYear':    r.academic_year,
            'semester':        r.semester or _plan_semester(r.program_id, r.course_code, plan_cache),
            'creditHours':     r.credit_hours,
            'finalPercentage': r.final_percentage,
            'grade':           r.grade_letter,
            'gradePoints':     r.grade_points,
            'cloAttainments':  r.clo_attainments,
            'finalizedAt':     r.finalized_at,
        } for r in qs.order_by('-finalized_at')]

        return Response({'results': results, 'count': len(results)})


def _graded_students(ic):
    """Roster rows that count in attainment reports: withdrawn students don't."""
    return [s for s in ic.students.all() if s.result_status != 'withdrawn']


def _teacher_lock_message(ic):
    """Why the teacher can't edit this course, or None while they still can."""
    if ic.status == 'closed':
        return f'Course "{ic.code}" is closed (finalized {ic.closed_at}) and cannot be edited.'
    if ic.submitted_at:
        return f'Final marks for "{ic.code}" have been submitted and cannot be edited unless the department sends the course back.'
    if ic.is_historical:
        return f'Course "{ic.code}" is being entered by the department.'
    return None


def _grading_structure_errors(ic):
    """Problems in the marking structure that make a course impossible to grade."""
    errors = []
    categories = list(ic.catalog_course.markscategories.all()) if ic.catalog_course_id else []
    if not categories:
        errors.append('Course has no marks categories defined.')
    else:
        cat_total = round(sum(c.percentage for c in categories), 2)
        if cat_total != 100:
            errors.append(f'Category percentages sum to {cat_total}%, not 100%.')

        for cat in categories:
            units = list(cat.unit_items.all())
            if cat.percentage > 0 and not units:
                errors.append(f'Category "{cat.name}" has {cat.percentage}% weight but no units defined.')
            elif units:
                unit_total = round(sum(u.weightage for u in units), 2)
                if unit_total != 100:
                    errors.append(f'Category "{cat.name}" unit weightages sum to {unit_total}%, not 100%.')

    if not ic.students.exists():
        errors.append('Course has no enrolled students to finalize.')
    return errors


def _submission_check(ic):
    """
    What stands between a teacher and submitting final marks.

    errors  - the marking structure is broken. Blocks.
    missing - a student has no mark in an assessment other students were marked
              in. Blocks until the mark is entered or the student is marked
              absent or withdrawn.
    warnings - an assessment nobody has a mark in (4 quizzes set, 3 marked). The
              teacher probably forgot it, but may not have, so they can accept
              this and it counts as 0.

    A stored 0 is a mark: the sheet can't tell a real 0 from a cleared cell.
    Uses the same marks as _sheet_course_total, so what passes here is what gets graded.
    """
    students = list(ic.students.all())
    to_grade = [s for s in students if not s.result_status]
    unit_marks = {s.pk: {m.unit_item_id: m.score for m in s.marks.all()} for s in to_grade}
    question_marks = {s.pk: {m.question_id: m.score for m in s.obe_marks.all()} for s in to_grade}

    missing = {}
    warnings = []
    for cat in (ic.catalog_course.markscategories.all() if ic.catalog_course_id else []):
        if not (cat.percentage > 0):
            continue
        units_by_no = {ui.unit_no: ui for ui in cat.unit_items.all()}
        for unit_no in range(1, cat.units + 1):
            ui = units_by_no.get(unit_no)
            questions = [q for q in ui.questions.all() if q.course_id == ic.id] if ui else []
            label = f'{cat.name} {unit_no}'

            def entered(student):
                if not questions:
                    return [unit_marks[student.pk].get(ui.id) if ui else None]
                rows = [question_marks[student.pk].get(q.id) for q in questions]
                if len(questions) == 1 and rows[0] is None:
                    rows = [unit_marks[student.pk].get(ui.id)]   # single-question unit: unit mark, as the sheet does
                return rows

            rows_by_student = [(s, entered(s)) for s in to_grade]
            if to_grade and not any(float(v) > 0 for _, rows in rows_by_student for v in rows if v is not None):
                warnings.append(f'{label}: no student has a mark. If you submit, it counts as 0 for everyone.')
                continue
            for s, rows in rows_by_student:
                if any(v is None for v in rows):
                    missing.setdefault(s.reg_no, {'regNo': s.reg_no, 'name': s.name, 'items': []})['items'].append(label)

    return {
        'courseId':     ic.frontend_id,
        'code':         ic.code,
        'title':        ic.title,
        'academicYear': ic.academic_year,
        'errors':       _grading_structure_errors(ic),
        'missing':      list(missing.values()),
        'warnings':     warnings,
        'students':     [{'regNo': s.reg_no, 'name': s.name, 'resultStatus': s.result_status} for s in students],
    }


class InstructorCourseSubmitView(APIView):
    """
    GET  /api/instructor/courses/<frontend_id>/submit/
         What would stop this course being submitted (see _submission_check).
    POST /api/instructor/courses/<frontend_id>/submit/  { "acknowledgeWarnings": true }
         Hands in final marks: the course becomes read-only for the teacher and
         leaves their dashboard. No grades are written; finalizing does that.
    """
    permission_classes = [IsInstructor]

    def _course(self, request, frontend_id):
        profile = get_instructor_profile(request.user)
        if not profile:
            return None
        return prefetch_instructor_course(
            InstructorCourse.objects.filter(instructor=profile, frontend_id=frontend_id)
        ).first()

    def get(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_submission_check(ic))

    def post(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _teacher_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)

        check = _submission_check(ic)
        if check['errors'] or check['missing']:
            return Response({'error': 'Some marks are still missing.', **check}, status=status.HTTP_400_BAD_REQUEST)
        if check['warnings'] and request.data.get('acknowledgeWarnings') is not True:
            return Response({'error': 'Please review the warnings before submitting.', **check},
                            status=status.HTTP_409_CONFLICT)

        ic.submitted_at = timezone.now()
        ic.submission_warnings = check['warnings']
        ic.returned_at = None
        ic.return_note = ''
        ic.save(update_fields=['submitted_at', 'submission_warnings', 'returned_at', 'return_note', 'updated_at'])
        return Response({'courseId': ic.frontend_id, 'submittedAt': ic.submitted_at})


class InstructorStudentStatusView(APIView):
    """
    PATCH /api/instructor/courses/<frontend_id>/student-status/
          { "regNo": "...", "resultStatus": "" | "absent" | "withdrawn" }
    """
    permission_classes = [IsInstructor]

    def patch(self, request, frontend_id):
        profile = get_instructor_profile(request.user)
        ic = InstructorCourse.objects.filter(instructor=profile, frontend_id=frontend_id).first() if profile else None
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _teacher_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)

        result_status = request.data.get('resultStatus', '')
        if result_status not in dict(CourseStudent.RESULT_STATUS_CHOICES):
            return Response({'error': 'resultStatus must be blank, "absent" or "withdrawn"'},
                            status=status.HTTP_400_BAD_REQUEST)
        reg_no = str(request.data.get('regNo', '')).strip()
        updated = CourseStudent.objects.filter(course=ic, reg_no__iexact=reg_no).update(result_status=result_status)
        if not updated:
            return Response({'error': f'Student "{reg_no}" is not in this course'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'regNo': reg_no, 'resultStatus': result_status})


class InstructorPastCoursesView(APIView):
    """
    GET /api/instructor/past-courses/

    The teacher's submitted and finalized courses, newest term first, read-only.
    A finalized course shows its transcript snapshot; a submitted one is still
    computed from its marks.
    """
    permission_classes = [IsInstructor]

    def get(self, request):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response({'error': 'Instructor profile not found'}, status=status.HTTP_403_FORBIDDEN)

        offerings = InstructorCourse.objects.filter(
            models.Q(status='closed') | models.Q(submitted_at__isnull=False),
            instructor=profile,
        ).select_related('program', 'catalog_course').prefetch_related(
            *SHEET_TOTAL_PREFETCH, 'grade_scale', 'final_results',
        )

        data = []
        for ic in sorted(offerings, key=lambda c: _term_sort_key(c.academic_year), reverse=True):
            finals = {r.student_reg_no.strip().upper(): r for r in ic.final_results.all()}
            rows = []
            for st in ic.students.all():
                final = finals.get(st.reg_no.strip().upper())
                if final:
                    pct, grade = final.final_percentage, final.grade_letter
                else:
                    total = _sheet_course_total(st)['total']
                    pct = round(total, 2)
                    grade = 'W' if st.result_status == 'withdrawn' else _get_grade(total, ic)[0]
                rows.append({
                    'regNo': st.reg_no, 'name': st.name, 'resultStatus': st.result_status,
                    'percentage': pct, 'grade': grade,
                })
            data.append({
                'id':           ic.frontend_id,
                'code':         ic.code,
                'title':        ic.title,
                'programCode':  ic.program.code.upper() if ic.program else '',
                'academicYear': ic.academic_year,
                'state':        'finalized' if ic.status == 'closed' else 'submitted',
                'submittedAt':  ic.submitted_at,
                'closedAt':     ic.closed_at,
                'students':     rows,
            })
        return Response(data)


class InstructorPastCourseDetailView(APIView):
    """
    GET /api/instructor/past-courses/<frontend_id>/

    One submitted or finalized course in the same shape as the teacher's current
    courses, so the dashboard can show all of it. Writes stay refused by
    _teacher_lock_message.
    """
    permission_classes = [IsInstructor]

    def get(self, request, frontend_id):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response({'error': 'Instructor profile not found'}, status=status.HTTP_403_FORBIDDEN)
        ic = prefetch_instructor_course(InstructorCourse.objects.filter(
            models.Q(status='closed') | models.Q(submitted_at__isnull=False),
            instructor=profile, frontend_id=frontend_id,
        )).first()
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(InstructorCourseSerializer(ic).data)


class ReturnCourseView(APIView):
    """
    POST /api/admin/return-course/  { "courseId": "...", "note": "..." }

    Sends a submitted course back to its teacher to correct. Not possible once
    the course is finalized: transcripts exist by then.
    """
    permission_classes = [IsDeptAdminOrQA]

    def post(self, request):
        course_id = str(request.data.get('courseId', '')).strip()
        note = str(request.data.get('note', '')).strip()
        if not note:
            return Response({'error': 'Please say what the teacher needs to fix.'}, status=status.HTTP_400_BAD_REQUEST)
        ic = InstructorCourse.objects.filter(frontend_id=course_id).first()
        if not ic:
            return Response({'error': f'Course "{course_id}" not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == 'dept_admin':
            admin_dept = get_admin_department(request.user)
            if not admin_dept or ic.department_id != admin_dept.id:
                return Response({'error': 'You can only send back courses in your own department.'},
                                status=status.HTTP_403_FORBIDDEN)
        if ic.status == 'closed':
            return Response({'error': 'This course is already finalized and cannot be sent back.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not ic.submitted_at:
            return Response({'error': 'This course has not been submitted.'}, status=status.HTTP_400_BAD_REQUEST)

        ic.submitted_at = None
        ic.submission_warnings = []
        ic.returned_at = timezone.now()
        ic.return_note = note
        ic.save(update_fields=['submitted_at', 'submission_warnings', 'returned_at', 'return_note', 'updated_at'])
        return Response({'courseId': ic.frontend_id, 'returnedAt': ic.returned_at})


class InstructorCourseStudentView(APIView):
    """
    POST /api/instructor/courses/<frontend_id>/students/
    An instructor adds students to one of THEIR OWN courses.

    Payload: { "students": [ { "regNo": "...", "name": "..." }, ... ] }

    Why this exists: the instructor UI's "Add Student" used to call
    POST /api/admin/enroll/, which is dept-admin only, so every instructor
    request got a 403. The frontend swallowed it and kept the student in
    browser storage only — the student looked enrolled but never reached the
    server, vanished on another device, and couldn't be given real marks.

    This is deliberately ADD-ONLY. /api/admin/enroll/ is a full sync that
    deletes anyone missing from the list (and CourseStudent -> marks
    CASCADE), so exposing that to instructors would let a stale browser list
    wipe enrolled students and their marks. Removing students stays a dept
    admin action.
    """
    permission_classes = [IsInstructor]

    def post(self, request, frontend_id):
        profile = get_instructor_profile(request.user)
        if not profile:
            return Response({'error': 'Instructor profile not found'},
                            status=status.HTTP_403_FORBIDDEN)

        ic = InstructorCourse.objects.filter(
            instructor=profile, frontend_id=frontend_id
        ).first()
        if not ic:
            # Same response whether the course doesn't exist or belongs to
            # someone else, so course IDs can't be probed.
            return Response({'error': 'Course not found'},
                            status=status.HTTP_404_NOT_FOUND)

        lock = _teacher_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)

        students = request.data.get('students', [])
        if not isinstance(students, list) or not students:
            return Response({'error': 'students must be a non-empty list'},
                            status=status.HTTP_400_BAD_REQUEST)

        added, already = [], []
        for s in students:
            if not isinstance(s, dict):
                continue
            reg_no = str(s.get('regNo', '')).strip().upper()
            if not reg_no:
                continue
            name = str(s.get('name', '')).strip() or reg_no
            _, created = CourseStudent.objects.get_or_create(
                course=ic, reg_no=reg_no, defaults={'name': name},
            )
            (added if created else already).append(reg_no)

        if not added and not already:
            return Response({'error': 'No valid registration numbers supplied'},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({'courseId': frontend_id, 'added': added, 'alreadyEnrolled': already},
                        status=status.HTTP_201_CREATED if added else status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════════
# PAST COURSE ENTRY
# ═══════════════════════════════════════════════════════════════════════════════
#
# Students already studying when the system went live took courses that GA and
# PO attainment must count. The department enters those courses here, doing what
# a teacher does on a current course (CLOs, weightage, questions, marks), through
# the same screen. Finalizing makes one a normal past course: it shows in that
# teacher's Past Courses, in the reports and in the student's dashboard.
# ───────────────────────────────────────────────────────────────────────────────

def _parse_past_term(term):
    """(\'Fall-2024\', term number) for a term that has ended, or (None, reason)."""
    match = re.fullmatch(r'(spring|fall)[-\s]*(\d{4})', str(term or '').strip().lower())
    if not match:
        return None, 'Term must look like Spring-2024 or Fall-2024.'
    season, year = match.group(1).capitalize(), match.group(2)
    index = term_index(season, year)
    if index >= current_term_index():
        return None, f'{season}-{year} has not ended. Use Teacher Assignments for the current term.'
    return f'{season}-{year}', index


def _past_lock_message(ic):
    """Why the department can't edit this course right now, or None."""
    if ic.status == 'closed':
        return f'Course "{ic.code}" is finalized. Reopen it to make corrections.'
    return None


def _past_roster_errors(code, academic_year, reg_nos, department, own_course=None):
    """Students who can't be on this course: unknown, not admitted yet, or already on it this term."""
    known = {s.reg_no.strip().upper(): s for s in AdmissionStudent.objects.filter(department=department)}
    taken = FinalResult.objects.filter(course_code__iexact=code, academic_year__iexact=academic_year)
    other_rosters = CourseStudent.objects.filter(course__code__iexact=code, course__academic_year__iexact=academic_year)
    if own_course:
        taken = taken.exclude(source_course=own_course)
        other_rosters = other_rosters.exclude(course=own_course)
    busy = {r.strip().upper() for r in taken.values_list('student_reg_no', flat=True)}
    busy |= {r.strip().upper() for r in other_rosters.values_list('reg_no', flat=True)}

    season, year = academic_year.split('-')
    term_no = term_index(season, year)
    errors = []
    for reg_no in reg_nos:
        admitted = admission_term_index(reg_no)
        if reg_no not in known:
            errors.append(f'{reg_no} is not a registered student of this department.')
        elif admitted is not None and admitted > term_no:
            errors.append(f'{reg_no} was admitted after {academic_year}.')
        elif reg_no in busy:
            errors.append(f'{reg_no} already has {code} in {academic_year}.')
    return errors


def _clean_past_students(students):
    """[(reg no, name)] from a request's student list, without blanks or repeats."""
    cleaned = {}
    for s in students if isinstance(students, list) else []:
        reg_no = str(s.get('regNo', '')).strip().upper() if isinstance(s, dict) else ''
        if reg_no:
            cleaned.setdefault(reg_no, str(s.get('name', '')).strip() or reg_no)
    return cleaned


def _copy_course_setup(source, target):
    """CLOs and questions of an earlier offering, so they aren't typed again each term."""
    for clo in source.clos.all():
        CLO.objects.create(course=target, code=clo.code, description=clo.description,
                           mapped_ga=clo.mapped_ga, order=clo.order)
    for q in source.obe_questions.all():
        OBEQuestion.objects.create(course=target, unit_item=q.unit_item, frontend_id=q.frontend_id,
                                   category_name=q.category_name, unit_no=q.unit_no, question_name=q.question_name,
                                   max_marks=q.max_marks, mapped_clos=q.mapped_clos, order=q.order)


def _past_course_errors(ic):
    """What stops a past course counting towards GA, on top of the teacher's checks."""
    errors = []
    clos = list(ic.clos.all())
    if not clos:
        errors.append('Add the CLOs of this course.')
    for clo in clos:
        if not clo.mapped_ga_id:
            errors.append(f'{clo.code} is not mapped to a GA.')
    _items, _objs, _clos, graded, unmapped = _ga_question_items(ic)
    if not graded:
        errors.append('Add the questions of each assessment, so GA can be calculated.')
    elif unmapped:
        errors.append(f'{unmapped} question{"s are" if unmapped != 1 else " is"} not mapped to a CLO with a GA.')
    return errors


class PastCourseBase(APIView):
    """A department's own past courses."""
    permission_classes = [IsDeptAdmin]

    def _course(self, request, frontend_id):
        department = get_admin_department(request.user)
        if not department:
            return None
        return prefetch_instructor_course(InstructorCourse.objects.filter(
            is_historical=True, department=department, frontend_id=frontend_id,
        )).select_related('instructor__user').first()


class PastCourseListView(PastCourseBase):
    """
    GET  /api/admin/past-courses/   Every past course of the department, newest term first.
    POST /api/admin/past-courses/   { programId, courseCode, academicYear, teacherId, students: [{regNo, name}] }
         Creates the course with its roster. CLOs and questions are copied from the
         latest offering of the same course, if there is one.
    """

    def get(self, request):
        department = get_admin_department(request.user)
        if not department:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)
        offerings = InstructorCourse.objects.filter(is_historical=True, department=department).select_related(
            'program', 'instructor__user').prefetch_related('students', 'clos')
        plan_cache = {}
        rows = [{
            'id':           ic.frontend_id,
            'code':         ic.code,
            'title':        ic.title,
            'programId':    ic.program.code.lower() if ic.program else '',
            'programCode':  ic.program.code.upper() if ic.program else '',
            'academicYear': ic.academic_year,
            'semester':     ic.semester or _plan_semester(ic.program_id, ic.code, plan_cache),
            'teacherName':  ic.instructor.user.get_full_name() or ic.instructor.user.username,
            'state':        'finalized' if ic.status == 'closed' else 'draft',
            'studentCount': len(ic.students.all()),
            'cloCount':     len(ic.clos.all()),
            'closedAt':     ic.closed_at,
        } for ic in offerings]
        rows.sort(key=lambda r: r['code'])
        rows.sort(key=lambda r: _term_sort_key(r['academicYear']), reverse=True)
        return Response(rows)

    def post(self, request):
        department = get_admin_department(request.user)
        if not department:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data

        term, term_no = _parse_past_term(data.get('academicYear'))
        if not term:
            return Response({'error': term_no}, status=status.HTTP_400_BAD_REQUEST)
        program = Program.objects.filter(code__iexact=str(data.get('programId', '')).strip(), department=department).first()
        if not program:
            return Response({'error': 'Choose a programme of your department.'}, status=status.HTTP_400_BAD_REQUEST)
        code = str(data.get('courseCode', '')).strip()
        catalog = Course.objects.filter(code__iexact=code, department=department, program=program).first()
        if not catalog:
            return Response({'error': f'"{code}" is not in the {program.code.upper()} course catalog.'},
                            status=status.HTTP_400_BAD_REQUEST)
        teacher = InstructorProfile.objects.filter(employee_id=str(data.get('teacherId', '')).strip()).first()
        if not teacher:
            return Response({'error': 'Choose the teacher who taught this course.'}, status=status.HTTP_400_BAD_REQUEST)

        if InstructorCourse.objects.filter(instructor=teacher, code__iexact=catalog.code,
                                           program=program, academic_year__iexact=term).exists():
            return Response({'error': f'{catalog.code} in {term} already exists for this teacher.'},
                            status=status.HTTP_400_BAD_REQUEST)

        students = _clean_past_students(data.get('students'))
        if not students:
            return Response({'error': 'Choose the students who took this course.'}, status=status.HTTP_400_BAD_REQUEST)
        roster_errors = _past_roster_errors(catalog.code, term, list(students), department)
        if roster_errors:
            return Response({'error': ' '.join(roster_errors)}, status=status.HTTP_400_BAD_REQUEST)

        earlier = InstructorCourse.objects.filter(code__iexact=catalog.code, program=program).prefetch_related(
            'clos', 'obe_questions')
        earlier = [c for c in earlier if c.clos.all()]
        with transaction.atomic():
            ic = InstructorCourse.objects.create(
                instructor=teacher,
                frontend_id=f'past-{catalog.code}-{teacher.employee_id}-{program.code.lower()}-{term}',
                catalog_course=catalog,
                code=catalog.code,
                title=catalog.title,
                course_type='Lab' if catalog.subtype == 'lab' else 'Theory',
                department=department,
                program=program,
                credit_hours=catalog.credit_hours,
                semester=_plan_semester(program.id, catalog.code) or '',
                academic_year=term,
                is_historical=True,
            )
            CourseStudent.objects.bulk_create([
                CourseStudent(course=ic, reg_no=reg_no, name=name) for reg_no, name in students.items()
            ])
            if earlier:
                _copy_course_setup(max(earlier, key=lambda c: _term_sort_key(c.academic_year)), ic)
        return Response({'id': ic.frontend_id}, status=status.HTTP_201_CREATED)


class PastCourseEligibleStudentsView(PastCourseBase):
    """
    GET /api/admin/past-courses/eligible-students/?programId=&courseCode=&academicYear=

    Students of a programme who could have taken a course in a past term. `suggested`
    is the batch whose semester that term matches the course's place in the plan;
    anyone else on the list would be a retake or an off-plan course.
    """

    def get(self, request):
        department = get_admin_department(request.user)
        if not department:
            return Response({'error': 'Admin profile not found'}, status=status.HTTP_403_FORBIDDEN)
        term, term_no = _parse_past_term(request.query_params.get('academicYear'))
        if not term:
            return Response({'error': term_no}, status=status.HTTP_400_BAD_REQUEST)
        program = Program.objects.filter(code__iexact=request.query_params.get('programId', '').strip(),
                                         department=department).first()
        code = request.query_params.get('courseCode', '').strip()
        if not program or not code:
            return Response({'error': 'programId and courseCode are required'}, status=status.HTTP_400_BAD_REQUEST)

        busy = {r.strip().upper() for r in FinalResult.objects.filter(
            course_code__iexact=code, academic_year__iexact=term).values_list('student_reg_no', flat=True)}
        busy |= {r.strip().upper() for r in CourseStudent.objects.filter(
            course__code__iexact=code, course__academic_year__iexact=term).values_list('reg_no', flat=True)}
        plan_semester = _plan_semester(program.id, code)

        rows = []
        for st in AdmissionStudent.objects.filter(program=program).order_by('reg_no'):
            admitted = admission_term_index(st.reg_no)
            if st.reg_no.strip().upper() in busy or (admitted is not None and admitted > term_no):
                continue
            semester = semester_label(term_no - admitted + 1) if admitted is not None else ''
            rows.append({'regNo': st.reg_no, 'name': st.name, 'semesterInTerm': semester,
                         'suggested': bool(semester) and semester == plan_semester})
        return Response({'semester': plan_semester or '', 'students': rows})


class PastCourseSaveView(InstructorCourseView, PastCourseBase):
    """
    POST /api/admin/past-courses/save/   { courses: [...] }

    The course screen's save. Same as a teacher's, under the course's own teacher,
    except the course's identity and roster can't be changed by what is sent.
    """
    http_method_names = ['post', 'options']

    def get_permissions(self):
        return [IsDeptAdmin()]

    def post(self, request, frontend_id=None):
        courses = request.data.get('courses', [])
        if not isinstance(courses, list) or len(courses) != 1 or not isinstance(courses[0], dict):
            return Response({'error': 'Send one course at a time.'}, status=status.HTTP_400_BAD_REQUEST)
        ic = self._course(request, courses[0].get('id', ''))
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        roster = {s.reg_no.strip().upper() for s in ic.students.all()}
        sent = dict(courses[0])
        sent.update(
            departmentId=ic.department.dept_id,
            programId=ic.program.code if ic.program else None,
            academicYear=ic.academic_year,
            code=ic.code,
            title=ic.title,
            students=[s for s in sent.get('students', [])
                      if isinstance(s, dict) and str(s.get('regNo', '')).strip().upper() in roster],
        )
        return self._save_courses([sent], ic.instructor, _past_lock_message)


class PastCourseDetailView(PastCourseBase):
    """
    GET    /api/admin/past-courses/<id>/   The course in the same shape as a teacher's course.
    DELETE /api/admin/past-courses/<id>/   Discards a course that isn't finalized, with its marks.
    """

    def get(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(InstructorCourseSerializer(ic).data)

    def delete(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _past_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)
        ic.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PastCourseStudentsView(PastCourseBase):
    """POST /api/admin/past-courses/<id>/students/   { students: [{regNo, name}] }  Add-only."""

    def post(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _past_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)
        students = _clean_past_students(request.data.get('students'))
        if not students:
            return Response({'error': 'No valid registration numbers supplied'}, status=status.HTTP_400_BAD_REQUEST)
        on_roster = {s.reg_no.strip().upper() for s in ic.students.all()}
        new = {r: n for r, n in students.items() if r not in on_roster}
        errors = _past_roster_errors(ic.code, ic.academic_year, list(new), ic.department, own_course=ic)
        if errors:
            return Response({'error': ' '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)
        for reg_no, name in new.items():
            CourseStudent.objects.create(course=ic, reg_no=reg_no, name=name)
        return Response({'courseId': frontend_id, 'added': list(new)}, status=status.HTTP_201_CREATED)


class PastCourseStudentStatusView(PastCourseBase):
    """PATCH /api/admin/past-courses/<id>/student-status/   { regNo, resultStatus }"""

    def patch(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _past_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)
        result_status = request.data.get('resultStatus', '')
        if result_status not in dict(CourseStudent.RESULT_STATUS_CHOICES):
            return Response({'error': 'resultStatus must be blank, "absent" or "withdrawn"'},
                            status=status.HTTP_400_BAD_REQUEST)
        reg_no = str(request.data.get('regNo', '')).strip()
        if not CourseStudent.objects.filter(course=ic, reg_no__iexact=reg_no).update(result_status=result_status):
            return Response({'error': f'Student "{reg_no}" is not in this course'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'regNo': reg_no, 'resultStatus': result_status})


class PastCourseFinalizeView(PastCourseBase):
    """
    GET  /api/admin/past-courses/<id>/submit/   What stops this course being finalized.
    POST /api/admin/past-courses/<id>/submit/   { acknowledgeWarnings }  Finalizes it.
    """

    @staticmethod
    def _check(ic):
        check = _submission_check(ic)
        check['errors'] = check['errors'] + _past_course_errors(ic)
        return check

    def get(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._check(ic))

    def post(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        lock = _past_lock_message(ic)
        if lock:
            return Response({'error': lock}, status=status.HTTP_400_BAD_REQUEST)
        check = self._check(ic)
        if check['errors'] or check['missing']:
            return Response({'error': 'Some marks or mappings are still missing.', **check},
                            status=status.HTTP_400_BAD_REQUEST)
        if check['warnings'] and request.data.get('acknowledgeWarnings') is not True:
            return Response({'error': 'Please review the warnings before finalizing.', **check},
                            status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            ic.submitted_at = timezone.now()
            ic.submission_warnings = check['warnings']
            _finalize_offering(ic, request.user)
        return Response({'courseId': ic.frontend_id, 'closedAt': ic.closed_at})


class PastCourseReopenView(PastCourseBase):
    """
    POST /api/admin/past-courses/<id>/reopen/

    Takes a finalized past course back to a draft, to correct a typing mistake. Its
    grades leave the transcript until it is finalized again. Only for past courses
    entered here: a course a teacher ran stays final.
    """

    def post(self, request, frontend_id):
        ic = self._course(request, frontend_id)
        if not ic:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        if ic.status != 'closed':
            return Response({'error': 'This course is not finalized.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            FinalResult.objects.filter(source_course=ic).delete()
            ic.status = 'active'
            ic.closed_at = None
            ic.closed_by = None
            ic.submitted_at = None
            ic.submission_warnings = []
            ic.save()
        return Response({'courseId': ic.frontend_id, 'state': 'draft'})
