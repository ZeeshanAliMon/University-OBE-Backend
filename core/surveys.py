"""
The four NCEAC surveys (OBE Framework for NCEAC, 2-07-2024, pages 30-37) and the
calculations on their responses. The forms themselves run in Microsoft Forms; QA
uploads the downloaded responses.

Survey KPI: answers are not averaged. For each question, at least 50% of the
responses must score 3 or above on the 1-5 scale.
"""
import re

from .models import GraduateAttribute, SurveyMapping, SurveyResponse, SurveyUpload

RATING_PASS = 3
SURVEY_KPI = 50.0
RATING_WORDS = {'excellent': 5, 'very good': 4, 'good': 3, 'average': 2, 'fail': 1}


SURVEY_FORMS = {
    'internship': {
        'title': 'Internship Feedback', 'usedFor': 'GA',
        'questions': [
            'Possess and apply relevant knowledge and skill',
            'Analytical approach towards solving a problem',
            'Ability to design/develop solutions for different problems',
            'Ability to investigate design process',
            'Has the potential to use modern tools',
            'Ability to work as a team member',
            'Interpersonal and communication skills',
            'Possess knowledge to assess societal, health, safety, legal and cultural issues and aware of responsibilities relevant to professional computing practice',
            'Punctuality and discipline',
            'Demonstrate lifelong learning through consistent commitment for continuous improvement',
        ],
    },
    'exit': {
        'title': 'Graduating (Exit) Survey', 'usedFor': 'GA',
        'questions': [
            'The program provides adequate Computing knowledge',
            'The program provides sufficient problem analysis skills',
            'The program helps design and develop solutions to technical problems',
            'The program helps perform investigation of a technical problem',
            'The program provides adequate skills to use modern tools',
            'The program gives an opportunity to work as an individual or in team',
            'The program enhances the skills of oral and written communication',
            'The program teaches professional responsibilities and to work for society',
            'The program teaches ethical responsibilities',
            'The program opens a way for lifelong learning',
        ],
    },
    'alumni': {
        'title': 'Alumni Survey', 'usedFor': 'PO',
        'questions': [
            'Computing knowledge',
            'Problem formulation and solving skills',
            'Collecting and analyzing appropriate data',
            'Ability to design a system/component/process/program/module',
            'Appreciation of ethical values and difference of opinion',
            'Taking part in activities to build better society',
            'Desire of improving personal skills/personality',
            'Ability to work in teams and listen to others',
            'Ability to work in challenging environments',
            'Able to think independently and make decisions',
            'Ability to meet deadlines/manage time',
            'Communication and presentation skills',
            'Technical report writing skills',
        ],
        'defaultPOs': {1: 'PO1', 2: 'PO1', 3: 'PO2', 4: 'PO2', 5: 'PO4', 6: 'PO4', 7: 'PO3',
                       8: 'PO4', 9: 'PO3', 10: 'PO2', 11: 'PO3', 12: 'PO4', 13: 'PO4'},
    },
    'employer': {
        'title': 'Employer Survey', 'usedFor': 'PO',
        'questions': [
            'Able to demonstrate professional knowledge concerning his/her area of specialization',
            'Able to investigate, analyze and design solutions for complex computing problems',
            'Tends to learn and adopt to the latest technology',
            'Is self-motivated, committed and punctual',
            'Able to demonstrate/uphold professional ethics while exercising his/her profession',
            'Demonstrates responsible behavior towards the environment and society',
            'Appreciates the difference of opinion and ethical values of others',
            'Able to work in a team and cooperate with others',
            'Possesses necessary communication skills',
            'Able to meet deadlines and manage time constraints',
            'Capable to think independently and can work in challenging environments',
        ],
        'defaultPOs': {1: 'PO1', 2: 'PO2', 3: 'PO2', 4: 'PO3', 5: 'PO4', 6: 'PO3', 7: 'PO4',
                       8: 'PO4', 9: 'PO4', 10: 'PO3', 11: 'PO2'},
    },
}
GA_FORMS = ('internship', 'exit')
PO_FORMS = ('alumni', 'employer')


def batch_code(value):
    """'SP23' from a batch or reg number in any layout: 'CS-SP-23', '052-SP23-22144'."""
    m = re.search(r'(FA|SP|SU|SM|WI)[-\s]?(\d{2,4})', str(value or '').upper())
    return f'{m.group(1)}{int(m.group(2)) % 100:02d}' if m else ''


def parse_rating(value):
    """1-5 from 5, '5', '5 = Excellent' or 'Excellent'. None if blank. Raises ValueError if neither."""
    text = str(value if value is not None else '').strip().lower()
    if not text:
        return None
    m = re.match(r'^([1-5])(\.0+)?(\b|$)', text)
    if m:
        return int(m.group(1))
    if text in RATING_WORDS:
        return RATING_WORDS[text]
    raise ValueError(f'"{value}" is not a rating from 1 to 5')


