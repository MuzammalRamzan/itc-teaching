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


# ── Exam CRUD ──

@api_view(['GET', 'POST'])
def exam_list(request):
    if request.method == 'GET':
        exams = Exam.objects.filter(is_active=True)
        return Response(ExamListSerializer(exams, many=True).data)

    if request.method == 'POST':
        if not request.user.is_admin:
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

    if not request.user.is_admin:
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PUT':
        for field in ['title', 'description', 'time_mins']:
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
    if not request.user.is_admin:
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
    if not request.user.is_admin:
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
    if not request.user.is_admin:
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
    if not request.user.is_admin:
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
    if not request.user.is_admin:
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
