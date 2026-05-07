from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Exam, WritingQuestion, SpeakingPart, ReadingPart
from .serializers import (
    ExamListSerializer, ExamDetailSerializer, ExamCreateSerializer,
    WritingQuestionSerializer, SpeakingPartSerializer,
    ReadingPartSerializer, ReadingPartAdminSerializer
)
from .permissions import IsAdminUser


def _admin_only(request):
    return bool(request.user and request.user.is_authenticated and request.user.is_admin)


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _exam_queryset_for_request(request):
    queryset = (
        Exam.objects
        .filter(is_deleted=False)
        .prefetch_related('questions', 'reading_parts', 'speaking_parts')
        .order_by('-created_at')
    )
    include_inactive = _parse_bool(request.query_params.get('include_inactive')) if hasattr(request, 'query_params') else False
    if not (_admin_only(request) and include_inactive):
        queryset = queryset.filter(is_active=True)
    return queryset


def _sync_exam_activation(exam):
    if exam.is_active and not exam.is_complete_for_activation:
        exam.is_active = False
        exam.save(update_fields=['is_active'])
    return exam


def _validate_list(name, value):
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise ValueError(f'{name} must be a list.')
    return value


def _normalize_writing_question(item, part, order):
    if not isinstance(item, dict):
        raise ValueError(f'Writing part {part} question payload must be an object.')

    question_type = (item.get('question_type') or '').strip() or WritingQuestion.TYPE_EMAIL
    if question_type not in {choice[0] for choice in WritingQuestion.QUESTION_TYPES}:
        raise ValueError(f'Unsupported writing question type: {question_type}')

    return {
        'part': part,
        'question_type': question_type,
        'label': (item.get('label') or f'Question {part}').strip() or f'Question {part}',
        'instruction': item.get('instruction', '') or '',
        'write_instruction': item.get('write_instruction', '') or '',
        'word_count': int(item.get('word_count') or (50 if part == 1 else 100)),
        'required': bool(item.get('required', part == 1)),
        'order': int(item.get('order') or order),
        'email_from': item.get('email_from', '') or '',
        'email_subject': item.get('email_subject', '') or '',
        'email_body': item.get('email_body', '') or '',
        'notes': _validate_list('notes', item.get('notes', [])),
        'prompt_title': item.get('prompt_title', '') or '',
        'prompt_heading': item.get('prompt_heading', '') or '',
        'prompt_items': _validate_list('prompt_items', item.get('prompt_items', [])),
        'story_opener': item.get('story_opener', '') or '',
    }


def _import_fet_exam_payload(payload, user, exam=None):
    if not isinstance(payload, dict):
        raise ValueError('The uploaded JSON must be an object.')

    title = (payload.get('title') or '').strip()
    if not title:
        raise ValueError('Exam title is required.')

    description = payload.get('description', '') or ''
    time_mins = int(payload.get('time_mins') or 45)
    writing = payload.get('writing') or {}
    reading_items = payload.get('reading') or payload.get('reading_parts') or []
    if not isinstance(writing, dict):
        raise ValueError('`writing` must be an object.')
    reading_items = _validate_list('reading', reading_items)

    writing_rows = []
    part1 = writing.get('part1')
    if part1:
        writing_rows.append(_normalize_writing_question(part1, 1, 1))
    for index, item in enumerate(_validate_list('writing.part2', writing.get('part2', [])), start=2):
        writing_rows.append(_normalize_writing_question(item, 2, index))

    reading_by_part = {}
    for item in reading_items:
        if not isinstance(item, dict):
            raise ValueError('Each reading part must be an object.')
        part_number = int(item.get('part_number') or 0)
        if part_number < 1 or part_number > 5:
            raise ValueError('Reading part_number must be between 1 and 5.')
        content = item.get('content', {})
        if not isinstance(content, dict):
            raise ValueError(f'Reading part {part_number} content must be an object.')
        reading_by_part[part_number] = content

    with transaction.atomic():
        if exam is None:
            exam = Exam.objects.create(
                title=title,
                description=description,
                time_mins=time_mins,
                exam_family=Exam.FAMILY_FET,
                created_by=user,
                is_active=False,
            )
            for part_num in range(1, 6):
                ReadingPart.objects.create(exam=exam, part_number=part_num)
        else:
            exam.title = title
            exam.description = description
            exam.time_mins = time_mins
            exam.exam_family = Exam.FAMILY_FET
            exam.save(update_fields=['title', 'description', 'time_mins', 'exam_family'])

        WritingQuestion.objects.filter(exam=exam).delete()
        SpeakingPart.objects.filter(exam=exam).delete()

        for row in writing_rows:
            WritingQuestion.objects.create(exam=exam, **row)

        for part_num in range(1, 6):
            part, _ = ReadingPart.objects.get_or_create(exam=exam, part_number=part_num)
            content = reading_by_part.get(part_num, {})
            part.content = content
            part.has_content = bool(content)
            part.save(update_fields=['content', 'has_content'])

    return _sync_exam_activation(exam)


