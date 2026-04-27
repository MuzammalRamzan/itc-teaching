import json
import re
import anthropic
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.authentication.credits import create_credit_transaction


def refund_ai_credit(user_id, amount):
    from apps.authentication.models import User

    user = User.objects.select_for_update().get(id=user_id)
    user.ai_credits += amount
    user.save(update_fields=['ai_credits'])
    return user


FET_PHILOSOPHY_PROMPT = """You are a warm, encouraging English writing coach for the Colleges of Excellence
FET (Foundation English Test) in Saudi Arabia. You score student writing using
the official FET rubrics and give feedback designed to help students increase
their marks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MARKING PHILOSOPHY — READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are an encouraging teacher, not a strict examiner. Your goal is accurate,
fair marking that reflects what the student can do — not what they cannot.

RULE 1 — BORDERLINE = HIGHER BAND
If a student's writing sits between two bands, always award the higher band.
Example: if you are unsure between 3 and 4, award 4.

RULE 2 — ERRORS THAT DO NOT BLOCK MEANING DO NOT REDUCE THE BAND
A spelling mistake or wrong word that a reader can still understand does NOT
move the student to a lower band. Only mark down for errors that make the
meaning genuinely unclear.

RULE 3 — NEVER PENALISE GOOD VOCABULARY
Sophisticated words used correctly (e.g. "integral", "beneficial", "excessive")
are a sign of a strong student. Never treat them as "possibly memorised." Award
the higher vocabulary band.

RULE 4 — SLIPS ARE NOT ERRORS
A slip is a one-off mistake in an otherwise correct pattern (e.g. one wrong
tense in a paragraph where all other tenses are correct). Do not reduce the
band for slips. Only reduce for systematic, repeated mistakes.

RULE 5 — CONTENT SCORE IS ABOUT COMMUNICATION, NOT PERFECTION
If the target reader can understand the message and the main points are covered,
award band 4 or 5 for content. Only award band 2-3 if significant information
is missing or the message is genuinely confusing.

RULE 6 — ZERO FOR CONTENT = ZERO EVERYTHING
If content scores 0 (totally irrelevant, incomprehensible, or clearly copied),
all other scores are also 0. This is the only automatic rule.
"""


FET_TASK1_RUBRIC_PROMPT = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 1 RUBRIC (10 marks total)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTENT & COMMUNICATIVE ACHIEVEMENT (0-5)
5 - All content relevant. Target reader fully informed. Holds attention.
    Pre-learnt language limited to greeting/sign-off only.
4 - No irrelevancies. Target reader mostly informed. Minimal pre-learnt
    language but all points are addressed.
3 - Minor irrelevances or omissions. Target reader informed on the whole.
    Generally appropriate communicative conventions used.
2 - Some irrelevances or misinterpretations. Target reader reasonably informed.
1 - Mostly irrelevant. Target reader minimally informed.
0 - Did not attempt, absent, or completely incomprehensible.

LANGUAGE & ORGANISATION (0-5)
5 - Well organised and coherent. Variety of linking words and cohesive devices.
    Range of everyday vocabulary. Range of simple and complex grammar with
    complete control. Minimal errors. Accurate spelling and punctuation.
4 - Generally well-organised. Range of basic linking words and cohesive devices.
    Range of everyday vocabulary. Simple with occasional complex grammar, good
    control. Errors don't impede communication. Basic vocabulary spelling accurate.
3 - Connected and coherent. Basic linking words and limited cohesive devices.
    Everyday vocabulary generally appropriate. Simple grammar with reasonable
    control. Errors noticeable but meaning still determinable. Mostly accurate
    everyday spelling. Word limit adhered to.
2 - Connected with basic high-frequency linking words only. Basic vocabulary.
    Simple grammar with some control. Errors may impede meaning at times.
    Spelling often inaccurate. May be under word count.
1 - Very basic linking words only. Basic vocabulary and grammar. May be
    well under word count.
