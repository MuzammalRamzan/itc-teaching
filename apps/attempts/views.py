from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.exams.models import Exam, WritingQuestion, SpeakingPart
from .models import ExamAttempt, WritingResponse, SpeakingResponse, ReadingResponse
from .serializers import (
    AttemptSerializer, AttemptDetailSerializer,
    WritingResponseSerializer, SpeakingResponseSerializer, ReadingResponseSerializer
)
from .scoring import score_all_reading


def feature_error(message, code='feature_locked', http_status=status.HTTP_403_FORBIDDEN):
    return Response({'error': message, 'code': code}, status=http_status)


@api_view(['POST'])
def create_attempt(request):
    exam_id = request.data.get('exam_id')
    mode = request.data.get('mode', 'practice')
    section = request.data.get('section', '')

    try:
        exam = Exam.objects.get(id=exam_id, is_active=True)
    except Exam.DoesNotExist:
        return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

    if mode == 'full_exam' or section == 'full_exam':
        if not request.user.can_access_full_exam():
            return feature_error('Your current plan does not include the full exam.')
    elif section == 'writing':
        if not request.user.can_access_writing():
            return feature_error('Your current plan does not include writing access.')
    elif section == 'speaking':
        if not request.user.can_access_speaking():
            return feature_error('Your current plan does not include speaking access.')
    elif section == 'reading':
        if not request.user.can_access_reading():
            return feature_error('Your current plan does not include reading access.')

    if section == 'speaking':
        existing_attempt = ExamAttempt.objects.filter(
            user=request.user,
            exam=exam,
            mode=mode,
            status=ExamAttempt.STATUS_IN_PROGRESS,
            speaking_responses__isnull=True,
        ).order_by('-started_at').first()
        if existing_attempt:
            return Response(AttemptSerializer(existing_attempt).data, status=status.HTTP_200_OK)

    bypass_ai_credits = request.headers.get('X-ITC-App') == 'frontendFET'

    attempt = ExamAttempt.objects.create(
        user=request.user,
        exam=exam,
        mode=mode,
        bypass_ai_credits=bypass_ai_credits,
    )
    return Response(AttemptSerializer(attempt).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def attempt_detail(request, attempt_id):
    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response(AttemptDetailSerializer(attempt).data)


@api_view(['POST'])
def submit_writing(request, attempt_id):
    from apps.marking.tasks import mark_writing_response

    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not request.user.can_access_writing():
        return feature_error('Your current plan does not include writing access.')

    responses_data = request.data.get('responses', [])
    if not responses_data:
        return Response({'error': 'No responses provided'}, status=status.HTTP_400_BAD_REQUEST)

    valid_items = []
    for item in responses_data:
        question_id = item.get('question_id')
        text = item.get('text', '').strip()
        if not text or len(text) < 5:
            continue
        try:
            question = WritingQuestion.objects.get(id=question_id, exam=attempt.exam)
        except WritingQuestion.DoesNotExist:
            continue
        valid_items.append((question, text))

    if not valid_items:
        return Response({'error': 'No valid writing responses found.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.user.plan == request.user.PLAN_BASIC and not attempt.bypass_ai_credits:
        return feature_error('AI marking is available on Promo Trial and AI Practice only.', code='ai_marking_locked')
    if request.user.plan == request.user.PLAN_FREE:
        return feature_error('Please purchase a plan to use writing.', code='plan_required')
    created_ids = []
    queued_ids = []
    reused_existing = False

    with transaction.atomic():
        attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
        user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)

        new_items = []
        for question, text in valid_items:
            existing = WritingResponse.objects.filter(
                attempt=attempt,
                question=question,
            ).order_by('-submitted_at').first()

            if existing and existing.text.strip() == text and existing.mark_status in (
                WritingResponse.STATUS_PENDING,
                WritingResponse.STATUS_MARKING,
                WritingResponse.STATUS_DONE,
            ):
                created_ids.append(str(existing.id))
                reused_existing = True
                continue

            new_items.append((question, text))

        required_credits = 0 if attempt.bypass_ai_credits else len(new_items)
        if user.ai_credits < required_credits:
            return feature_error(
                f'You need {required_credits} AI credits for this submission.',
                code='insufficient_credits',
                http_status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        for question, text in new_items:
            response = WritingResponse.objects.create(
                attempt=attempt,
                question=question,
                text=text,
            )
            response_id = str(response.id)
            created_ids.append(response_id)
            queued_ids.append(response_id)

    for response_id in queued_ids:
        mark_writing_response.delay(response_id)

    return Response({
        'status': 'marking',
        'writing_response_ids': created_ids,
        'credits_used': 0,
        'remaining_credits': request.user.ai_credits,
        'message': 'Marking in progress. AI credits will be charged only after the report is successfully generated.',
        'reused_existing': reused_existing,
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
def submit_speaking(request, attempt_id):
    from apps.marking.tasks import mark_speaking_response

    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not request.user.can_access_speaking():
        return feature_error('Your current plan does not include speaking access.')
    if not request.user.can_use_ai_marking():
        return feature_error('You need AI credits to score speaking.', code='insufficient_credits', http_status=status.HTTP_402_PAYMENT_REQUIRED)

    transcript = request.data.get('transcript', [])
    if not transcript:
        return Response({'error': 'No transcript provided'}, status=status.HTTP_400_BAD_REQUEST)

    remaining_credits = request.user.ai_credits
    with transaction.atomic():
        attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
        user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
        credits_to_charge = 1 if attempt.speaking_chat_credit_charged else 2
        if user.ai_credits < credits_to_charge:
            return feature_error(f'Speaking assessment needs {credits_to_charge} more AI credit(s).', code='insufficient_credits', http_status=status.HTTP_402_PAYMENT_REQUIRED)
        user.ai_credits -= credits_to_charge
        user.save(update_fields=['ai_credits'])
        remaining_credits = user.ai_credits

        response = SpeakingResponse.objects.create(
            attempt=attempt,
            transcript=transcript,
            credits_charged=credits_to_charge,
        )
        mark_speaking_response.delay(str(response.id))

    return Response({
        'status': 'marking',
        'speaking_response_id': str(response.id),
        'credits_used': credits_to_charge,
        'remaining_credits': remaining_credits,
        'message': 'Marking in progress.',
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
def submit_reading(request, attempt_id):
    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not request.user.can_access_reading():
        return feature_error('Your current plan does not include reading access.')

    answers_by_part = request.data.get('answers', {})
    result = score_all_reading(attempt.exam, answers_by_part)

    reading_response = ReadingResponse.objects.create(
        attempt=attempt,
        answers=answers_by_part,
        total_score=result['total'],
        max_score=result['max'],
        percentage=result['percentage'],
        part_scores=result['part_scores'],
    )

    return Response(ReadingResponseSerializer(reading_response).data)


@api_view(['POST'])
def complete_attempt(request, attempt_id):
    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    attempt.status = ExamAttempt.STATUS_COMPLETE
    attempt.completed_at = timezone.now()
    attempt.save()
    return Response({'status': 'complete', 'completed_at': attempt.completed_at})


@api_view(['POST'])
def speaking_chat(request, attempt_id):
    import anthropic
    from django.conf import settings
    from apps.exams.models import SpeakingPart

    try:
        attempt = ExamAttempt.objects.get(id=attempt_id, user=request.user)
    except ExamAttempt.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not request.user.can_access_speaking():
        return feature_error('Your current plan does not include speaking access.')

    messages = request.data.get('messages', [])
    if not messages:
        return Response({'error': 'No messages'}, status=status.HTTP_400_BAD_REQUEST)

    charged_now = False
    with transaction.atomic():
        attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
        user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
        if not attempt.speaking_chat_credit_charged:
            if user.ai_credits < 1:
                return feature_error('You need at least 1 AI credit to start the speaking examiner.', code='insufficient_credits', http_status=status.HTTP_402_PAYMENT_REQUIRED)
            user.ai_credits -= 1
            user.save(update_fields=['ai_credits'])
            attempt.speaking_chat_credit_charged = True
            attempt.save(update_fields=['speaking_chat_credit_charged'])
            charged_now = True

    parts = SpeakingPart.objects.filter(exam=attempt.exam).order_by('order', 'part')
    system = settings.SPEAKING_EXAMINER_PROMPT + '\n\nSPEAKING TEST STRUCTURE:\n\n'
    for p in parts:
        system += f'=== {p.label} ===\nInstructions: {p.instruction}\n'
        if p.part in ('1', '4'):
            system += 'Questions:\n'
            for i, q in enumerate(p.questions, 1):
                system += f'  {i}. {q}\n'
        elif p.part == '2':
            system += f'Compare:\n  A: {p.situation_a}\n  B: {p.situation_b}\n'
        elif p.part == '3':
            system += f'Central question: "{p.central_question}"\n'
            system += f'Options: {" / ".join(p.options)}\n'
        system += '\n'
    system += f'\nBegin by warmly greeting the student, explain there are {parts.count()} parts, then start Part 1.'

    if not settings.ANTHROPIC_API_KEY:
        if charged_now:
            with transaction.atomic():
                attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
                user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
                user.ai_credits += 1
                user.save(update_fields=['ai_credits'])
                attempt.speaking_chat_credit_charged = False
                attempt.save(update_fields=['speaking_chat_credit_charged'])
        return Response(
            {'error': 'Anthropic API key is not configured on the backend.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        result = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=600,
            system=system,
            messages=messages,
        )
        reply = result.content[0].text
    except Exception:
        if charged_now:
            with transaction.atomic():
                attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
                user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
                user.ai_credits += 1
                user.save(update_fields=['ai_credits'])
                attempt.speaking_chat_credit_charged = False
                attempt.save(update_fields=['speaking_chat_credit_charged'])
        raise

    return Response({
        'reply': reply,
        'system': system,
        'credits_charged': 1 if charged_now else 0,
        'start_credit_already_used': not charged_now,
    })


@api_view(['GET'])
def my_attempts(request):
    attempts = ExamAttempt.objects.filter(
        user=request.user,
        status=ExamAttempt.STATUS_COMPLETE
    ).select_related('exam')[:20]
    return Response(AttemptSerializer(attempts, many=True).data)


@api_view(['GET'])
def my_fet_attempts(request):
    attempts = (
        ExamAttempt.objects.filter(
            user=request.user,
            exam__exam_family=Exam.FAMILY_FET,
            writing_responses__isnull=False,
        )
        .select_related('exam')
        .prefetch_related('writing_responses__question')
        .distinct()
        .order_by('-started_at')[:12]
    )
    return Response(AttemptDetailSerializer(attempts, many=True).data)
