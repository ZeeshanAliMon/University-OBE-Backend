from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .models import Department, Program, GraduateAttribute
from .serializers import (
    DepartmentSerializer, ProgramSerializer,
    GraduateAttributeSerializer, UserSerializer
)


# ─── Auth ─────────────────────────────────────────────────────────────────────


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': 'Invalid username or password'}, status=401)
    refresh = RefreshToken.for_user(user)
    return Response({
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
        'user': {
            'id':        user.id,
            'username':  user.username,
            'email':     user.email,
            'user_type': user.role,      # student / teacher / QA
        }
    })
# ─── Main data endpoint — matches your current data.json shape ────────────────

@api_view(['GET'])
@permission_classes([AllowAny])   # swap to IsAuthenticated once login is wired
def all_data(request):
    """
    Single endpoint that returns everything the frontend needs on load.
    Matches exactly:
    {
        departments: [...],
        programs:    [...],
        gas:         [...]
    }
    """
    departments = Department.objects.all()
    programs    = Program.objects.prefetch_related(
                    'objectives__ga_mappings__graduate_attribute'
                  ).all()
    gas         = GraduateAttribute.objects.all()

    return Response({
        'departments': DepartmentSerializer(departments, many=True).data,
        'programs':    ProgramSerializer(programs, many=True).data,
        'gas':         GraduateAttributeSerializer(gas, many=True).data,
    })


# ─── Individual endpoints (for updates from QA dashboard) ────────────────────

@api_view(['GET', 'PUT'])
def department_detail(request, dept_id):
    """
    GET  /api/departments/cs/   → fetch one department
    PUT  /api/departments/cs/   → update vision / mission
    """
    try:
        dept = Department.objects.get(code=dept_id.upper())
    except Department.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        return Response(DepartmentSerializer(dept).data)

    if request.method == 'PUT':
        dept.vision  = request.data.get('vision',  dept.vision)
        dept.mission = request.data.get('mission', dept.mission)
        dept.save()
        return Response(DepartmentSerializer(dept).data)


@api_view(['GET', 'PATCH'])
@permission_classes([AllowAny])
def program_detail(request, program_id):
    try:
        program = Program.objects.prefetch_related(
            'objectives__ga_mappings__graduate_attribute'
        ).get(code=program_id.upper())
    except Program.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        return Response(ProgramSerializer(program, context={'request': request}).data)

    if request.method == 'PATCH':
        serializer = ProgramSerializer(
            program,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
@api_view(['GET'])
@permission_classes([AllowAny])
def departments_list(request):
    departments = Department.objects.all()
    return Response(DepartmentSerializer(departments, many=True).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def programs_list(request):
    programs = Program.objects.prefetch_related(
        'objectives__ga_mappings__graduate_attribute'
    ).all()
    return Response(ProgramSerializer(programs, many=True).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def gas_list(request):
    gas = GraduateAttribute.objects.all()
    return Response(GraduateAttributeSerializer(gas, many=True).data)