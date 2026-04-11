from rest_framework import serializers
from .models import ExamAttempt, WritingResponse, SpeakingResponse, ReadingResponse


class WritingResponseSerializer(serializers.ModelSerializer):
    scores = serializers.ReadOnlyField()
    question_label = serializers.CharField(source='question.label', read_only=True)

    class Meta:
        model = WritingResponse
        fields = ['id', 'question_label', 'text', 'mark_status', 'scores',
                  'total', 'band', 'cefr', 'strengths', 'improvements',
                  'suggestion', 'zero_reason', 'submitted_at', 'marked_at']


class SpeakingResponseSerializer(serializers.ModelSerializer):
    scores = serializers.ReadOnlyField()

    class Meta:
        model = SpeakingResponse
        fields = ['id', 'mark_status', 'scores', 'total', 'band', 'cefr',
                  'strengths', 'improvements', 'suggestion', 'submitted_at', 'marked_at']


class ReadingResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingResponse
        fields = ['id', 'total_score', 'max_score', 'percentage',
                  'part_scores', 'submitted_at']


class AttemptSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)

    class Meta:
        model = ExamAttempt
        fields = ['id', 'exam_id', 'exam_title', 'mode', 'status', 'started_at', 'completed_at']


class AttemptDetailSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    writing_responses = WritingResponseSerializer(many=True, read_only=True)
    speaking_responses = SpeakingResponseSerializer(many=True, read_only=True)
    reading_responses = ReadingResponseSerializer(many=True, read_only=True)

    class Meta:
        model = ExamAttempt
        fields = ['id', 'exam_id', 'exam_title', 'mode', 'status',
                  'started_at', 'completed_at',
                  'writing_responses', 'speaking_responses', 'reading_responses']
