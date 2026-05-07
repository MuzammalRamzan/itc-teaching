import uuid
from django.db import models
from apps.authentication.models import User


class Exam(models.Model):
    FAMILY_GENERAL = 'general'
    FAMILY_FET = 'fet'
    FAMILY_CHOICES = [
        (FAMILY_GENERAL, 'General'),
        (FAMILY_FET, 'FET'),
    ]

    # Primary skill an exam was created for. Drives which admin library it
    # appears in ("Writing exams" / "Reading exams" / "Speaking exams") and
    # how the dashboard groups it. Existing rows are backfilled by the
    # accompanying migration based on which content they actually carry.
    SKILL_WRITING = 'writing'
    SKILL_READING = 'reading'
    SKILL_SPEAKING = 'speaking'
    PRIMARY_SKILL_CHOICES = [
        (SKILL_WRITING, 'Writing'),
        (SKILL_READING, 'Reading'),
        (SKILL_SPEAKING, 'Speaking'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    time_mins = models.IntegerField(default=45)
    exam_family = models.CharField(max_length=20, choices=FAMILY_CHOICES, default=FAMILY_GENERAL)
    primary_skill = models.CharField(max_length=20, choices=PRIMARY_SKILL_CHOICES, default=SKILL_WRITING)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_exams')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'exams'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.count()

    @property
    def has_writing_content(self):
        return self.questions.exists()

    @property
    def has_speaking_content(self):
        return any(part.has_content for part in self.speaking_parts.all())

    @property
    def has_reading_content(self):
        return any(part.question_count > 0 for part in self.reading_parts.all())

    @property
    def is_complete_for_activation(self):
        return self.has_writing_content or self.has_speaking_content or self.has_reading_content

    @property
    def activation_block_reason(self):
        if self.is_complete_for_activation:
            return ''
        return 'This exam cannot be activated until at least one question or content section is added.'


class WritingQuestion(models.Model):
    TYPE_EMAIL = 'email'
    TYPE_ARTICLE = 'article'
    TYPE_STORY = 'story'
    TYPE_PICTURE = 'picture'
    QUESTION_TYPES = [
        (TYPE_EMAIL, 'Email'),
        (TYPE_ARTICLE, 'Article'),
        (TYPE_STORY, 'Story'),
        (TYPE_PICTURE, 'Picture'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    part = models.IntegerField(choices=[(1, 'Part 1'), (2, 'Part 2')], default=1)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default=TYPE_EMAIL)
    label = models.CharField(max_length=100, default='Question 1')
    instruction = models.TextField(blank=True, default='')
    write_instruction = models.TextField(blank=True, default='')
    word_count = models.IntegerField(default=100)
    required = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    # Email
    email_from = models.CharField(max_length=200, blank=True, default='')
    email_subject = models.CharField(max_length=300, blank=True, default='')
    email_body = models.TextField(blank=True, default='')
    notes = models.JSONField(default=list)
    # Article
    prompt_title = models.CharField(max_length=300, blank=True, default='')
    prompt_heading = models.CharField(max_length=300, blank=True, default='')
    prompt_items = models.JSONField(default=list)
    # Story
    story_opener = models.TextField(blank=True, default='')
    # Picture
    image = models.ImageField(upload_to='questions/', null=True, blank=True)

    class Meta:
        db_table = 'writing_questions'
        ordering = ['order', 'part']

    def __str__(self):
        return f'{self.exam.title} - {self.label}'


class SpeakingPart(models.Model):
    PART_CHOICES = [
        ('1', 'Part 1 - Interview'),
        ('2', 'Part 2 - Long Turn'),
        ('3', 'Part 3 - Collaborative'),
        ('4', 'Part 4 - Discussion'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='speaking_parts')
    part = models.CharField(max_length=1, choices=PART_CHOICES)
    label = models.CharField(max_length=200)
    instruction = models.TextField(blank=True, default='')
    order = models.IntegerField(default=0)
    # Part 1 & 4
    questions = models.JSONField(default=list)
    # Part 2
    situation_a = models.TextField(blank=True, default='')
    situation_b = models.TextField(blank=True, default='')
    # Part 3
    central_question = models.TextField(blank=True, default='')
    options = models.JSONField(default=list)

    class Meta:
        db_table = 'speaking_parts'
        ordering = ['order', 'part']

    def __str__(self):
        return f'{self.exam.title} - {self.label}'

    @property
    def has_content(self):
        if self.part in {'1', '4'}:
            return bool(self.questions)
        if self.part == '2':
            return bool((self.situation_a or '').strip() or (self.situation_b or '').strip())
        if self.part == '3':
            return bool((self.central_question or '').strip() or self.options)
        return False


class ReadingPart(models.Model):
    # New 5-part FET reading layout, mirroring the gallery design 1:1.
    # Old (pre-2026-05) parts 2/3/4/5/6 used different content shapes —
    # legacy data is wiped by the matching migration; admin must re-upload.
    PART_TYPES = [
        (1, 'Signs & Notices'),
        (2, 'Gap Fill'),
        (3, 'Text Matching'),
        (4, 'People ↔ Place'),
        (5, 'Long Reading'),
    ]

    TYPE_DESCRIPTIONS = {
        1: 'Read each short note or notice and choose the correct meaning (A, B or C).',
        2: 'Read the passage and choose the best word for each gap from three options.',
        3: 'Read three short personal texts. For each question, choose which person is being described.',
        4: 'For each place, read the description and pick the person whose needs match it best.',
        5: 'Read the article and answer the multiple-choice questions (A, B, C or D).',
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='reading_parts')
    part_number = models.IntegerField(choices=PART_TYPES)
    has_content = models.BooleanField(default=False)
    content = models.JSONField(default=dict)

    class Meta:
        db_table = 'reading_parts'
        ordering = ['part_number']
        unique_together = ['exam', 'part_number']

    def __str__(self):
        return f'{self.exam.title} - Reading Part {self.part_number}'

    @property
    def question_count(self):
        # Each part counts the number of scoreable questions in its content.
        # Shapes match gallery-frontend's data model exactly:
        #   1: { signs: [{ from, to, body, signoff, question, options[3], correct, why_en, why_ar, evidence }] }
        #   2: { topic, passage, gaps: [{ n, options[3], correct, why_en, why_ar, evidence }] }
        #   3: { people: [{ id, name, color, text }], questions: [{ n, text, correct, why_en, why_ar, evidence }] }
        #   4: { items: [{ n, place: { name, body }, people: [{ id, name, need }], correct, why_en, why_ar, evidence }] }
        #   5: { article: { title, byline, paragraphs[] }, questions: [{ n, text, options[4], correct, focus_paragraph, highlight, why_en, why_ar, evidence }] }
        c = self.content if isinstance(self.content, dict) else {}
        if self.part_number == 1:
            return len(c.get('signs', []) or [])
        elif self.part_number == 2:
            return len(c.get('gaps', []) or [])
        elif self.part_number == 3:
            return len(c.get('questions', []) or [])
        elif self.part_number == 4:
            return len(c.get('items', []) or [])
        elif self.part_number == 5:
            return len(c.get('questions', []) or [])
        return 0

    @property
    def type_name(self):
        return dict(self.PART_TYPES).get(self.part_number, '')

    @property
    def description(self):
        return self.TYPE_DESCRIPTIONS.get(self.part_number, '')
