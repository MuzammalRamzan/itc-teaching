import json
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


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def mark_writing_response(self, response_id):
    from apps.attempts.models import WritingResponse
    try:
        response = WritingResponse.objects.get(id=response_id)
        response.mark_status = 'marking'
        response.save(update_fields=['mark_status'])

        q = response.question
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

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        result = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1000,
            system=settings.B1W_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}]
        )
        data = json.loads(result.content[0].text.replace('```json', '').replace('```', '').strip())

        scores = data.get('scores', {})
        with transaction.atomic():
            response = WritingResponse.objects.select_for_update().select_related('attempt__user').get(id=response_id)
            user = response.attempt.user.__class__.objects.select_for_update().get(id=response.attempt.user_id)

            if not response.credits_charged:
                if user.ai_credits < 1:
                    response.mark_status = 'failed'
                    response.zero_reason = 'Insufficient AI credits to finalize writing marking.'
                    response.save(update_fields=['mark_status', 'zero_reason'])
                    return
                user.ai_credits -= 1
                user.save(update_fields=['ai_credits'])
                response.credits_charged = True

            response.score_content = scores.get('content')
            response.score_communicative = scores.get('communicative')
            response.score_organisation = scores.get('organisation')
            response.score_language = scores.get('language')
            response.total = data.get('total')
            response.band = data.get('band', '')
            response.cefr = data.get('cefr', '')
            response.strengths = data.get('strengths', '')
            response.improvements = data.get('improvements', '')
            response.suggestion = data.get('suggestion', '')
            response.zero_reason = data.get('zero_reason', '')
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