def _import_general_writing_payload(payload, user, exam=None):
    if not isinstance(payload, dict):
        raise ValueError('The uploaded JSON must be an object.')

    title = (payload.get('title') or '').strip()
    if not title:
        raise ValueError('Exam title is required.')

    description = payload.get('description', '') or ''
    time_mins = int(payload.get('time_mins') or 45)
    writing = payload.get('writing') or {}
    if not isinstance(writing, dict):
        raise ValueError('`writing` must be an object.')

    writing_rows = []
    part1 = writing.get('part1')
    if part1:
        writing_rows.append(_normalize_writing_question(part1, 1, 1))
    for index, item in enumerate(_validate_list('writing.part2', writing.get('part2', [])), start=2):
        writing_rows.append(_normalize_writing_question(item, 2, index))

    if not writing_rows:
        raise ValueError('At least one writing question is required.')

    with transaction.atomic():
        if exam is None:
            exam = Exam.objects.create(
                title=title,
                description=description,
                time_mins=time_mins,
                exam_family=Exam.FAMILY_GENERAL,
                created_by=user,
                is_active=False,
            )
            for part_num in range(1, 6):
                ReadingPart.objects.create(exam=exam, part_number=part_num)
        else:
            exam.title = title
            exam.description = description
            exam.time_mins = time_mins
            exam.exam_family = Exam.FAMILY_GENERAL
            exam.save(update_fields=['title', 'description', 'time_mins', 'exam_family'])

        WritingQuestion.objects.filter(exam=exam).delete()
        for row in writing_rows:
            WritingQuestion.objects.create(exam=exam, **row)

    return _sync_exam_activation(exam)


# ── Exam CRUD ──

