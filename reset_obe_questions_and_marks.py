"""
Full reset of OBE questions and ALL student marks.

WHAT IT DELETES
    * every OBEQuestion          (3,600+ bulk-seeded rows)
    * every OBEStudentMark       (per-question marks)
    * every StudentMark          (per-unit marks)

WHAT IT KEEPS
    Everything that defines the marking STRUCTURE, so instructors don't have
    to rebuild it:
        * MarksCategory  - Assignments / Quizzes / Mid Term / Final, with
                           their percentages and unit counts
        * UnitItem       - the units themselves, with passing marks,
                           total marks and weightages
        * CourseStudent  - course rosters (students stay enrolled)
        * CLO            - course learning outcomes
    Courses, programs, departments, instructors and students are untouched.

AFTER RUNNING
    Every unit has zero questions. The instructor UI creates a single fresh
    question when a unit is opened, and the "Add Question" button adds more
    from there — which is the behaviour you asked for.

    UnitItem.total_marks is deliberately left as-is: the frontend seeds that
    first auto-created question with the unit's total marks, so zeroing it
    here would give you a 0-mark question instead of a sensible default.

!! THIS CANNOT BE UNDONE !!
    Back up first — it's a single SQLite file:
        cp db.sqlite3 "db.sqlite3.backup-$(date +%F-%H%M)"

USAGE
    Dry run (counts only, writes nothing):
        python manage.py shell -c "exec(open('reset_obe_questions_and_marks.py').read())"

    Apply for real:
        APPLY=1 python manage.py shell -c "exec(open('reset_obe_questions_and_marks.py').read())"
"""
import os
from django.db import transaction
from core.models import (
    OBEQuestion, OBEStudentMark, StudentMark,
    MarksCategory, UnitItem, CourseStudent, CLO,
)

APPLY = os.environ.get('APPLY') == '1'

q_count      = OBEQuestion.objects.count()
obe_marks    = OBEStudentMark.objects.count()
unit_marks   = StudentMark.objects.count()

print("=" * 68)
print("RESET OBE QUESTIONS + ALL STUDENT MARKS")
print("MODE:", "APPLY — deleting for real" if APPLY else "DRY RUN — nothing will be written")
print("=" * 68)

print("\nWILL DELETE")
print(f"  OBE Questions .............. {q_count:>7}")
print(f"  OBE Student Marks .......... {obe_marks:>7}   (per-question)")
print(f"  Student Marks .............. {unit_marks:>7}   (per-unit)")
print(f"  {'':.<30} {'-'*7}")
print(f"  total rows removed ......... {q_count + obe_marks + unit_marks:>7}")

print("\nWILL KEEP (marking structure stays intact)")
print(f"  Marks Categories ........... {MarksCategory.objects.count():>7}")
print(f"  Unit Items ................. {UnitItem.objects.count():>7}")
print(f"  Course Students (rosters) .. {CourseStudent.objects.count():>7}")
print(f"  CLOs ....................... {CLO.objects.count():>7}")

if not APPLY:
    print("\nNothing written.")
    print("Back up first:  cp db.sqlite3 \"db.sqlite3.backup-$(date +%F-%H%M)\"")
    print("Then apply:     APPLY=1 python manage.py shell -c \"exec(open('reset_obe_questions_and_marks.py').read())\"")
else:
    with transaction.atomic():
        # Marks first, then questions. Deleting questions would cascade the
        # per-question marks anyway, but doing it explicitly keeps the
        # reported numbers honest and also catches any orphaned rows.
        d_obe_marks  = OBEStudentMark.objects.all().delete()[0]
        d_unit_marks = StudentMark.objects.all().delete()[0]
        d_questions  = OBEQuestion.objects.all().delete()[0]

    print("\n--- DELETED ---")
    print(f"  OBE Student Marks .......... {d_obe_marks:>7}")
    print(f"  Student Marks .............. {d_unit_marks:>7}")
    print(f"  OBE Questions .............. {d_questions:>7}")

    print("\n--- VERIFY (all should be 0) ---")
    print(f"  OBE Questions remaining .... {OBEQuestion.objects.count():>7}")
    print(f"  OBE Student Marks left ..... {OBEStudentMark.objects.count():>7}")
    print(f"  Student Marks left ......... {StudentMark.objects.count():>7}")

    print("\n--- STRUCTURE PRESERVED ---")
    print(f"  Marks Categories ........... {MarksCategory.objects.count():>7}")
    print(f"  Unit Items ................. {UnitItem.objects.count():>7}")
    print(f"  Course Students ............ {CourseStudent.objects.count():>7}")
    print(f"  CLOs ....................... {CLO.objects.count():>7}")
    print("\nDone. Instructors will now see one fresh question per unit.")
