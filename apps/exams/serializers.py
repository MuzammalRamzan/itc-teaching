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
    is_complete = serializers.SerializerMethodField()
    activation_block_reason = serializers.SerializerMethodField()
    has_writing_content = serializers.ReadOnlyField()
    has_reading_content = serializers.ReadOnlyField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'time_mins', 'exam_family', 'created_at',
                  'question_count', 'is_active', 'is_complete', 'activation_block_reason',
                  'has_writing_content', 'has_reading_content']

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_is_complete(self, obj):
        return obj.is_complete_for_activation

    def get_activation_block_reason(self, obj):
        return obj.activation_block_reason


class ExamDetailSerializer(serializers.ModelSerializer):
    questions = WritingQuestionSerializer(many=True, read_only=True)
    speaking_parts = SpeakingPartSerializer(many=True, read_only=True)
    reading_parts = ReadingPartSerializer(many=True, read_only=True)
    is_complete = serializers.SerializerMethodField()
    activation_block_reason = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'time_mins', 'exam_family', 'created_at',
                  'is_active', 'is_complete', 'activation_block_reason', 'questions', 'speaking_parts', 'reading_parts']

    def get_is_complete(self, obj):
        return obj.is_complete_for_activation

    def get_activation_block_reason(self, obj):
        return obj.activation_block_reason


class ExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = ['title', 'description', 'time_mins', 'exam_family', 'is_active']

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['is_active'] = False
        exam = Exam.objects.create(created_by=user, **validated_data)
        # Auto-create the 6 reading part slots
        for part_num in range(1, 7):
            ReadingPart.objects.create(exam=exam, part_number=part_num)
        return exam
