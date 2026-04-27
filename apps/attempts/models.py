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
    student_level = models.CharField(max_length=4, blank=True, default='')
    potential_score = models.IntegerField(null=True, blank=True)
    well_done = models.TextField(blank=True, default='')
    practice_task = models.TextField(blank=True, default='')
    feedback_json = models.JSONField(blank=True, null=True, default=dict)
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


class CalendarEvent(models.Model):
    """Admin-managed academic-calendar events shown on the FET landing page."""

    ACCENT_GREEN = 'green'
    ACCENT_ORANGE = 'orange'
    ACCENT_BLUE = 'blue'
    ACCENT_PURPLE = 'purple'
    ACCENT_RED = 'red'
    ACCENT_CHOICES = [
        (ACCENT_GREEN, 'Green'),
        (ACCENT_ORANGE, 'Orange'),
        (ACCENT_BLUE, 'Blue'),
        (ACCENT_PURPLE, 'Purple'),
        (ACCENT_RED, 'Red'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    starts_at = models.DateField()
    ends_at = models.DateField()
    accent = models.CharField(max_length=10, choices=ACCENT_CHOICES, default=ACCENT_GREEN)
    hint = models.CharField(max_length=60, blank=True, default='')
    description = models.TextField(blank=True, default='')
    recommended_minutes_per_day = models.IntegerField(default=0, help_text='0 = full rest, 15 = light review, 25 = adjusted hours')
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'calendar_events'
        ordering = ['order', 'starts_at']

    def __str__(self):
        return f'{self.name} ({self.starts_at} → {self.ends_at})'


class UserBreakOptIn(models.Model):
    """Per-user opt-in for an academic break: 'I'll be away'."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='break_opt_ins')
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name='opt_ins')
    away = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_break_opt_ins'
        unique_together = ('user', 'event')
