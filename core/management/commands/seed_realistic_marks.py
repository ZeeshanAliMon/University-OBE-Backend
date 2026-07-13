"""
Seed realistic marks for all assigned courses in OBE system.
This populates:
1. InstructorCourse records (if not exist)
2. CourseStudent enrollments
3. OBEQuestion assessments
4. OBEStudentMark grades
5. FinalResult transcripts
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import (
    User, Student, Course, CLO, InstructorCourse, 
    CourseStudent, OBEQuestion, OBEStudentMark, FinalResult,
    CourseAssignment, Instructor, Program, Department
)
from django.contrib.auth.hashers import make_password
import random
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Seed realistic marks and grades for all courses'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting realistic marks seeding...'))
        
        try:
            with transaction.atomic():
                # 1. Get or create test data
                self.stdout.write('Step 1: Ensuring test data exists...')
                dept_comp = self.get_or_create_dept('Computing')
                dept_bus = self.get_or_create_dept('Business')
                
                prog_cs = self.get_or_create_program('BSCS', 'BS Computer Science', dept_comp)
                prog_bba = self.get_or_create_program('BBA', 'BS Business Admin', dept_bus)
                
                # 2. Create courses with CLOs if not exist
                self.stdout.write('Step 2: Creating courses with CLOs...')
                courses = self.create_courses_with_clos()
                
                # 3. Create instructors
                self.stdout.write('Step 3: Creating instructors...')
                instructors = self.create_instructors()
                
                # 4. Create CourseAssignments
                self.stdout.write('Step 4: Creating course assignments...')
                assignments = self.create_course_assignments(courses, instructors, [prog_cs, prog_bba])
                
                # 5. Create InstructorCourse instances
                self.stdout.write('Step 5: Creating instructor courses...')
                instructor_courses = self.create_instructor_courses(assignments)
                
                # 6. Get or create students
                self.stdout.write('Step 6: Creating students...')
                students = self.create_students([prog_cs, prog_bba])
                
                # 7. Enroll students in courses
                self.stdout.write('Step 7: Enrolling students in courses...')
                self.enroll_students(instructor_courses, students)
                
                # 8. Create assessment questions
                self.stdout.write('Step 8: Creating assessment questions...')
                self.create_assessment_questions(courses)
                
                # 9. Generate realistic marks for students
                self.stdout.write('Step 9: Generating realistic student marks...')
                self.generate_realistic_marks(instructor_courses, students)
                
                # 10. Create final results
                self.stdout.write('Step 10: Creating final transcripts...')
                self.create_final_results(instructor_courses, students)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during seeding: {str(e)}'))
            raise
        
        self.stdout.write(self.style.SUCCESS('✅ Seeding completed successfully!'))
        self.print_summary()

    def get_or_create_dept(self, name):
        dept, created = Department.objects.get_or_create(
            name=name,
            defaults={'vision': f'{name} Department', 'mission': f'{name} Excellence'}
        )
        if created:
            self.stdout.write(f'  Created department: {name}')
        return dept

    def get_or_create_program(self, code, name, dept):
        prog, created = Program.objects.get_or_create(
            code=code,
            defaults={'name': name, 'department': dept}
        )
        if created:
            self.stdout.write(f'  Created program: {code}')
        return prog

    def create_courses_with_clos(self):
        """Create courses with CLOs"""
        courses_data = [
            ('CS101', 'Introduction to Programming', 'core', 3, 'Computing'),
            ('CS201', 'Data Structures', 'core', 3, 'Computing'),
            ('CS301', 'Database Systems', 'core', 3, 'Computing'),
            ('CS401', 'Web Development', 'elective', 3, 'Computing'),
            ('BUS101', 'Business Fundamentals', 'core', 3, 'Business'),
            ('BUS201', 'Marketing Management', 'core', 3, 'Business'),
        ]
        
        courses = []
        for code, title, course_type, credits, dept_name in courses_data:
            dept = Department.objects.get(name=dept_name)
            course, created = Course.objects.get_or_create(
                code=code,
                defaults={
                    'title': title,
                    'course_type': course_type,
                    'credit_hours': credits,
                    'department': dept
                }
            )
            
            if created:
                self.stdout.write(f'  Created course: {code}')
                # Create CLOs for course
                clos = [
                    ('CLO1', f'Understand fundamentals of {title}'),
                    ('CLO2', f'Apply concepts in {title}'),
                    ('CLO3', f'Analyze problems in {title}'),
                    ('CLO4', f'Create solutions in {title}'),
                ]
                for clo_code, description in clos:
                    CLO.objects.get_or_create(
                        course=course,
                        clo_code=clo_code,
                        defaults={'description': description}
                    )
            
            courses.append(course)
        
        return courses

    def create_instructors(self):
        """Create instructor users and profiles"""
        instructors_data = [
            ('ali.hassan@iqra.edu.pk', 'Ali', 'Hassan', 'Computing'),
            ('fatima.khan@iqra.edu.pk', 'Fatima', 'Khan', 'Computing'),
            ('ahmed.raza@iqra.edu.pk', 'Ahmed', 'Raza', 'Business'),
            ('sara.malik@iqra.edu.pk', 'Sara', 'Malik', 'Business'),
        ]
        
        instructors = []
        for email, first, last, dept_name in instructors_data:
            dept = Department.objects.get(name=dept_name)
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'role': 'instructor',
                    'password': make_password('instpass123')
                }
            )
            
            if created:
                self.stdout.write(f'  Created instructor: {email}')
                instructor, _ = Instructor.objects.get_or_create(
                    user=user,
                    defaults={'designation': 'Lecturer', 'department': dept}
                )
            else:
                instructor = Instructor.objects.get(user=user)
            
            instructors.append(instructor)
        
        return instructors

    def create_course_assignments(self, courses, instructors, programs):
        """Create course assignments (who teaches what)"""
        assignments = []
        
        # Assign CS courses to CS instructors
        cs_instructors = instructors[:2]
        cs_courses = courses[:4]
        cs_program = programs[0]
        
        for i, course in enumerate(cs_courses):
            instructor = cs_instructors[i % len(cs_instructors)]
            assignment, created = CourseAssignment.objects.get_or_create(
                instructor=instructor,
                course=course,
                program=cs_program,
                defaults={'academic_year': 'Fall-2024'}
            )
            if created:
                self.stdout.write(f'  Assigned {course.code} to {instructor.user.email}')
            assignments.append(assignment)
        
        # Assign BUS courses to BUS instructors
        bus_instructors = instructors[2:]
        bus_courses = courses[4:]
        bus_program = programs[1]
        
        for i, course in enumerate(bus_courses):
            instructor = bus_instructors[i % len(bus_instructors)]
            assignment, created = CourseAssignment.objects.get_or_create(
                instructor=instructor,
                course=course,
                program=bus_program,
                defaults={'academic_year': 'Fall-2024'}
            )
            if created:
                self.stdout.write(f'  Assigned {course.code} to {instructor.user.email}')
            assignments.append(assignment)
        
        return assignments

    def create_instructor_courses(self, assignments):
        """Create InstructorCourse instances from assignments"""
        instructor_courses = []
        
        for assignment in assignments:
            ic, created = InstructorCourse.objects.get_or_create(
                instructor=assignment.instructor,
                course=assignment.course,
                program=assignment.program,
                defaults={
                    'department': assignment.program.department,
                    'semester': '1st',
                    'academic_year': 'Fall-2024',
                    'status': 'active'
                }
            )
            if created:
                self.stdout.write(f'  Created InstructorCourse: {assignment.course.code}')
            instructor_courses.append(ic)
        
        return instructor_courses

    def create_students(self, programs):
        """Create student users and enrollments"""
        students_data = [
            ('ahmed.student@student.iqra.edu.pk', 'Ahmed', 'Student1', 'FA24-BSCS-001', programs[0]),
            ('fatima.student@student.iqra.edu.pk', 'Fatima', 'Student2', 'FA24-BSCS-002', programs[0]),
            ('ali.student@student.iqra.edu.pk', 'Ali', 'Student3', 'FA24-BSCS-003', programs[0]),
            ('sara.student@student.iqra.edu.pk', 'Sara', 'Student4', 'FA24-BSCS-004', programs[0]),
            ('zara.student@student.iqra.edu.pk', 'Zara', 'Student5', 'FA24-BSCS-005', programs[0]),
            ('hamza.student@student.iqra.edu.pk', 'Hamza', 'Student6', 'FA24-BBA-001', programs[1]),
            ('aisha.student@student.iqra.edu.pk', 'Aisha', 'Student7', 'FA24-BBA-002', programs[1]),
            ('hassan.student@student.iqra.edu.pk', 'Hassan', 'Student8', 'FA24-BBA-003', programs[1]),
        ]
        
        students = []
        for email, first, last, reg_no, program in students_data:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'role': 'student',
                    'password': make_password('stupass123')
                }
            )
            
            if created:
                self.stdout.write(f'  Created student: {email}')
                student, _ = Student.objects.get_or_create(
                    user=user,
                    defaults={
                        'reg_no': reg_no,
                        'program': program,
                        'batch_year': 2024
                    }
                )
            else:
                student = Student.objects.get(user=user)
            
            students.append(student)
        
        return students

    def enroll_students(self, instructor_courses, students):
        """Enroll students in courses"""
        cs_students = students[:5]
        bus_students = students[5:]
        
        for ic in instructor_courses:
            if ic.program.code == 'BSCS':
                for student in cs_students:
                    CourseStudent.objects.get_or_create(
                        instructor_course=ic,
                        student=student
                    )
            else:
                for student in bus_students:
                    CourseStudent.objects.get_or_create(
                        instructor_course=ic,
                        student=student
                    )
        
        self.stdout.write('  Students enrolled in courses')

    def create_assessment_questions(self, courses):
        """Create OBE assessment questions"""
        for course in courses:
            clos = CLO.objects.filter(course=course)
            
            for i, clo in enumerate(clos):
                num_questions = random.randint(2, 4)
                for q in range(num_questions):
                    OBEQuestion.objects.get_or_create(
                        course=course,
                        clo=clo,
                        question_number=q + 1,
                        defaults={
                            'question_text': f'{course.code} - {clo.clo_code} - Question {q+1}',
                            'max_marks': 10
                        }
                    )
        
        self.stdout.write('  Created assessment questions')

    def generate_realistic_marks(self, instructor_courses, students):
        """Generate realistic marks for students"""
        mark_count = 0
        
        for ic in instructor_courses:
            # Get questions for this course
            questions = OBEQuestion.objects.filter(course=ic.course)
            if not questions.exists():
                continue
            
            # Get enrolled students
            enrollments = CourseStudent.objects.filter(instructor_course=ic)
            
            for enrollment in enrollments:
                # Generate marks for each question
                for question in questions:
                    # Realistic score distribution (70% 70-90, 20% 50-70, 10% 90-100)
                    rand = random.random()
                    if rand < 0.70:
                        score = random.randint(70, 90)
                    elif rand < 0.90:
                        score = random.randint(50, 70)
                    else:
                        score = random.randint(90, 100)
                    
                    OBEStudentMark.objects.get_or_create(
                        student=enrollment.student,
                        question=question,
                        defaults={'score': score}
                    )
                    mark_count += 1
        
        self.stdout.write(f'  Generated {mark_count} realistic marks')

    def create_final_results(self, instructor_courses, students):
        """Create final result transcripts"""
        result_count = 0
        
        for ic in instructor_courses:
            enrollments = CourseStudent.objects.filter(instructor_course=ic)
            
            for enrollment in enrollments:
                student = enrollment.student
                
                # Calculate average score from marks
                marks = OBEStudentMark.objects.filter(
                    student=student,
                    question__course=ic.course
                ).values_list('score', flat=True)
                
                if marks:
                    final_percentage = sum(marks) / len(marks)
                    
                    # Determine grade
                    if final_percentage >= 90:
                        grade = 'A'
                    elif final_percentage >= 80:
                        grade = 'B'
                    elif final_percentage >= 70:
                        grade = 'C'
                    elif final_percentage >= 60:
                        grade = 'D'
                    else:
                        grade = 'F'
                    
                    # Get CLO attainments (by averaging marks per CLO)
                    clo_attainments = {}
                    clos = CLO.objects.filter(course=ic.course)
                    for clo in clos:
                        clo_marks = OBEStudentMark.objects.filter(
                            student=student,
                            question__clo=clo
                        ).values_list('score', flat=True)
                        if clo_marks:
                            clo_attainments[clo.clo_code] = round(sum(clo_marks) / len(clo_marks), 1)
                    
                    FinalResult.objects.get_or_create(
                        student=student,
                        course=ic.course,
                        academic_year=ic.academic_year,
                        defaults={
                            'final_percentage': round(final_percentage, 1),
                            'grade_letter': grade,
                            'clo_attainments': clo_attainments,
                            'instructor_name': ic.instructor.user.get_full_name(),
                            'finalized_at': datetime.now()
                        }
                    )
                    result_count += 1
        
        self.stdout.write(f'  Created {result_count} final result records')

    def print_summary(self):
        """Print summary of seeded data"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('SEEDING SUMMARY')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Courses: {Course.objects.count()}')
        self.stdout.write(f'Students: {Student.objects.count()}')
        self.stdout.write(f'Instructors: {Instructor.objects.count()}')
        self.stdout.write(f'InstructorCourses: {InstructorCourse.objects.count()}')
        self.stdout.write(f'CourseStudents (Enrollments): {CourseStudent.objects.count()}')
        self.stdout.write(f'OBEQuestions: {OBEQuestion.objects.count()}')
        self.stdout.write(f'OBEStudentMarks: {OBEStudentMark.objects.count()}')
        self.stdout.write(f'FinalResults (Transcripts): {FinalResult.objects.count()}')
        
        self.stdout.write('='*60 + '\n')

