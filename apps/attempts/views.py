import uuid

from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from datetime import date, timedelta

from apps.authentication.credits import create_credit_transaction
from apps.exams.models import Exam, WritingQuestion, SpeakingPart
from .models import ExamAttempt, WritingResponse, SpeakingResponse, ReadingResponse, CalendarEvent, UserBreakOptIn
from .serializers import (
    AttemptSerializer, AttemptDetailSerializer,
    WritingResponseSerializer, SpeakingResponseSerializer, ReadingResponseSerializer,
    CalendarEventSerializer, CalendarEventAdminSerializer,
)
from .scoring import score_all_reading


def _user_active_away_event(user):
    """Returns the CalendarEvent the user has marked 'away' covering today, or None."""
    if not user or not user.is_authenticated:
        return None
    today = date.today()
    return (
        CalendarEvent.objects.filter(
            is_active=True,
            starts_at__lte=today,
            ends_at__gte=today,
            opt_ins__user=user,
            opt_ins__away=True,
        )
        .order_by('starts_at')
        .first()
    )


def feature_error(message, code='feature_locked', http_status=status.HTTP_403_FORBIDDEN):
    return Response({'error': message, 'code': code}, status=http_status)


@api_view(['POST'])
def create_attempt(request):
    exam_id = request.data.get('exam_id')
    mode = request.data.get('mode', 'practice')
    section = request.data.get('section', '')
    is_fet_app = request.headers.get('X-ITC-App') == 'frontendFET'

    try:
        exam = Exam.objects.get(id=exam_id, is_active=True)
    except Exam.DoesNotExist:
        return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

    # Block practice when the user is currently inside a break they've opted to be away for.
    if section in {'writing', 'reading', 'speaking'} or mode == 'full_exam':
        away_event = _user_active_away_event(request.user)
        if away_event is not None:
            return Response(
                {
                    'error': f'You\'re marked as away during "{away_event.name}". Practice resumes after the break.',
                    'code': 'on_break',
                    'event': {
                        'id': str(away_event.id),
                        'name': away_event.name,
                        'starts_at': away_event.starts_at.isoformat(),
                        'ends_at': away_event.ends_at.isoformat(),
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    if mode == 'full_exam' or section == 'full_exam':
        if not request.user.can_access_full_exam():
            return feature_error('Your current plan does not include the full exam.')
    elif section == 'writing':
        if not request.user.can_access_writing():
            return feature_error('Your current plan does not include writing access.')
        if is_fet_app and request.user.ai_credits < 1:
            return feature_error(
                'You need at least 1 AI credit before starting this writing submission.',
                code='insufficient_credits',
                http_status=status.HTTP_402_PAYMENT_REQUIRED,
            )
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

    attempt = ExamAttempt.objects.create(
        user=request.user,
        exam=exam,
        mode=mode,
        bypass_ai_credits=False,
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
    created_ids = []
    queued_ids = []
    reused_existing = False
    remaining_credits = request.user.ai_credits

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

        required_credits = 0 if attempt.bypass_ai_credits or not new_items else 1
        if user.ai_credits < required_credits:
            return feature_error(
                f'You need {required_credits} AI credits for this submission.',
                code='insufficient_credits',
                http_status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        submission_group_id = uuid.uuid4() if new_items else None

        for index, (question, text) in enumerate(new_items):
            response = WritingResponse.objects.create(
                attempt=attempt,
                question=question,
                text=text,
                submission_group_id=submission_group_id,
                credits_charged=False,
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
        'remaining_credits': remaining_credits,
        'message': 'Marking in progress. 1 AI credit will be deducted after the report is generated successfully.' if queued_ids else 'Marking in progress.',
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
        create_credit_transaction(
            user=user,
            delta=-credits_to_charge,
            description=f'{credits_to_charge} credits spent on speaking assessment for {attempt.exam.title}.',
            source_type='speaking_scoring',
            source_id=attempt.id,
            metadata={
                'attempt_id': str(attempt.id),
                'exam_id': str(attempt.exam_id),
                'exam_title': attempt.exam.title,
            },
        )
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
            create_credit_transaction(
                user=user,
                delta=-1,
                description=f'1 credit spent to start speaking test for {attempt.exam.title}.',
                source_type='speaking_start',
                source_id=attempt.id,
                metadata={
                    'attempt_id': str(attempt.id),
                    'exam_id': str(attempt.exam_id),
                    'exam_title': attempt.exam.title,
                },
            )
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
                create_credit_transaction(
                    user=user,
                    delta=1,
                    description=f'1 credit refunded for speaking test start on {attempt.exam.title}.',
                    source_type='speaking_start_refund',
                    source_id=attempt.id,
                    metadata={'attempt_id': str(attempt.id), 'exam_id': str(attempt.exam_id), 'exam_title': attempt.exam.title},
                )
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
                create_credit_transaction(
                    user=user,
                    delta=1,
                    description=f'1 credit refunded for speaking test start on {attempt.exam.title}.',
                    source_type='speaking_start_refund',
                    source_id=attempt.id,
                    metadata={'attempt_id': str(attempt.id), 'exam_id': str(attempt.exam_id), 'exam_title': attempt.exam.title},
                )
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
    attempts = (
        ExamAttempt.objects.filter(user=request.user)
        .filter(
            Q(status=ExamAttempt.STATUS_COMPLETE)
            | Q(writing_responses__isnull=False)
            | Q(speaking_responses__isnull=False)
            | Q(reading_responses__isnull=False)
        )
        .select_related('exam')
        .distinct()
        .order_by('-started_at')[:20]
    )
    return Response(AttemptSerializer(attempts, many=True).data)


@api_view(['GET'])
def my_fet_attempts(request):
    # Returns the calling user's recent writing-bearing attempts. Was previously
    # gated to exam_family='fet' but the frontendFET app also creates 'general'
    # attempts; this endpoint is only consumed by frontendFET so the looser
    # filter is the right semantic.
    attempts = (
        ExamAttempt.objects.filter(
            user=request.user,
            writing_responses__isnull=False,
        )
        .select_related('exam')
        .prefetch_related('writing_responses__question', 'reading_responses')
        .distinct()
        .order_by('-started_at')[:12]
    )
    return Response(AttemptDetailSerializer(attempts, many=True).data)


@api_view(['GET'])
def calendar_events(request):
    """Lists active calendar events with current user's away opt-in state."""
    today = date.today()
    qs = CalendarEvent.objects.filter(is_active=True, ends_at__gte=today).order_by('order', 'starts_at')

    try:
        limit = max(1, min(20, int(request.query_params.get('limit', 6))))
    except (TypeError, ValueError):
        limit = 6
    qs = qs[:limit]

    return Response(CalendarEventSerializer(qs, many=True, context={'request': request}).data)


@api_view(['POST'])
def calendar_event_opt_in(request, event_id):
    """Mark the current user as 'away' (or back) for a specific calendar event."""
    try:
        event = CalendarEvent.objects.get(id=event_id, is_active=True)
    except CalendarEvent.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)

    away = bool(request.data.get('away', False))
    opt_in, _ = UserBreakOptIn.objects.update_or_create(
        user=request.user, event=event, defaults={'away': away}
    )
    return Response(CalendarEventSerializer(event, context={'request': request}).data)


# ── Admin: manage calendar events ──

def _admin_required(request):
    if not request.user or not request.user.is_authenticated or not getattr(request.user, 'is_admin', False):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    return None


@api_view(['GET', 'POST'])
def calendar_events_admin(request):
    forbidden = _admin_required(request)
    if forbidden:
        return forbidden

    if request.method == 'GET':
        qs = CalendarEvent.objects.all().order_by('order', 'starts_at')
        return Response(CalendarEventAdminSerializer(qs, many=True).data)

    serializer = CalendarEventAdminSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    event = serializer.save()
    return Response(CalendarEventAdminSerializer(event).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
def calendar_event_admin_detail(request, event_id):
    forbidden = _admin_required(request)
    if forbidden:
        return forbidden

    try:
        event = CalendarEvent.objects.get(id=event_id)
    except CalendarEvent.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(CalendarEventAdminSerializer(event).data)

    if request.method == 'DELETE':
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = CalendarEventAdminSerializer(event, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    event = serializer.save()
    return Response(CalendarEventAdminSerializer(event).data)


# ── FET dashboard ──────────────────────────────────────────────────────────
#
# Aggregates a unified per-exam progress view from existing attempt + response
# rows (no schema change). Powers the Duolingo-style dashboard at /dashboard.
#
# Per-exam progress is computed across all three skills:
#   tasks_total = (writing tasks) + (reading parts with content) + (speaking
#                 parts with content)
#   tasks_done  = number of those the user has submitted at least once
#
# Response shape:
#   {
#     "user": { "name", "first_name" },
#     "overall_progress": int,
#     "continue_learning": null | { exam_id, exam_title, subtitle, tasks_done,
#                                   tasks_total, pct, last_activity, skill_hint },
#     "next_up": null | { same shape, no last_activity },
#     "in_progress": [...],
#     "completed": [...],
#     "streak_days": int
#   }


def _compute_exam_progress_for_user(user):
    """Returns a list of per-exam summaries, sorted by last_activity desc."""
    from apps.exams.models import ReadingPart  # local import to avoid cycles
    from collections import defaultdict

    # Pull every admin-active exam — both family='general' and family='fet' —
    # so the dashboard shows the full set of papers a student can work on.
    # Filtering by family was dropping exams the user expected to see here.
    exams_qs = Exam.objects.filter(
        is_active=True, is_deleted=False,
    ).order_by('-created_at')
    # Defensive dedupe by id (in case a future migration introduces dupes).
    seen_exam_ids = set()
    exams = []
    for ex in exams_qs:
        if ex.id in seen_exam_ids: continue
        seen_exam_ids.add(ex.id)
        exams.append(ex)

    # Writing tasks are counted at the PART level, not per-question. The
    # writing exam has 2 parts: Part 1 (mandatory single question) and
    # Part 2 (multiple topic options, the user picks ONE). So the per-exam
    # writing total is "how many parts have at least one question" — never
    # more than 2 — and a part is "done" when the user has submitted any
    # response for any of that part's questions.
    writing_parts_meta = defaultdict(set)  # exam_id → {1, 2}
    for wq in WritingQuestion.objects.values('exam_id', 'part').distinct():
        writing_parts_meta[str(wq['exam_id'])].add(int(wq['part']))
    # Map exam_id → which question_id belongs to which part, so we can
    # convert WritingResponse.question_id → part when building "done" set.
    question_part_map = {}  # str(question_id) → int(part)
    for wq in WritingQuestion.objects.values('id', 'part'):
        question_part_map[str(wq['id'])] = int(wq['part'])
    writing_totals = {ex_id: len(parts) for ex_id, parts in writing_parts_meta.items()}

    reading_totals = defaultdict(int)
    reading_parts_meta = defaultdict(set)  # exam_id → {part_numbers with content}
    for rp in ReadingPart.objects.all():
        if rp.has_content and getattr(rp, 'question_count', 0) > 0:
            reading_parts_meta[str(rp.exam_id)].add(rp.part_number)
    for ex_id, parts in reading_parts_meta.items():
        reading_totals[ex_id] = len(parts)

    speaking_totals = defaultdict(int)
    for sp in SpeakingPart.objects.all():
        if sp.has_content:
            speaking_totals[str(sp.exam_id)] += 1

    # All attempts for this user, with response rows prefetched in batch so
    # we don't fire 3 queries per attempt as we iterate (N+1 → ~4 queries
    # total regardless of attempt count). Critical for users with 100+ exams.
    user_attempts = list(
        ExamAttempt.objects.filter(user=user)
        .select_related('exam')
        .prefetch_related('writing_responses', 'reading_responses', 'speaking_responses')
    )
    attempts_by_exam = defaultdict(list)
    for a in user_attempts:
        attempts_by_exam[str(a.exam_id)].append(a)

    # Build "completed parts" sets per exam.
    writing_done = defaultdict(set)   # exam_id → {1, 2}  (writing PART numbers)
    reading_done = defaultdict(set)   # exam_id → {part_number}
    speaking_done = defaultdict(int)  # exam_id → count of speaking responses

    last_activity = {}  # exam_id → datetime

    for a in user_attempts:
        ex_id = str(a.exam_id)
        # Writing — a part is "done" when the user has any response for any
        # question in that part. Submitting Q1 marks Part 1 done; submitting
        # any one of the Part 2 topic options marks Part 2 done.
        for wr in a.writing_responses.all():
            part_num = question_part_map.get(str(wr.question_id))
            if part_num is not None:
                writing_done[ex_id].add(part_num)
            last_activity[ex_id] = max(last_activity.get(ex_id, wr.submitted_at), wr.submitted_at)
        # Reading — collect part numbers from part_scores JSON
        for rr in a.reading_responses.all():
            for ps in (rr.part_scores or []):
                pn = ps.get('part_number') if isinstance(ps, dict) else None
                if pn is not None:
                    reading_done[ex_id].add(int(pn))
            last_activity[ex_id] = max(last_activity.get(ex_id, rr.submitted_at), rr.submitted_at)
        # Speaking — coarse: each response = 1 speaking part touched
        speaking_done[ex_id] += a.speaking_responses.count()
        for sr in a.speaking_responses.all():
            last_activity[ex_id] = max(last_activity.get(ex_id, sr.submitted_at), sr.submitted_at)

    summaries = []
    for ex in exams:
        ex_id = str(ex.id)
        w_total = writing_totals.get(ex_id, 0)
        r_total = reading_totals.get(ex_id, 0)
        s_total = speaking_totals.get(ex_id, 0)
        tasks_total = w_total + r_total + s_total
        if tasks_total == 0:
            continue  # exam has no content — skip from dashboard

        w_done = len(writing_done.get(ex_id, set()))
        r_done = len(reading_done.get(ex_id, set()))
        s_done = min(speaking_done.get(ex_id, 0), s_total)
        tasks_done = w_done + r_done + s_done

        pct = round((tasks_done / tasks_total) * 100) if tasks_total else 0
        if pct >= 100:
            status_label = 'completed'
        elif tasks_done > 0:
            status_label = 'in_progress'
        else:
            status_label = 'not_started'

        # Pick a subtitle — prefer first writing question label, else exam description
        subtitle = (ex.description or '').strip()
        if not subtitle and w_total > 0:
            first_q = WritingQuestion.objects.filter(exam=ex).order_by('order', 'part').first()
            if first_q and first_q.label:
                subtitle = first_q.label

        # Skill hint: which skill has the most progress / most content
        if w_total >= r_total and w_total >= s_total:
            skill_hint = 'writing'
        elif r_total >= s_total:
            skill_hint = 'reading'
        else:
            skill_hint = 'speaking'

        # Per-skill breakdown so the dashboard can show "Writing 2/2 ✓,
        # Reading 3/6, Speaking 0/4" chips on every card.
        skills = {
            'writing': {
                'done': min(w_done, w_total), 'total': w_total,
                'has_content': w_total > 0,
                'pct': round((w_done / w_total) * 100) if w_total else 0,
                'status': 'completed' if w_total and w_done >= w_total else 'in_progress' if w_done > 0 else 'not_started',
            },
            'reading': {
                'done': min(r_done, r_total), 'total': r_total,
                'has_content': r_total > 0,
                'pct': round((r_done / r_total) * 100) if r_total else 0,
                'status': 'completed' if r_total and r_done >= r_total else 'in_progress' if r_done > 0 else 'not_started',
            },
            'speaking': {
                'done': min(s_done, s_total), 'total': s_total,
                'has_content': s_total > 0,
                'pct': round((s_done / s_total) * 100) if s_total else 0,
                'status': 'completed' if s_total and s_done >= s_total else 'in_progress' if s_done > 0 else 'not_started',
            },
        }

        # Pick the "next skill to resume" — first skill with content that
        # isn't finished. Order: writing → reading → speaking. The Resume
        # CTA on the dashboard sends the user straight into this skill flow.
        next_skill = None
        for sk in ('writing', 'reading', 'speaking'):
            if skills[sk]['has_content'] and skills[sk]['status'] != 'completed':
                next_skill = sk
                break

        last_act = last_activity.get(ex_id)
        summaries.append({
            'exam_id': ex_id,
            'exam_title': ex.title or 'Untitled exam',
            'subtitle': subtitle[:140] if subtitle else '',
            'time_mins': int(getattr(ex, 'time_mins', 0) or 0),
            'tasks_done': tasks_done,
            'tasks_total': tasks_total,
            'pct': pct,
            'status': status_label,
            'skill_hint': skill_hint,
            'skills': skills,
            'next_skill': next_skill,
            'last_activity': last_act.isoformat() if last_act else None,
            'has_writing_content': w_total > 0,
            'has_reading_content': r_total > 0,
            'has_speaking_content': s_total > 0,
        })

    # Sort: most-recent activity first, then not-started exams after
    summaries.sort(
        key=lambda s: (s['last_activity'] or '', s['exam_title']),
        reverse=True,
    )
    return summaries


def _streak_days_for_user(user):
    """Counts consecutive days (ending today) the user has submitted anything."""
    today = timezone.now().date()
    activity_dates = set()
    for ts in WritingResponse.objects.filter(attempt__user=user).values_list('submitted_at', flat=True):
        if ts: activity_dates.add(ts.date())
    for ts in ReadingResponse.objects.filter(attempt__user=user).values_list('submitted_at', flat=True):
        if ts: activity_dates.add(ts.date())
    for ts in SpeakingResponse.objects.filter(attempt__user=user).values_list('submitted_at', flat=True):
        if ts: activity_dates.add(ts.date())
    if not activity_dates: return 0
    streak = 0
    cur = today
    while cur in activity_dates:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak


@api_view(['GET'])
def fet_dashboard(request):
    user = request.user
    if not user.is_authenticated:
        return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

    summaries = _compute_exam_progress_for_user(user)
    in_progress = [s for s in summaries if s['status'] == 'in_progress']
    completed = [s for s in summaries if s['status'] == 'completed']
    not_started = [s for s in summaries if s['status'] == 'not_started']

    # Continue learning — most recent in-progress.
    continue_learning = in_progress[0] if in_progress else None

    # Next up — first not-started exam (admin order). None if everything started.
    next_up = not_started[0] if not_started else None

    # Overall progress = avg pct across all exams that have any content.
    if summaries:
        overall = round(sum(s['pct'] for s in summaries) / len(summaries))
    else:
        overall = 0

    # Average score (real exam scores, not task completion). Pulled from
    # response rows that actually carry a percentage.
    score_samples = []
    for rr in ReadingResponse.objects.filter(attempt__user=user, percentage__isnull=False):
        score_samples.append(rr.percentage)
    for wr in WritingResponse.objects.filter(attempt__user=user, total__isnull=False):
        if wr.total is None:
            continue
        # Each marked criterion is out of 5. The rubric uses a different
        # number of criteria per writing part: Part 1 has 2 criteria
        # (max 10), Part 2 has 4 criteria (max 20). The legacy formula
        # `total / 30 * 100` was wrong — derive the real max from which
        # criterion fields were actually scored.
        criteria = [wr.score_content, wr.score_communicative, wr.score_organisation, wr.score_language]
        max_score = sum(5 for c in criteria if c is not None)
        if max_score <= 0:
            continue
        score_samples.append(round((wr.total / max_score) * 100))
    average_score = round(sum(score_samples) / len(score_samples)) if score_samples else 0

    # Current level — derived from average score, CEFR-style cut-offs.
    if average_score >= 85:
        current_level = {'cefr': 'C1', 'label': 'Advanced'}
    elif average_score >= 70:
        current_level = {'cefr': 'B2', 'label': 'Intermediate'}
    elif average_score >= 55:
        current_level = {'cefr': 'B1', 'label': 'Intermediate'}
    elif average_score >= 40:
        current_level = {'cefr': 'A2', 'label': 'Elementary'}
    elif score_samples:
        current_level = {'cefr': 'A1', 'label': 'Beginner'}
    else:
        current_level = {'cefr': '—', 'label': 'Not yet rated'}

    # This week vs last week — count DISTINCT exams the user submitted any
    # response for, not the raw count of response rows. Writing has 2
    # responses per exam (Q1+Q2) and reading practice can be 6+ per exam,
    # so the previous "count rows" behaviour was inflating the number.
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    last_week_start = week_start - timedelta(days=7)
    this_week_exams = set()
    last_week_exams = set()
    daily_active = {i: False for i in range(7)}  # 0=Mon … 6=Sun

    def _ingest(qs):
        # qs yields (submitted_at, attempt__exam_id) tuples
        for ts, exam_id in qs:
            if not ts: continue
            d = ts.date()
            if d >= week_start:
                this_week_exams.add(exam_id)
            if last_week_start <= d < week_start:
                last_week_exams.add(exam_id)
            if d >= week_start and (d - week_start).days < 7:
                daily_active[(d - week_start).days] = True

    _ingest(WritingResponse.objects.filter(attempt__user=user).values_list('submitted_at', 'attempt__exam_id'))
    _ingest(ReadingResponse.objects.filter(attempt__user=user).values_list('submitted_at', 'attempt__exam_id'))
    _ingest(SpeakingResponse.objects.filter(attempt__user=user).values_list('submitted_at', 'attempt__exam_id'))

    this_week_count = len(this_week_exams)
    last_week_count = len(last_week_exams)
    weekly_activity = [
        {'label': lbl, 'active': daily_active[i]}
        for i, lbl in enumerate(['M', 'T', 'W', 'T', 'F', 'S', 'S'])
    ]

    # Skill breakdown — avg pct per skill across all exams that have content
    # for that skill (regardless of attempt status).
    skill_totals = {'writing': 0, 'reading': 0, 'listening': 0, 'speaking': 0}
    skill_counts = {'writing': 0, 'reading': 0, 'listening': 0, 'speaking': 0}
    for s in summaries:
        for sk in ('writing', 'reading', 'speaking'):
            sub = s.get('skills', {}).get(sk, {})
            if sub.get('has_content'):
                skill_totals[sk] += sub.get('pct', 0)
                skill_counts[sk] += 1
    skill_breakdown = {
        sk: {
            'pct': round(skill_totals[sk] / skill_counts[sk]) if skill_counts[sk] else 0,
            'has_content': skill_counts[sk] > 0,
        }
        for sk in ('writing', 'reading', 'listening', 'speaking')
    }

    # Achievements — derived from real activity, no hardcoding of state.
    streak_days = _streak_days_for_user(user)
    total_attempts = ExamAttempt.objects.filter(user=user).count()
    achievements = [
        {
            'key': 'first_exam',
            'title': 'First Exam',
            'description': 'Completed your first exam',
            'icon': '🏅',
            'completed': len(completed) >= 1,
        },
        {
            'key': 'streak_5',
            'title': '5 Day Streak',
            'description': 'Studied 5 days in a row',
            'icon': '🔥',
            'completed': streak_days >= 5,
        },
        {
            'key': 'getting_started',
            'title': 'Getting Started',
            'description': 'Started your preparation journey',
            'icon': '🚀',
            'completed': total_attempts >= 1,
        },
        {
            'key': 'three_exams',
            'title': 'Triple Threat',
            'description': 'Completed 3 different exams',
            'icon': '🏆',
            'completed': len(completed) >= 3,
        },
    ]

    name = (getattr(user, 'name', '') or '').strip() or (user.email or '').split('@')[0]
    first_name = name.split(' ')[0] if name else 'there'
    initials = ''.join([p[0] for p in name.split(' ') if p][:2]).upper() or first_name[:2].upper()

    return Response({
        'user': {'name': name, 'first_name': first_name, 'initials': initials, 'email': user.email or ''},
        'overall_progress': overall,
        'average_score': average_score,
        'current_level': current_level,
        'this_week': {
            'count': this_week_count,
            'delta_vs_last_week': this_week_count - last_week_count,
        },
        'continue_learning': continue_learning,
        'next_up': next_up,
        'in_progress': in_progress,
        'completed': completed,
        'not_started': not_started,
        'all_exams': summaries,
        'skill_breakdown': skill_breakdown,
        'weekly_activity': weekly_activity,
        'achievements': achievements,
        'streak_days': streak_days,
    })
