import uuid
from django.db import models
from apps.authentication.models import User


class Exam(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    time_mins = models.IntegerField(default=45)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_exams')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'exams'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.count()


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


class ReadingPart(models.Model):
    PART_TYPES = [
        (1, 'Multiple Choice - Signs & Notices'),
        (2, 'Matching'),
        (3, 'True / False'),
        (4, 'Multiple Choice - Article'),
        (5, 'Multiple Choice Cloze'),
        (6, 'Open Cloze'),
    ]

    TYPE_DESCRIPTIONS = {
        1: 'Look at the text in each question. What does it say? Choose the correct explanation (A, B or C).',
        2: 'The people below all want to find an activity. Eight short texts describe different activities. Decide which would be most suitable for each person.',
        3: 'Look at the sentences below about a topic. Read the text to decide if each sentence is correct (True) or incorrect (False).',
        4: 'Read the article. For each question, choose the correct answer (A, B, C or D).',
        5: 'Read the text below and choose the correct word for each space (A, B, C or D).',
        6: 'Read the text below and write the missing word in each space. Use only ONE word.',
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
        c = self.content
        if self.part_number == 1:
            return len(c.get('signs', []))
        elif self.part_number == 2:
            return len(c.get('people', []))
        elif self.part_number == 3:
            return len(c.get('statements', []))
        elif self.part_number == 4:
            return len(c.get('questions', []))
        elif self.part_number == 5:
            return len(c.get('blanks', []))
        elif self.part_number == 6:
            return len(c.get('answers', []))
        return 0

    @property
    def type_name(self):
        return dict(self.PART_TYPES).get(self.part_number, '')

    @property
    def description(self):
        return self.TYPE_DESCRIPTIONS.get(self.part_number, '')
