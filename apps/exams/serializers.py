from rest_framework import serializers
from .models import Exam, WritingQuestion, SpeakingPart, ReadingPart


class WritingQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingQuestion
        exclude = ['exam']


class SpeakingPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakingPart
        exclude = ['exam']


class ReadingPartSerializer(serializers.ModelSerializer):
    type_name = serializers.ReadOnlyField()
    description = serializers.ReadOnlyField()
    question_count = serializers.ReadOnlyField()

    class Meta:
        model = ReadingPart
        exclude = ['exam']


class ReadingPartAdminSerializer(serializers.ModelSerializer):
    """Includes content for admin editing."""
    type_name = serializers.ReadOnlyField()
    description = serializers.ReadOnlyField()
    question_count = serializers.ReadOnlyField()

    class Meta:
        model = ReadingPart
        exclude = ['exam']


class ExamListSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'time_mins', 'created_at', 'question_count']

    def get_question_count(self, obj):
        return obj.questions.count()


class ExamDetailSerializer(serializers.ModelSerializer):
    questions = WritingQuestionSerializer(many=True, read_only=True)
    speaking_parts = SpeakingPartSerializer(many=True, read_only=True)
    reading_parts = ReadingPartSerializer(many=True, read_only=True)

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'time_mins', 'created_at',
                  'questions', 'speaking_parts', 'reading_parts']


class ExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = ['title', 'description', 'time_mins']

    def create(self, validated_data):
        user = self.context['request'].user
        exam = Exam.objects.create(created_by=user, **validated_data)
        # Auto-create the 6 reading part slots
        for part_num in range(1, 7):
            ReadingPart.objects.create(exam=exam, part_number=part_num)
        return exam
