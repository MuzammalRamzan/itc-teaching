import json
import re
import anthropic
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone


def refund_ai_credit(user_id, amount):
    from apps.authentication.models import User

    user = User.objects.select_for_update().get(id=user_id)
    user.ai_credits += amount
    user.save(update_fields=['ai_credits'])


FET_TASK1_SYSTEM_PROMPT = """You are marking FET Writing Task 1 using ONLY this rubric.

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
- Award a band only when ALL criteria for that score are met. If between two scores, award the LOWER score.
- If the writing is too short, irrelevant, memorised, or impossible to assess properly, award 0 for both criteria.
- Feedback must be honest. Do not give positive praise when there is too little relevant language.
- Return JSON only with this exact shape:
{"scores":{"content_communicative":N,"language_organisation":N},"total":N,"strengths":"...","improvements":"...","suggestion":"...","zero_reason":"..."}
"""


FET_TASK2_SYSTEM_PROMPT = """You are marking FET Writing Task 2 using ONLY this rubric.

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
- Award a score only when the full description for that band is met. If between two scores, award the LOWER score.
- If content is totally irrelevant, incomprehensible, memorised, or too short to assess, award 0 and set the other criteria to 0 as well.
- Feedback must be honest and evidence-based. Do not give encouraging praise when the response is extremely weak.
- Return JSON only with this exact shape:
{"scores":{"content_communicative":N,"organisation":N,"vocabulary":N,"grammar":N},"total":N,"strengths":"...","improvements":"...","suggestion":"...","zero_reason":"..."}
"""


def _extract_word_tokens(text):
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text or '')


def _too_little_language(question, text):
    words = _extract_word_tokens(text)
    unique_words = {word.lower() for word in words}
    min_words = 6 if question.part == 1 else 12
    min_unique = 4 if question.part == 1 else 6
    return len(words) < min_words or len(unique_words) < min_unique


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


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def mark_writing_response(self, response_id):
    from apps.attempts.models import WritingResponse
    try:
        response = WritingResponse.objects.get(id=response_id)
        response.mark_status = 'marking'
        response.save(update_fields=['mark_status'])

        q = response.question
        is_fet = getattr(response.attempt.exam, 'exam_family', '') == 'fet'
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

        if is_fet and _too_little_language(q, response.text):
            data = _fet_zero_result(
                q,
                'Too little relevant language was provided to assess this task under the FET rubric.',
            )
        else:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            result = client.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=1000,
                system=FET_TASK1_SYSTEM_PROMPT if is_fet and q.part == 1 else FET_TASK2_SYSTEM_PROMPT if is_fet else settings.B1W_SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': prompt}]
            )
            data = json.loads(result.content[0].text.replace('```json', '').replace('```', '').strip())

        normalised = _normalise_writing_result(response, data)
        with transaction.atomic():
            response = WritingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
            user = response.attempt.user.__class__.objects.select_for_update().get(id=response.attempt.user_id)

            if not response.credits_charged and not response.attempt.bypass_ai_credits:
                if user.ai_credits < 1:
                    response.mark_status = 'failed'
                    response.zero_reason = 'Insufficient AI credits to finalize writing marking.'
                    response.save(update_fields=['mark_status', 'zero_reason'])
                    return
                user.ai_credits -= 1
                user.save(update_fields=['ai_credits'])
                response.credits_charged = True

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
            response.save()

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            try:
                with transaction.atomic():
                    response = WritingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
                    update_fields = ['mark_status']
                    response.mark_status = 'failed'
                    if response.credits_charged and not response.credits_refunded:
                        refund_ai_credit(response.attempt.user_id, 1)
                        response.credits_refunded = True
                        update_fields.append('credits_refunded')
                    response.save(update_fields=update_fields)
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
                        refund_ai_credit(response.attempt.user_id, response.credits_charged)
                        response.credits_refunded = True
                        update_fields.append('credits_refunded')
                    response.save(update_fields=update_fields)
            except Exception:
                pass
            raise exc
        raise self.retry(exc=exc)
