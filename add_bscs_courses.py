from core.models import Course, Department, Program

dept = Department.objects.get(dept_id='computing')
prog = Program.objects.get(code__iexact='bscs')

courses = [
    # code, title, type, credits
    ('CMC111', 'Programming Fundamentals', 'core', 3),
    ('GER111', 'Application of Information & Communication Technologies', 'core', 3),
    ('GER121', 'Functional English', 'core', 3),
    ('GER131', 'Calculus and Analytic Geometry', 'core', 3),
    ('GER141', 'Islamic Studies', 'core', 2),
    ('GER151', 'Natural Science (Applied Physics)', 'core', 3),
    ('MTE111', 'Multivariable Calculus', 'core', 3),
    ('CMC112', 'Object Oriented Programming', 'core', 3),
    ('CMC121', 'Digital Logic Design', 'core', 3),
    ('GER122', 'Expository Writing', 'core', 3),
    ('GER132', 'Discrete Structures', 'core', 3),
    ('GER142', 'Ideology and Constitution of Pakistan', 'core', 2),
    ('MTE212', 'Probability & Statistics', 'core', 3),
    ('CMC222', 'Computer Organization & Assembly Language', 'core', 3),
    ('CMC251', 'Data Structures', 'core', 3),
    ('CSC252', 'Theory of Automata', 'core', 3),
    ('CMC261', 'Computer Networks', 'core', 3),
    ('MTE213', 'Linear Algebra', 'core', 3),
    ('MTE221', 'Technical & Business Writing', 'core', 3),
    ('CSC223', 'Computer Architecture', 'core', 3),
    ('CMC241', 'Operating Systems', 'core', 3),
    ('CMC253', 'Analysis of Algorithms', 'core', 3),
    ('GER261', 'Introduction to Management', 'core', 3),
    ('CMC331', 'Database Systems', 'core', 3),
    ('CSC354', 'Compiler Construction', 'core', 3),
    ('CMC362', 'Information Security', 'core', 3),
    ('CMC371', 'Software Engineering', 'core', 3),
    ('CSC332', 'Advance Database Management Systems', 'core', 3),
    ('CMC381', 'Artificial Intelligence', 'core', 3),
    ('CSC382', 'HCI & Computer Graphics', 'core', 3),
    ('CSC311', 'Introduction to Marketing', 'core', 3),
    ('CSC442', 'Parallel & Distributed Computing', 'core', 3),
    ('GER462', 'Technopreneurship', 'core', 3),
    ('CMC491', 'Final Year Project - I', 'core', 3),
    ('GER443', 'Civics and Community Engagement', 'core', 3),
    ('GER463', 'Professional Practices', 'core', 3),
    ('CMC492', 'Final Year Project - II', 'core', 3),
    ('CSC467', 'Internet of Things', 'elective', 3),
    ('CSC436', 'Data Warehousing & Data Mining', 'elective', 3),
    ('CSC479', 'Machine Learning', 'elective', 3),
    ('CSC435', 'Mobile Application Development', 'elective', 3),
    ('CSC321', 'Embedded Systems', 'elective', 3),
    ('CSC478', 'Routing and Switching', 'elective', 3),
]

created = skipped = 0
for code, title, ctype, credits in courses:
    _, was_created = Course.objects.get_or_create(
        code=code,
        program=prog,
        defaults=dict(
            title=title,
            type=ctype,
            department=dept,
            credit_hours=credits,
        )
    )
    if was_created:
        created += 1
        print(f'  Created: {code} — {title}')
    else:
        skipped += 1
        print(f'  Exists:  {code}')

print(f'\nDone — {created} created, {skipped} already existed')
print(f'BSCS total: {Course.objects.filter(program=prog).count()} courses')