0 - Did not attempt or absent.
"""


FET_TASK2_RUBRIC_PROMPT = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 2 RUBRIC (20 marks total)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTENT & COMMUNICATIVE ACHIEVEMENT (0-5)
5 - All content relevant. All elements fully communicated. Target reader fully
    informed. Holds attention. Communicates straightforward and complex ideas.
4 - All elements communicated. Target reader informed. Minor irrelevance may
    occur. Simple and some complex ideas communicated effectively.
3 - Minor irrelevances or omissions. All elements communicated. Target reader
    on the whole informed. Communicates straightforward ideas.
2 - Some elements omitted or unsuccessfully dealt with. Message only partially
    communicated. Communicates simple ideas in simple ways. Some text may
    be memorised.
1 - Irrelevances and misinterpretation. Target reader minimally informed.
    Only single words or phrases produced.
0 - Totally irrelevant, incomprehensible, clearly memorised, or too little
    to assess.

ORGANISATION (0-5)
5 - Well organised and coherent. Variety of cohesive devices and organisational
    patterns used to good effect.
4 - Connected and coherent. Linking words and a range of cohesive devices used.
3 - Connected and coherent. Linking words and variety of cohesive devices used.
2 - Connected with limited basic high-frequency linking words only.
1 - Not connected. Little use of even basic linking words.
0 - See content = 0 rule.

VOCABULARY (0-5)
5 - Range of vocabulary including less common lexis used appropriately.
    Highly accurate spelling with only errors in high-level vocabulary.
4 - Everyday and some less common vocabulary used appropriately.
    Spelling accurate.
3 - Range of everyday vocabulary used appropriately with occasional
    inappropriate use of less common lexis. Most spelling correct.
2 - Basic vocabulary used appropriately. Some spelling errors which may
    require interpretation.
1 - Some basic vocabulary used appropriately. Many spelling errors
    requiring interpretation.
0 - See content = 0 rule.

GRAMMAR (0-5)
5 - Range of simple and complex grammatical forms. Good degree of control.
    Errors don't impede communication. Punctuation highly accurate.
4 - Range of simple and some complex grammatical forms. Good degree of
    control. Errors don't impede communication. Punctuation mostly correct.
3 - Range of simple and some complex grammatical forms. Good degree of
    control. Some errors noticeable, meaning still determinable.
    Punctuation generally correct.
2 - Simple grammatical forms with a degree of control. Punctuation
    usually correct.
1 - Simple grammatical forms. Errors may impede communication.
    Punctuation occasionally correct.
0 - See content = 0 rule.
"""


FET_FEEDBACK_RULES_PROMPT = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEEDBACK FORMAT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE A - ONE WELL-DONE
Write exactly one sentence praising something specific from their actual
writing. Never generic praise like "good job." Always reference something
real they did (e.g. "You used 'on one hand / on the other hand' perfectly").

RULE B - IMPROVEMENTS ONLY, NO CRITICISM
Every piece of feedback must be framed as "do this to get more marks" -
never "you did this wrong." The student should feel capable, not judged.

RULE C - MAXIMUM 3 IMPROVEMENTS
Give the student the 3 highest-impact changes only, ordered easiest first.
Never list more than 3 even if there are more errors.

RULE D - EVERY IMPROVEMENT HAS A BEFORE/AFTER EXAMPLE
Each improvement must include a concrete example using the student's own
words where possible. Show exactly what the change looks like.

RULE E - ARABIC FOR A1 AND A2 ONLY
If the student is A1 or A2 level, include an Arabic explanation for any
improvement that involves a grammar rule or confusing concept. Do not
use Arabic for B1 or B2 students.

RULE F - SHOW THE POTENTIAL SCORE
Calculate what score the student could realistically reach if they made
the suggested improvements. Show this as "you could reach X/10" or
"X/20."

