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


FET_TASK1_SYSTEM_PROMPT = """You are marking Writing Task 1 using ONLY this rubric.

TASK 1 TOTAL = 10 MARKS.

Criterion 1: Content and Communicative Achievement (0-5)
- 5: all content relevant, target reader fully informed.
- 4: no irrelevancies, target reader mostly informed.
- 3: minor irrelevances/omissions, target reader informed on the whole.
- 2: some irrelevances/misinterpretations, target reader reasonably informed.
- 1: mostly irrelevant, target reader minimally informed.
- 0: did not attempt / absent / too little language to assess.

Criterion 2: Language and Organisation (0-5)
- 5: well organised and coherent, a variety of linking devices, accurate spelling/punctuation, strong control.
- 4: generally well organised, a range of basic linking devices, mostly accurate language.
- 3: connected and coherent, basic linking, reasonable control, word limit adhered to.
- 2: some basic linking, basic vocabulary and grammar, may be under word count.
- 1: very basic language, weak linking, errors often noticeable.
- 0: did not attempt / absent / too little language to assess.

STRICT RULES:
- Mark slightly generously while staying evidence-based.
- If between two adjacent scores, award the HIGHER score when the lower-band description is clearly met and most of the next-band performance is present.
- If the writing is too short, irrelevant, memorised, or impossible to assess properly, award 0 for both criteria.
- Feedback must be honest. Do not give positive praise when there is too little relevant language.
- Return JSON only with this exact shape:
{"scores":{"content_communicative":N,"language_organisation":N},"total":N,"strengths":"...","improvements":"...","suggestion":"...","zero_reason":"..."}
"""


FET_TASK2_SYSTEM_PROMPT = """You are marking Writing Task 2 using ONLY this rubric.

TASK 2 TOTAL = 20 MARKS.

Criteria scored 0-5 each:
1. Content and Communicative Achievement
2. Organisation
3. Vocabulary
4. Grammar

Score guidance:
- 5: fully successful and fully relevant for the rubric criterion
- 4: strong control with only minor issues
- 3: acceptable / generally appropriate / meaning clear
- 2: partial success only, limited control
- 1: minimal success, serious weakness
- 0: totally irrelevant, incomprehensible, memorised, or too little language to assess

STRICT RULES:
- Mark slightly generously while staying evidence-based.
- If between two adjacent scores, award the HIGHER score when the lower-band description is clearly met and most of the next-band performance is present.
- If content is totally irrelevant, incomprehensible, memorised, or too short to assess, award 0 and set the other criteria to 0 as well.
- Feedback must be honest and evidence-based. Do not give encouraging praise when the response is extremely weak.
- Return JSON only with this exact shape:
{"scores":{"content_communicative":N,"organisation":N,"vocabulary":N,"grammar":N},"total":N,"strengths":"...","improvements":"...","suggestion":"...","zero_reason":"..."}
"""


LEVEL_AWARE_FEEDBACK_PROMPT = """
FEEDBACK CALIBRATION:
- First estimate the student's current working level from the writing itself.
- Tailor feedback to the student's actual ability, not to an ideal target performance.
- For weaker students, use simpler language, focus on 1-2 important improvements, and recognise basic success clearly.
- For mid-level students, balance encouragement with concrete next steps.
- For stronger students, give more precise and demanding feedback about control, range, development, and accuracy.
- Keep feedback supportive and realistic. Do not sound harsh or overly advanced for a weaker student.
- "strengths" should name what the student can already do at their current level.
- "improvements" should prioritise the most useful next step for that level.
- "suggestion" should be one practical action the student can apply in the next answer.
"""


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
        base_prompt = FET_TASK1_SYSTEM_PROMPT if response.question.part == 1 else FET_TASK2_SYSTEM_PROMPT
    else:
        base_prompt = settings.B1W_SYSTEM_PROMPT

    exam_family = getattr(response.attempt.exam, 'exam_family', '')
    exam_context = 'FET writing exam focused on foundation-level learners.' if exam_family == 'fet' else 'General B1 writing exam.'
    return f"{base_prompt}\n{LEVEL_AWARE_FEEDBACK_PROMPT}\nEXAM CONTEXT:\n- {exam_context}"


def _clamp_score(value, maximum=5):
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError):
        return 0


def _fet_zero_result(question, reason):
    if question.part == 1:
        return {
            'score_content': 0,
            'score_communicative': None,
            'score_organisation': None,
            'score_language': 0,
            'total': 0,
            'band': '',
            'cefr': '',
            'strengths': '',
            'improvements': reason,
            'suggestion': 'Write enough relevant language to answer all required points before time ends.',
            'zero_reason': reason,
        }

    return {
        'score_content': 0,
        'score_communicative': 0,
        'score_organisation': 0,
        'score_language': 0,
        'total': 0,
        'band': '',
        'cefr': '',
        'strengths': '',
        'improvements': reason,
        'suggestion': 'Write a complete response with relevant content and enough supporting language to allow assessment.',
        'zero_reason': reason,
    }


def _normalise_writing_result(response, data):
    scores = data.get('scores', {}) or {}

    if getattr(response.question, 'part', None) == 1:
        score_content = _clamp_score(scores.get('content_communicative'))
        score_language = _clamp_score(scores.get('language_organisation'))
        total = score_content + score_language
        return {
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

    if getattr(response.question, 'part', None) == 2:
        score_content = _clamp_score(scores.get('content_communicative'))
        score_communicative = _clamp_score(scores.get('organisation'))
        score_organisation = _clamp_score(scores.get('vocabulary'))
        score_language = _clamp_score(scores.get('grammar'))
        total = score_content + score_communicative + score_organisation + score_language
        return {
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

    if getattr(response.attempt.exam, 'exam_family', '') == 'fet':
        if response.question.part == 1:
            score_content = _clamp_score(scores.get('content_communicative'))
            score_language = _clamp_score(scores.get('language_organisation'))
            total = score_content + score_language
            return {
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

        score_content = _clamp_score(scores.get('content_communicative'))
        score_communicative = _clamp_score(scores.get('organisation'))
        score_organisation = _clamp_score(scores.get('vocabulary'))
        score_language = _clamp_score(scores.get('grammar'))
        total = score_content + score_communicative + score_organisation + score_language
        return {
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

    return {
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
                max_tokens=1000,
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
