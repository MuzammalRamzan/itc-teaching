import uuid
from django.db import models
from apps.authentication.models import User
from apps.exams.models import Exam, WritingQuestion


class ExamAttempt(models.Model):
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETE = 'complete'
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETE, 'Complete'),
    ]
    MODE_PRACTICE = 'practice'
    MODE_FULL_EXAM = 'full_exam'
    MODE_CHOICES = [
        (MODE_PRACTICE, 'Practice'),
        (MODE_FULL_EXAM, 'Full Exam'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attempts')
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name='attempts')
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_PRACTICE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    speaking_chat_credit_charged = models.BooleanField(default=False)
    bypass_ai_credits = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'exam_attempts'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user.name} - {self.exam.title} ({self.status})'


class WritingResponse(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_MARKING = 'marking'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_MARKING, 'Marking'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='writing_responses')
    question = models.ForeignKey(WritingQuestion, on_delete=models.PROTECT)
    submission_group_id = models.UUIDField(null=True, blank=True, db_index=True)
    text = models.TextField()
    mark_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Scores
    score_content = models.IntegerField(null=True)
    score_communicative = models.IntegerField(null=True)
    score_organisation = models.IntegerField(null=True)
    score_language = models.IntegerField(null=True)
    total = models.IntegerField(null=True)
    band = models.CharField(max_length=1, blank=True, default='')
    cefr = models.CharField(max_length=10, blank=True, default='')
    strengths = models.TextField(blank=True, default='')
    improvements = models.TextField(blank=True, default='')
    suggestion = models.TextField(blank=True, default='')
    zero_reason = models.TextField(blank=True, default='')
    credits_charged = models.BooleanField(default=False)
    credits_refunded = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'writing_responses'

    @property
    def scores(self):
        return {
            'content': self.score_content,
            'communicative': self.score_communicative,
            'organisation': self.score_organisation,
            'language': self.score_language,
        }


class SpeakingResponse(models.Model):
    STATUS_CHOICES = WritingResponse.STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='speaking_responses')
    transcript = models.JSONField(default=list)  # [{role: "ai"|"user", text: "..."}]
    mark_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    score_grammar = models.IntegerField(null=True)
    score_discourse = models.IntegerField(null=True)
    score_interaction = models.IntegerField(null=True)
    total = models.IntegerField(null=True)
    band = models.CharField(max_length=1, blank=True, default='')
    cefr = models.CharField(max_length=10, blank=True, default='')
    strengths = models.TextField(blank=True, default='')
    improvements = models.TextField(blank=True, default='')
    suggestion = models.TextField(blank=True, default='')
    credits_charged = models.IntegerField(default=2)
    credits_refunded = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'speaking_responses'

    @property
    def scores(self):
        return {
            'grammar': self.score_grammar,
            'discourse': self.score_discourse,
            'interaction': self.score_interaction,
        }


class ReadingResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='reading_responses')
    answers = models.JSONField(default=dict)
    total_score = models.IntegerField(null=True)
    max_score = models.IntegerField(null=True)
    percentage = models.IntegerField(null=True)
    part_scores = models.JSONField(default=list)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reading_responses'
