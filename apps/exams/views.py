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
        if part_number < 1 or part_number > 6:
            raise ValueError('Reading part_number must be between 1 and 6.')
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
            )
            for part_num in range(1, 7):
                ReadingPart.objects.create(exam=exam, part_number=part_num)
        else:
            exam.title = title
            exam.description = description
            exam.time_mins = time_mins
            exam.exam_family = Exam.FAMILY_FET
            exam.is_active = True
            exam.save(update_fields=['title', 'description', 'time_mins', 'exam_family', 'is_active'])

        WritingQuestion.objects.filter(exam=exam).delete()
        SpeakingPart.objects.filter(exam=exam).delete()

        for row in writing_rows:
            WritingQuestion.objects.create(exam=exam, **row)

        for part_num in range(1, 7):
            part, _ = ReadingPart.objects.get_or_create(exam=exam, part_number=part_num)
            content = reading_by_part.get(part_num, {})
            part.content = content
            part.has_content = bool(content)
            part.save(update_fields=['content', 'has_content'])

    return exam


# ── Exam CRUD ──

@api_view(['GET', 'POST'])
def exam_list(request):
    if request.method == 'GET':
        exams = Exam.objects.filter(is_active=True)
        family = (request.query_params.get('family') or '').strip().lower()
        if family in {Exam.FAMILY_GENERAL, Exam.FAMILY_FET}:
            exams = exams.filter(exam_family=family)
        return Response(ExamListSerializer(exams, many=True).data)

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
        exam = Exam.objects.get(id=exam_id, is_active=True)
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
        exam.save()
        return Response(ExamDetailSerializer(exam).data)

    if request.method == 'DELETE':
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
        return Response({'detail': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)

    serializer = WritingQuestionSerializer(question, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
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
        return Response({'detail': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)

    serializer = SpeakingPartSerializer(part, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
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
    return Response(ReadingPartAdminSerializer(part).data)


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
