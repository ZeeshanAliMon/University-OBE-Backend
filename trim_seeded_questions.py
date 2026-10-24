"""
Trim auto-seeded OBE questions down to ONE per unit.

WHY
    seed_full_demo.py used to create 2-5 questions per unit (22 per course).
    Instructors opening "Set Marks Unit" were met with a pre-filled list of
    8+ questions they never created. The seed now creates one per unit, but
    rows written by earlier runs are still in the database — this script
    removes them.

WHAT IT DOES
    For every unit, keeps the FIRST question (lowest `order`) and deletes the
    rest, so the instructor starts from one and adds their own.

SAFETY
    OBEQuestion -> OBEStudentMark CASCADEs, so deleting a question destroys
    any marks recorded against it. This script therefore NEVER deletes a
    question that has student marks — those are reported and left alone for
    you to review by hand.

USAGE
    Dry run first (shows what would change, writes nothing):
        python manage.py shell -c "exec(open('trim_seeded_questions.py').read())"

    Then apply for real:
        APPLY=1 python manage.py shell -c "exec(open('trim_seeded_questions.py').read())"
"""
import os
from collections import defaultdict
from core.models import OBEQuestion, OBEStudentMark, UnitItem

APPLY = os.environ.get('APPLY') == '1'

print("=" * 68)
print("TRIM SEEDED OBE QUESTIONS  ->  one question per unit")
print("MODE:", "APPLY (changes will be saved)" if APPLY else "DRY RUN (nothing written)")
print("=" * 68)

# Group every question by the unit it belongs to.
by_unit = defaultdict(list)
orphans = []
for q in OBEQuestion.objects.select_related('course', 'unit_item').order_by('order', 'id'):
    if q.unit_item_id:
        by_unit[q.unit_item_id].append(q)
    else:
        orphans.append(q)

to_delete, protected = [], []

for unit_id, questions in by_unit.items():
    if len(questions) <= 1:
        continue
    # Keep the first, consider the rest for removal.
    for q in questions[1:]:
        if OBEStudentMark.objects.filter(question=q).exists():
            protected.append(q)
        else:
            to_delete.append(q)

print(f"\nUnits inspected:            {len(by_unit)}")
print(f"Units with >1 question:     {sum(1 for qs in by_unit.values() if len(qs) > 1)}")
print(f"Questions to remove:        {len(to_delete)}")
print(f"Kept (have student marks):  {len(protected)}")
if orphans:
    print(f"Questions with no unit:     {len(orphans)} (left untouched)")

if protected:
    print("\n--- KEPT because marks exist (review these yourself) ---")
    for q in protected[:40]:
        n = OBEStudentMark.objects.filter(question=q).count()
        print(f"  {q.course.code:<12} {q.category_name:<22} U{q.unit_no} "
              f"{q.question_name:<28} ({n} mark(s))")
    if len(protected) > 40:
        print(f"  ... and {len(protected) - 40} more")

if to_delete:
    print("\n--- WOULD REMOVE ---" if not APPLY else "\n--- REMOVING ---")
    for q in to_delete[:40]:
        print(f"  {q.course.code:<12} {q.category_name:<22} U{q.unit_no} {q.question_name}")
    if len(to_delete) > 40:
        print(f"  ... and {len(to_delete) - 40} more")

if APPLY and to_delete:
    deleted = 0
    for q in to_delete:
        q.delete()
        deleted += 1

    # Re-sum each affected unit's total marks from its surviving questions,
    # so the "Unit Total Marks" field stays consistent with what's left.
    touched_units = {q.unit_item_id for q in to_delete}
    resynced = 0
    for unit in UnitItem.objects.filter(id__in=touched_units):
        remaining = list(unit.questions.all())
        if remaining:
            new_total = sum(x.max_marks or 0 for x in remaining)
            if unit.total_marks != new_total:
                unit.total_marks = new_total
                unit.save(update_fields=['total_marks'])
                resynced += 1

    print(f"\nDeleted {deleted} question(s). Re-summed total marks on {resynced} unit(s).")
    print("Done.")
elif to_delete:
    print("\nNothing written. Re-run with APPLY=1 to apply.")
else:
    print("\nNothing to do — every unit already has one question or fewer.")
