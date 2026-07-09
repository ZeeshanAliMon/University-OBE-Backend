from core.models import CourseAssignment, InstructorCourse

created = 0
for a in CourseAssignment.objects.select_related('instructor','course','program'):
    prog = a.program.code.lower() if a.program else 'all'
    term = f'-{a.academic_year.lower().replace(" ","")}' if a.academic_year else ''
    fid  = f'course-assigned-{a.course.code}-{a.instructor.employee_id}-{prog}{term}'
    _, was_created = InstructorCourse.objects.get_or_create(
        instructor=a.instructor,
        frontend_id=fid,
        defaults=dict(
            code=a.course.code, title=a.course.title,
            course_type='Theory', department=a.course.department,
            program=a.program, credit_hours=a.course.credit_hours or 3,
            clo_count=0, selected_grading_system='ready1',
            frontend_id=fid, semester='', academic_year=a.academic_year,
        )
    )
    if was_created:
        created += 1
        print(f'Created stub: {fid}')