RULE G - END WITH ONE PRACTICE TASK
Give exactly one specific task the student can do right now, in under
5 minutes. It must be concrete (e.g. "rewrite your last sentence using
this structure") not general (e.g. "practise your grammar").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STUDENT LEVEL DETECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detect the student's level from their writing:

A1 - Very short sentences, basic vocabulary only, many missing verbs
     (is/am/are), unclear purpose, under 40 words.
A2 - Simple sentences, mostly present tense, some past tense attempts,
     basic connectors (and/but), message is understandable, 40-80 words.
B1 - Paragraph structure present, uses discourse markers (however/
     furthermore/in conclusion), mix of simple and complex sentences,
     80-150 words.
B2 - Complex ideas, varied vocabulary including less common lexis,
     complex grammatical structures, strong organisation, 150+ words.
"""


FET_TASK1_OUTPUT_PROMPT = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPOND ONLY IN THIS JSON FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

No markdown. No backticks. No preamble. Return only the JSON object below.

{
  "studentLevel": "A1" | "A2" | "B1" | "B2",
  "totalScore": number,
  "maxScore": 10,
  "potentialScore": number,
  "wellDone": "one specific sentence praising something real in their writing",
  "criteria": [
    { "name": "Content & Communicative Achievement", "score": number, "maxScore": 5 },
    { "name": "Language & Organisation", "score": number, "maxScore": 5 }
  ],
  "improvements": [
    {
      "criterionName": "Content & Communicative Achievement" | "Language & Organisation",
      "marksGained": number,
      "action": "short verb-first instruction e.g. Change 3 verbs to past tense",
      "why": "one sentence explaining why this gains marks, max 20 words",
      "before": "the student's original phrase or a representative example",
      "after": "the improved version",
      "arabicExplanation": "Arabic explanation of the rule (A1/A2 only, null for B1/B2)"
    }
  ],
  "practiceTask": "one specific task under 5 minutes"
}
"""


FET_TASK2_OUTPUT_PROMPT = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPOND ONLY IN THIS JSON FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

No markdown. No backticks. No preamble. Return only the JSON object below.

{
  "studentLevel": "A1" | "A2" | "B1" | "B2",
  "totalScore": number,
  "maxScore": 20,
  "potentialScore": number,
  "wellDone": "one specific sentence praising something real in their writing",
  "criteria": [
    { "name": "Content & Communicative Achievement", "score": number, "maxScore": 5 },
    { "name": "Organisation", "score": number, "maxScore": 5 },
    { "name": "Vocabulary", "score": number, "maxScore": 5 },
    { "name": "Grammar", "score": number, "maxScore": 5 }
  ],
  "improvements": [
    {
      "criterionName": "Content & Communicative Achievement" | "Organisation" | "Vocabulary" | "Grammar",
      "marksGained": number,
      "action": "short verb-first instruction",
      "why": "one sentence explaining why this gains marks, max 20 words",
      "before": "the student's original phrase or a representative example",
      "after": "the improved version",
      "arabicExplanation": "Arabic explanation of the rule (A1/A2 only, null for B1/B2)"
    }
  ],
  "practiceTask": "one specific task under 5 minutes"
}
"""


FET_TASK1_SYSTEM_PROMPT = (
    FET_PHILOSOPHY_PROMPT
    + '\n'
    + FET_TASK1_RUBRIC_PROMPT
    + '\n'
    + FET_FEEDBACK_RULES_PROMPT
    + '\n'
    + FET_TASK1_OUTPUT_PROMPT
)


FET_TASK2_SYSTEM_PROMPT = (
    FET_PHILOSOPHY_PROMPT
    + '\n'
    + FET_TASK2_RUBRIC_PROMPT
    + '\n'
    + FET_FEEDBACK_RULES_PROMPT
    + '\n'
    + FET_TASK2_OUTPUT_PROMPT
)


LEVEL_AWARE_FEEDBACK_PROMPT = ''


def _extract_word_tokens(text):
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text or '')


def _too_little_language(question, text):
    words = _extract_word_tokens(text)
    unique_words = {word.lower() for word in words}
    min_words = 6 if question.part == 1 else 12
    min_unique = 4 if question.part == 1 else 6
    return len(words) < min_words or len(unique_words) < min_unique


def _build_writing_system_prompt(response, use_rubric_prompt):
    if use_rubric_prompt:
        # FET v2 prompt is self-contained per spec — no additional appending.
        return FET_TASK1_SYSTEM_PROMPT if response.question.part == 1 else FET_TASK2_SYSTEM_PROMPT

    base_prompt = settings.B1W_SYSTEM_PROMPT
    exam_context = 'General B1 writing exam.'
    return f"{base_prompt}\n{LEVEL_AWARE_FEEDBACK_PROMPT}\nEXAM CONTEXT:\n- {exam_context}"


def _clamp_score(value, maximum=5):
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError):
        return 0


def _empty_v2_payload():
    return {
        'student_level': '',
        'potential_score': None,
        'well_done': '',
        'practice_task': '',
        'feedback_json': {},
    }


def _fet_zero_result(question, reason):
    base = {
        'band': '',
        'cefr': '',
        'strengths': '',
        'improvements': reason,
        'zero_reason': reason,
    }
    base.update(_empty_v2_payload())
    if question.part == 1:
        base.update({
            'score_content': 0,
            'score_communicative': None,
            'score_organisation': None,
            'score_language': 0,
            'total': 0,
            'suggestion': 'Write enough relevant language to answer all required points before time ends.',
        })
        return base

    base.update({
        'score_content': 0,
        'score_communicative': 0,
        'score_organisation': 0,
        'score_language': 0,
        'total': 0,
        'suggestion': 'Write a complete response with relevant content and enough supporting language to allow assessment.',
    })
    return base


# Maps v2 criterion names to legacy DB columns. Order matters within each task.
TASK1_CRITERIA = {
    'Content & Communicative Achievement': 'score_content',
    'Language & Organisation': 'score_language',
}

TASK2_CRITERIA = {
    'Content & Communicative Achievement': 'score_content',
    'Organisation': 'score_communicative',  # legacy column reused for organisation
    'Vocabulary': 'score_organisation',     # legacy column reused for vocabulary
    'Grammar': 'score_language',            # legacy column reused for grammar
}


def _build_legacy_strings_from_v2(data):
    well_done = (data.get('wellDone') or '').strip()
    practice_task = (data.get('practiceTask') or '').strip()
    improvements_list = data.get('improvements') or []
    improvement_lines = []
    for item in improvements_list:
        if not isinstance(item, dict):
            continue
        action = (item.get('action') or '').strip()
        why = (item.get('why') or '').strip()
        before = (item.get('before') or '').strip()
        after = (item.get('after') or '').strip()
        line = action
        if why:
            line = f'{line} — {why}' if line else why
        if before and after:
            line = f'{line} (e.g. "{before}" → "{after}")' if line else f'"{before}" → "{after}"'
        if line:
            improvement_lines.append(line)
    return {
        'strengths': well_done,
        'improvements': '\n\n'.join(improvement_lines),
        'suggestion': practice_task,
    }


def _normalise_v2_writing_result(response, data):
    """Map the FET v2 JSON payload to the dict mark_writing_response persists."""
    part = getattr(response.question, 'part', None)
    criteria_map = TASK1_CRITERIA if part == 1 else TASK2_CRITERIA

    score_columns = {
        'score_content': None if part == 1 else 0,
        'score_communicative': None if part == 1 else 0,
        'score_organisation': None if part == 1 else 0,
        'score_language': 0,
    }
    if part == 1:
        score_columns['score_content'] = 0

    seen_criteria = []
    for criterion in (data.get('criteria') or []):
        if not isinstance(criterion, dict):
            continue
        name = (criterion.get('name') or '').strip()
        column = criteria_map.get(name)
        if not column:
            continue
        score_columns[column] = _clamp_score(criterion.get('score'))
        seen_criteria.append({
            'name': name,
            'score': score_columns[column],
            'maxScore': 5,
        })

    total = sum((value or 0) for value in score_columns.values() if value is not None)
    if isinstance(data.get('totalScore'), (int, float)):
        # Trust the model's total only when criteria add up to it; otherwise rely on summed columns.
        ai_total = int(data.get('totalScore'))
        if abs(ai_total - total) <= 1:
            total = ai_total

    legacy_text = _build_legacy_strings_from_v2(data)

    sanitised_improvements = []
    for item in (data.get('improvements') or [])[:3]:
        if not isinstance(item, dict):
            continue
        sanitised_improvements.append({
            'criterionName': (item.get('criterionName') or '').strip(),
            'marksGained': _clamp_score(item.get('marksGained'), maximum=5),
            'action': (item.get('action') or '').strip(),
            'why': (item.get('why') or '').strip(),
            'before': (item.get('before') or '').strip(),
            'after': (item.get('after') or '').strip(),
            'arabicExplanation': (item.get('arabicExplanation') or None),
        })

    student_level = (data.get('studentLevel') or '').strip().upper()
    if student_level not in {'A1', 'A2', 'B1', 'B2'}:
        student_level = ''

    max_score = 10 if part == 1 else 20
    potential_raw = data.get('potentialScore')
    try:
        potential_score = max(int(total), min(max_score, int(potential_raw))) if potential_raw is not None else None
    except (TypeError, ValueError):
        potential_score = None

    feedback_json = {
        'studentLevel': student_level,
        'totalScore': int(total),
        'maxScore': max_score,
        'potentialScore': potential_score,
        'wellDone': (data.get('wellDone') or '').strip(),
        'criteria': seen_criteria or [],
        'improvements': sanitised_improvements,
        'practiceTask': (data.get('practiceTask') or '').strip(),
    }

    return {
        'score_content': score_columns['score_content'],
        'score_communicative': score_columns['score_communicative'],
        'score_organisation': score_columns['score_organisation'],
        'score_language': score_columns['score_language'],
        'total': int(total),
        'band': '',
        'cefr': '',
        'strengths': legacy_text['strengths'],
        'improvements': legacy_text['improvements'],
        'suggestion': legacy_text['suggestion'],
        'zero_reason': '',
        'student_level': student_level,
        'potential_score': potential_score,
        'well_done': feedback_json['wellDone'],
        'practice_task': feedback_json['practiceTask'],
        'feedback_json': feedback_json,
    }


def _normalise_writing_result(response, data):
    """Dispatch to v2 (new schema) or v1 (legacy) based on payload shape."""
    if isinstance(data, dict) and ('criteria' in data or 'wellDone' in data or 'studentLevel' in data):
        return _normalise_v2_writing_result(response, data)

    # Legacy v1 path — kept for backwards compatibility with non-FET prompts.
    scores = data.get('scores', {}) or {}
    legacy = _empty_v2_payload()

    if getattr(response.question, 'part', None) == 1:
        score_content = _clamp_score(scores.get('content_communicative'))
        score_language = _clamp_score(scores.get('language_organisation'))
        total = score_content + score_language
        result = {
            'score_content': score_content,
            'score_communicative': None,
            'score_organisation': None,
            'score_language': score_language,
            'total': total,
            'band': '',
            'cefr': '',
            'strengths': (data.get('strengths') or '').strip(),
            'improvements': (data.get('improvements') or '').strip(),
            'suggestion': (data.get('suggestion') or '').strip(),
            'zero_reason': (data.get('zero_reason') or '').strip(),
        }
        result.update(legacy)
        return result

    if getattr(response.question, 'part', None) == 2:
        score_content = _clamp_score(scores.get('content_communicative'))
        score_communicative = _clamp_score(scores.get('organisation'))
        score_organisation = _clamp_score(scores.get('vocabulary'))
        score_language = _clamp_score(scores.get('grammar'))
        total = score_content + score_communicative + score_organisation + score_language
        result = {
            'score_content': score_content,
            'score_communicative': score_communicative,
            'score_organisation': score_organisation,
            'score_language': score_language,
            'total': total,
            'band': '',
            'cefr': '',
            'strengths': (data.get('strengths') or '').strip(),
            'improvements': (data.get('improvements') or '').strip(),
            'suggestion': (data.get('suggestion') or '').strip(),
            'zero_reason': (data.get('zero_reason') or '').strip(),
        }
        result.update(legacy)
        return result

    if getattr(response.attempt.exam, 'exam_family', '') == 'fet':
        if response.question.part == 1:
            score_content = _clamp_score(scores.get('content_communicative'))
            score_language = _clamp_score(scores.get('language_organisation'))
            total = score_content + score_language
            result = {
                'score_content': score_content,
                'score_communicative': None,
                'score_organisation': None,
                'score_language': score_language,
                'total': total,
                'band': '',
                'cefr': '',
                'strengths': (data.get('strengths') or '').strip(),
                'improvements': (data.get('improvements') or '').strip(),
                'suggestion': (data.get('suggestion') or '').strip(),
                'zero_reason': (data.get('zero_reason') or '').strip(),
            }
            result.update(legacy)
            return result

        score_content = _clamp_score(scores.get('content_communicative'))
        score_communicative = _clamp_score(scores.get('organisation'))
        score_organisation = _clamp_score(scores.get('vocabulary'))
        score_language = _clamp_score(scores.get('grammar'))
        total = score_content + score_communicative + score_organisation + score_language
        result = {
            'score_content': score_content,
            'score_communicative': score_communicative,
            'score_organisation': score_organisation,
            'score_language': score_language,
            'total': total,
            'band': '',
            'cefr': '',
            'strengths': (data.get('strengths') or '').strip(),
            'improvements': (data.get('improvements') or '').strip(),
            'suggestion': (data.get('suggestion') or '').strip(),
            'zero_reason': (data.get('zero_reason') or '').strip(),
        }
        result.update(legacy)
        return result

    fallback = {
        'score_content': scores.get('content'),
        'score_communicative': scores.get('communicative'),
        'score_organisation': scores.get('organisation'),
        'score_language': scores.get('language'),
        'total': data.get('total'),
        'band': data.get('band', ''),
        'cefr': data.get('cefr', ''),
        'strengths': data.get('strengths', ''),
        'improvements': data.get('improvements', ''),
        'suggestion': data.get('suggestion', ''),
        'zero_reason': data.get('zero_reason', ''),
    }
    fallback.update(legacy)
    return fallback


def _soften_borderline_writing_scores(response, normalised):
    question = getattr(response, 'question', None)
    if not question or getattr(response.attempt.exam, 'exam_family', '') != 'fet':
        return normalised

    if normalised['zero_reason'] or not (response.text or '').strip():
        return normalised

    if question.part == 1:
        total = int(normalised['total'] or 0)
        if total in {5, 7, 9}:
            if total == 5 and normalised['score_content'] < 5:
                normalised['score_content'] += 1
            elif normalised['score_language'] < 5:
                normalised['score_language'] += 1
            normalised['total'] = normalised['score_content'] + normalised['score_language']
        return normalised

    total = int(normalised['total'] or 0)
    if total in {9, 13, 17}:
        for field in ('score_language', 'score_organisation', 'score_communicative', 'score_content'):
            if (normalised[field] or 0) < 5:
                normalised[field] += 1
                break
        normalised['total'] = (
            normalised['score_content']
            + normalised['score_communicative']
            + normalised['score_organisation']
            + normalised['score_language']
        )
    return normalised


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def mark_writing_response(self, response_id):
    from apps.attempts.models import WritingResponse
    try:
        response = WritingResponse.objects.get(id=response_id)
        response.mark_status = 'marking'
        response.save(update_fields=['mark_status'])

        q = response.question
        use_rubric_prompt = getattr(q, 'part', None) in {1, 2}
        prompt = f'TASK:{q.question_type}\n'
        if q.question_type == 'email':
            prompt += f'Notes:{",".join(q.notes or [])}'
        elif q.question_type == 'article':
            prompt += f'Prompts:{"|".join(q.prompt_items or [])}'
        elif q.question_type == 'story':
            prompt += f'Opener:"{q.story_opener}"'
        prompt += f'\n~{q.word_count or 100} words\n\nSTUDENT:\n{response.text}'

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError('Anthropic API key is not configured on the backend.')

        if use_rubric_prompt and _too_little_language(q, response.text):
            data = _fet_zero_result(
                q,
                'Too little relevant language was provided to assess this task under the rubric.',
            )
        else:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            result = client.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=1800,
                system=_build_writing_system_prompt(response, use_rubric_prompt),
                messages=[{'role': 'user', 'content': prompt}]
            )
            data = json.loads(result.content[0].text.replace('```json', '').replace('```', '').strip())

        normalised = _normalise_writing_result(response, data)
        normalised = _soften_borderline_writing_scores(response, normalised)
        with transaction.atomic():
            response = WritingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
            charged_now = False

            if response.submission_group_id and not response.attempt.bypass_ai_credits:
                group_responses = list(
                    WritingResponse.objects.select_for_update().filter(
                        attempt=response.attempt,
                        submission_group_id=response.submission_group_id,
                    )
                )
                charged_response = next((item for item in group_responses if item.credits_charged), None)
                if charged_response is None:
                    user = response.attempt.user.__class__.objects.select_for_update().get(pk=response.attempt.user_id)
                    if user.ai_credits < 1:
                        raise RuntimeError('You need at least 1 AI credit to finish writing marking.')
                    user.ai_credits -= 1
                    user.save(update_fields=['ai_credits'])
                    create_credit_transaction(
                        user=user,
                        delta=-1,
                        description=f'1 credit spent on writing feedback for {response.attempt.exam.title}.',
                        source_type='writing_submission',
                        source_id=response.submission_group_id,
                        metadata={
                            'attempt_id': str(response.attempt_id),
                            'exam_id': str(response.attempt.exam_id),
                            'exam_title': response.attempt.exam.title,
                            'question_id': str(response.question_id),
                        },
                    )
                    response.credits_charged = True
                    charged_now = True

            response.score_content = normalised['score_content']
            response.score_communicative = normalised['score_communicative']
            response.score_organisation = normalised['score_organisation']
            response.score_language = normalised['score_language']
            response.total = normalised['total']
            response.band = normalised['band']
            response.cefr = normalised['cefr']
            response.strengths = normalised['strengths']
            response.improvements = normalised['improvements']
            response.suggestion = normalised['suggestion']
            response.zero_reason = normalised['zero_reason']
            response.student_level = normalised.get('student_level', '') or ''
            response.potential_score = normalised.get('potential_score')
            response.well_done = normalised.get('well_done', '') or ''
            response.practice_task = normalised.get('practice_task', '') or ''
            response.feedback_json = normalised.get('feedback_json') or {}
            response.mark_status = 'done'
            response.marked_at = timezone.now()
            update_fields = [
                'score_content',
                'score_communicative',
                'score_organisation',
                'score_language',
                'total',
                'band',
                'cefr',
                'strengths',
                'improvements',
                'suggestion',
                'zero_reason',
                'student_level',
                'potential_score',
                'well_done',
                'practice_task',
                'feedback_json',
                'mark_status',
                'marked_at',
            ]
            if charged_now:
                update_fields.append('credits_charged')
            response.save(update_fields=update_fields)

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                with transaction.atomic():
                    response = WritingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
                    update_fields = ['mark_status']
                    response.mark_status = 'failed'
                    response.save(update_fields=update_fields)

                    if response.submission_group_id and not response.attempt.bypass_ai_credits:
                        group_responses = list(
                            WritingResponse.objects.select_for_update().filter(
                                attempt=response.attempt,
                                submission_group_id=response.submission_group_id,
                            )
                        )
                        charged_response = next(
                            (
                                item for item in group_responses
                                if item.credits_charged and not item.credits_refunded
                            ),
                            None,
                        )
                        if charged_response and all(item.mark_status == WritingResponse.STATUS_FAILED for item in group_responses):
                            user = refund_ai_credit(response.attempt.user_id, 1)
                            create_credit_transaction(
                                user=user,
                                delta=1,
                                description=f'1 credit refunded for writing feedback on {response.attempt.exam.title}.',
                                source_type='writing_refund',
                                source_id=response.submission_group_id,
                                metadata={
                                    'attempt_id': str(response.attempt_id),
                                    'exam_id': str(response.attempt.exam_id),
                                    'exam_title': response.attempt.exam.title,
                                },
                            )
                            charged_response.credits_refunded = True
                            charged_response.save(update_fields=['credits_refunded'])
            except Exception:
                pass
            raise exc
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def mark_speaking_response(self, response_id):
    from apps.attempts.models import SpeakingResponse
    from apps.exams.models import SpeakingPart
    try:
        response = SpeakingResponse.objects.get(id=response_id)
        response.mark_status = 'marking'
        response.save(update_fields=['mark_status'])

        # Build the examiner system prompt
        parts = SpeakingPart.objects.filter(exam=response.attempt.exam).order_by('order', 'part')
        system = settings.SPEAKING_EXAMINER_PROMPT + '\n\nSPEAKING TEST STRUCTURE:\n\n'
        for p in parts:
            system += f'=== {p.label} ===\nInstructions: {p.instruction}\n'
            if p.part in ('1', '4'):
                for i, q in enumerate(p.questions or [], 1):
                    system += f'  {i}. {q}\n'
            elif p.part == '2':
                system += f'A: {p.situation_a}\nB: {p.situation_b}\n'
            elif p.part == '3':
                system += f'Central: "{p.central_question}"\nOptions: {" / ".join(p.options or [])}\n'
            system += '\n'

        messages = list(response.transcript)
        messages.append({'role': 'user', 'content': settings.SPEAK_MARK_PROMPT})

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError('Anthropic API key is not configured on the backend.')

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        result = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=600,
            system=system,
            messages=messages
        )
        data = json.loads(result.content[0].text.replace('```json', '').replace('```', '').strip())

        scores = data.get('scores', {})
        response.score_grammar = scores.get('grammar')
        response.score_discourse = scores.get('discourse')
        response.score_interaction = scores.get('interaction')
        response.total = data.get('total')
        response.band = data.get('band', '')
        response.cefr = data.get('cefr', '')
        response.strengths = data.get('strengths', '')
        response.improvements = data.get('improvements', '')
        response.suggestion = data.get('suggestion', '')
        response.mark_status = 'done'
        response.marked_at = timezone.now()
        response.save()

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                with transaction.atomic():
                    response = SpeakingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
                    update_fields = ['mark_status']
                    response.mark_status = 'failed'
                    if not response.credits_refunded:
                        user = refund_ai_credit(response.attempt.user_id, response.credits_charged)
                        create_credit_transaction(
                            user=user,
                            delta=response.credits_charged,
                            description=f'{response.credits_charged} credits refunded for speaking assessment on {response.attempt.exam.title}.',
                            source_type='speaking_refund',
                            source_id=response.id,
                            metadata={
                                'attempt_id': str(response.attempt_id),
                                'exam_id': str(response.attempt.exam_id),
                                'exam_title': response.attempt.exam.title,
                            },
                        )
                        response.credits_refunded = True
                        update_fields.append('credits_refunded')
                    response.save(update_fields=update_fields)
            except Exception:
                pass
            raise exc
        raise self.retry(exc=exc)