def _ga_number(ga_id):
    numbers = re.findall(r'\d+', ga_id or '')
    return int(numbers[-1]) if numbers else None


def current_mapping(program, form_type):
    """{question number: target}, a GA id or a PO code. QA's changes over the framework's default."""
    form = SURVEY_FORMS[form_type]
    if form['usedFor'] == 'GA':
        by_number = {_ga_number(g.ga_id): g.ga_id for g in GraduateAttribute.objects.filter(program=program)}
        mapping = {n: by_number.get(n, '') for n in range(1, len(form['questions']) + 1)}
    else:
        mapping = dict(form['defaultPOs'])
    for row in SurveyMapping.objects.filter(program=program, form_type=form_type):
        mapping[row.question_no] = row.target
    return mapping


def _pct(ok, n):
    return round(ok / n * 100, 2) if n else None


def question_results(program, form_type, year=None, batches=None, graduation_year=None):
    """
    One row per (question, target), pooled over the form's uploads. Each upload
    counts under the mapping saved with it, so changing a mapping leaves past
    results as they were.
    """
    responses = SurveyResponse.objects.filter(program=program, upload__form_type=form_type).select_related('upload')
    if year:
        responses = responses.filter(upload__year=year)
    if graduation_year:
        responses = responses.filter(graduation_year=graduation_year)
    if batches is not None:
        responses = responses.filter(batch__in=batches)

    fallback = current_mapping(program, form_type)
    rows = {}
    response_count = 0
    for response in responses:
        response_count += 1
        snapshot = (response.upload.mapping_snapshot or {}).get(program.code.upper(), {})
        for key, rating in (response.ratings or {}).items():
            no = int(key)
            target = snapshot.get(str(no), fallback.get(no, ''))
            row = rows.setdefault((no, target), {'questionNo': no, 'target': target, 'counts': {str(r): 0 for r in range(1, 6)}})
            row['counts'][str(rating)] += 1

    questions = SURVEY_FORMS[form_type]['questions']
    out = []
    for (no, target) in sorted(rows):
        row = rows[(no, target)]
        n = sum(row['counts'].values())
        ok = sum(v for r, v in row['counts'].items() if int(r) >= RATING_PASS)
        percent = _pct(ok, n)
        out.append({**row, 'text': questions[no - 1] if no <= len(questions) else '',
                    'responses': n, 'scoredThreeOrAbove': ok, 'percent': percent,
                    'kpiMet': percent is not None and percent >= SURVEY_KPI})
    return out, response_count


def target_results(program, form_type, **filters):
    """{target: {percent, questions, responses}}: the average of its questions' percentages."""
    rows, response_count = question_results(program, form_type, **filters)
    out = {}
    for row in rows:
        if row['target']:
            out.setdefault(row['target'], []).append(row)
    return ({
        target: {'percent': round(sum(r['percent'] for r in rs) / len(rs), 2), 'questions': rs,
                 'responses': max(r['responses'] for r in rs)}
        for target, rs in out.items()
    }, response_count)


def indirect_ga(program, batches=None):
    """
    {ga_id: {internship, exit, indirect}}: the percentage scoring 3 or above on
    each form, and their average. The two forms count equally; with responses on
    only one form, that form alone is the indirect figure.
    """
    results = {f: target_results(program, f, batches=batches) for f in GA_FORMS}
    counts = {f: results[f][1] for f in GA_FORMS}
    out = {}
    for f in GA_FORMS:
        for ga_id, r in results[f][0].items():
            out.setdefault(ga_id, {})[f] = r
    for row in out.values():
        values = [row[f]['percent'] for f in GA_FORMS if f in row]
        row['indirect'] = round(sum(values) / len(values), 2)
    return out, counts


def indirect_po(program, graduation_year=None):
    """{po_code: {percent, questions}} over the alumni and employer questions mapped to the PO."""
    out = {}
    counts = {}
    for f in PO_FORMS:
        results, counts[f] = target_results(program, f, graduation_year=graduation_year)
        for po, r in results.items():
            row = out.setdefault(po, {'questions': []})
            row['questions'] += [{**q, 'formType': f} for q in r['questions']]
    for row in out.values():
        row['percent'] = round(sum(q['percent'] for q in row['questions']) / len(row['questions']), 2)
    return out, counts


def graduation_years(program):
    return sorted(set(SurveyResponse.objects.filter(
        program=program, upload__form_type__in=PO_FORMS, graduation_year__isnull=False,
    ).values_list('graduation_year', flat=True)))