@api_view(['GET', 'POST'])
def exam_list(request):
    if request.method == 'GET':
        exams = _exam_queryset_for_request(request)
        family = (request.query_params.get('family') or '').strip().lower()
        if family in {Exam.FAMILY_GENERAL, Exam.FAMILY_FET}:
            exams = exams.filter(exam_family=family)
        # Filter by primary_skill so the admin can list "Writing exams" and
        # "Reading exams" as independent libraries even though they share
        # the same Exam table.
        primary_skill = (request.query_params.get('primary_skill') or '').strip().lower()
        if primary_skill in {Exam.SKILL_WRITING, Exam.SKILL_READING, Exam.SKILL_SPEAKING}:
            exams = exams.filter(primary_skill=primary_skill)

        page_param = request.query_params.get('page')
        if page_param is None:
            return Response(ExamListSerializer(exams, many=True).data)

        try:
            page = max(1, int(page_param))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(50, int(request.query_params.get('page_size', 12))))
        except (TypeError, ValueError):
            page_size = 12

        total = exams.count()
        start = (page - 1) * page_size
        end = start + page_size
        page_items = list(exams[start:end])
        return Response({
            'results': ExamListSerializer(page_items, many=True).data,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total + page_size - 1) // page_size),
            'has_next': end < total,
            'has_prev': page > 1,
        })

    if request.method == 'POST':
        if not _admin_only(request):
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            exam = serializer.save()
            return Response(ExamDetailSerializer(exam).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def exam_detail(request, exam_id):
    try:
        if _admin_only(request) and request.method in {'PUT', 'DELETE'}:
            exam = Exam.objects.filter(is_deleted=False).get(id=exam_id)
        else:
            exam = _exam_queryset_for_request(request).get(id=exam_id)
    except Exam.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(ExamDetailSerializer(exam).data)

    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PUT':
        for field in ['title', 'description', 'time_mins', 'exam_family']:
            if field in request.data:
                setattr(exam, field, request.data[field])
        if 'is_active' in request.data:
            requested_active = _parse_bool(request.data.get('is_active'))
            if requested_active and not exam.is_complete_for_activation:
                exam.is_active = False
                exam.save()
                return Response({
                    'error': exam.activation_block_reason,
                    'exam': ExamDetailSerializer(exam).data,
                }, status=status.HTTP_400_BAD_REQUEST)
            exam.is_active = requested_active
        exam.save()
        exam = _sync_exam_activation(exam)
        return Response(ExamDetailSerializer(exam).data)

    if request.method == 'DELETE':
        exam.is_deleted = True
        exam.is_active = False
        exam.save()
        return Response({'detail': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)


# ── Writing Questions ──

@api_view(['POST'])
def add_writing_question(request, exam_id):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data.copy()
    data['exam'] = exam.id
    serializer = WritingQuestionSerializer(data=data)
    if serializer.is_valid():
        question = serializer.save(exam=exam)
        _sync_exam_activation(exam)
        return Response(WritingQuestionSerializer(question).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_writing_question(request, exam_id, question_id):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        question = WritingQuestion.objects.get(id=question_id, exam_id=exam_id)
    except WritingQuestion.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        question.delete()
        _sync_exam_activation(question.exam)
        return Response({'detail': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)

    serializer = WritingQuestionSerializer(question, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        _sync_exam_activation(question.exam)
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Speaking Parts ──

@api_view(['POST'])
def add_speaking_part(request, exam_id):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SpeakingPartSerializer(data=request.data)
    if serializer.is_valid():
        part = serializer.save(exam=exam)
        _sync_exam_activation(exam)
        return Response(SpeakingPartSerializer(part).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
def update_speaking_part(request, exam_id, part_id):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        part = SpeakingPart.objects.get(id=part_id, exam_id=exam_id)
    except SpeakingPart.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        part.delete()
        _sync_exam_activation(part.exam)
        return Response({'detail': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)

    serializer = SpeakingPartSerializer(part, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        _sync_exam_activation(part.exam)
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Reading Parts ──

@api_view(['PUT'])
def update_reading_part(request, exam_id, part_number):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        part = ReadingPart.objects.get(exam_id=exam_id, part_number=part_number)
    except ReadingPart.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    content = request.data.get('content', {})
    part.content = content
    part.has_content = bool(content)
    part.save()
    _sync_exam_activation(part.exam)
    return Response(ReadingPartAdminSerializer(part).data)


@api_view(['POST'])
@parser_classes([JSONParser])
def import_reading_content(request, exam_id):
    """Bulk-import all reading parts from a single JSON payload.

    Body shape (any subset of parts may be omitted — only provided parts get
    updated, others left untouched). The 5-part FET reading layout:

        {
          "parts": {
            "1": { "signs": [ { from, to, body, signoff, question, options[3], correct, why_en, why_ar, evidence } ] },
            "2": { "topic": "...", "passage": "... [GAP1] …", "gaps": [ { n, options[3], correct, why_en, why_ar, evidence } ] },
            "3": { "people": [...], "questions": [ { n, text, correct, why_en, why_ar, evidence } ] },
            "4": { "items": [ { n, place: { name, body }, people: [...], correct, why_en, why_ar, evidence } ] },
            "5": { "article": { title, byline, paragraphs: [...] }, "questions": [ { n, text, options[4], correct, focus_paragraph, highlight, why_en, why_ar, evidence } ] }
          }
        }
    """
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        exam = Exam.objects.get(id=exam_id, is_deleted=False)
    except Exam.DoesNotExist:
        return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data
    if not isinstance(payload, dict):
        return Response({'error': 'Payload must be a JSON object.'}, status=status.HTTP_400_BAD_REQUEST)
    parts_payload = payload.get('parts')
    if not isinstance(parts_payload, dict):
        return Response({'error': 'Payload must include a "parts" object keyed by part number (1–5).'}, status=status.HTTP_400_BAD_REQUEST)

    # Optional top-level metadata. Lets admins ship the exam title (and a
    # description / time) as part of the same JSON file so they don't have
    # to edit the exam name separately after upload.
    title_from_json = (payload.get('title') or '').strip()
    description_from_json = payload.get('description')
    time_mins_from_json = payload.get('time_mins')
    exam_meta_changed = False
    if title_from_json:
        exam.title = title_from_json
        exam_meta_changed = True
    if isinstance(description_from_json, str):
        exam.description = description_from_json
        exam_meta_changed = True
    if time_mins_from_json is not None:
        try:
            tm = int(time_mins_from_json)
            if tm > 0:
                exam.time_mins = tm
                exam_meta_changed = True
        except (TypeError, ValueError):
            pass
    if exam_meta_changed:
        exam.save(update_fields=['title', 'description', 'time_mins'])

    updated = []
    skipped = []
    errors = {}

    for part_key, content in parts_payload.items():
        # Accept "1" / 1 / "part1" / "Part 1" — extract the int.
        try:
            num = int(str(part_key).strip().lower().replace('part', '').replace(' ', ''))
        except ValueError:
            errors[str(part_key)] = 'Invalid part key — must be 1, 2, 3, 4, or 5.'
            continue
        if num < 1 or num > 5:
            errors[str(part_key)] = 'Part number must be between 1 and 5.'
            continue
        if not isinstance(content, dict):
            errors[str(num)] = 'Content for this part must be a JSON object.'
            continue

        part, _created = ReadingPart.objects.get_or_create(
            exam=exam, part_number=num, defaults={'content': {}, 'has_content': False},
        )
        part.content = content
        part.has_content = bool(content)
        part.save()
        updated.append({
            'part_number': num,
            'has_content': part.has_content,
            'question_count': part.question_count,
        })

    # List parts not touched so the admin sees what stayed the same.
    for p in ReadingPart.objects.filter(exam=exam):
        if not any(u['part_number'] == p.part_number for u in updated):
            skipped.append({'part_number': p.part_number, 'has_content': p.has_content, 'question_count': p.question_count})

    _sync_exam_activation(exam)
    return Response({
        'message': f'Imported reading content for {len(updated)} part(s).',
        'updated': updated,
        'skipped': skipped,
        'errors': errors or None,
    })


@api_view(['POST'])
@parser_classes([JSONParser])
def import_fet_exam(request):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    exam_id = request.data.get('exam_id')
    exam = None
    if exam_id:
      try:
          exam = Exam.objects.get(id=exam_id)
      except Exam.DoesNotExist:
          return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.get('payload', request.data)
    try:
        saved_exam = _import_fet_exam_payload(payload, request.user, exam=exam)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(ExamDetailSerializer(saved_exam).data, status=status.HTTP_201_CREATED if exam is None else status.HTTP_200_OK)


@api_view(['POST'])
@parser_classes([JSONParser])
def import_general_writing_exam(request):
    if not _admin_only(request):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    exam_id = request.data.get('exam_id')
    exam = None
    if exam_id:
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.get('payload', request.data)
    try:
        saved_exam = _import_general_writing_payload(payload, request.user, exam=exam)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(ExamDetailSerializer(saved_exam).data, status=status.HTTP_201_CREATED if exam is None else status.HTTP_200_OK)
