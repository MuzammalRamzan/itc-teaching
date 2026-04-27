from rest_framework import serializers
from .models import ExamAttempt, WritingResponse, SpeakingResponse, ReadingResponse


def _max_total_for_question(question):
    return 10 if getattr(question, 'part', None) == 1 else 20


def _max_total_for_response(response):
    return _max_total_for_question(getattr(response, 'question', None))


def _clean_feedback(text):
    return ' '.join((text or '').split())


def _combine_feedback(responses, attr):
    seen = set()
    items = []
    for response in responses:
        value = _clean_feedback(getattr(response, attr, ''))
        if value and value not in seen:
            seen.add(value)
            items.append(value)
    return ' '.join(items)


def _build_overall_writing_feedback(task_breakdown, responses):
    total = sum(item['total'] for item in task_breakdown)
    max_total = sum(item['max_total'] for item in task_breakdown) or 1
    ratio = total / max_total
    missing_task = any(item['status'] != 'done' for item in task_breakdown)
    zero_reasons = [_clean_feedback(response.zero_reason) for response in responses if _clean_feedback(response.zero_reason)]

    if zero_reasons:
        zero_reason = ' '.join(dict.fromkeys(zero_reasons))
    elif missing_task:
        zero_reason = 'One writing task was not completed, so the overall score is reduced.'
    else:
        zero_reason = ''

    strengths = _combine_feedback(responses, 'strengths')
    improvements = _combine_feedback(responses, 'improvements')
    suggestion = _combine_feedback(responses, 'suggestion')

    if ratio <= 0.2:
        strengths = ''
        improvements = 'Too little successful language was produced across the test to achieve a strong result. More relevant content, fuller development, and clearer organisation are needed.'
        suggestion = 'Complete both tasks and make sure each required point is answered with enough language to be assessed securely.'
    else:
        if missing_task:
            extra = ' Complete both writing tasks to access the full score range.'
            improvements = f'{improvements}{extra}'.strip() if improvements else 'Complete both writing tasks to access the full score range.'
        if not strengths and ratio >= 0.4:
            strengths = 'Some relevant content is communicated, but performance is still inconsistent across the full writing test.'
        if not improvements:
            improvements = 'Develop the ideas more fully and make the organisation, vocabulary, and grammar more consistent across the whole test.'
        if not suggestion:
            suggestion = 'Before time ends, check that every task point has been addressed and that each answer is long enough to be assessed properly.'

    return {
        'strengths': strengths,
        'improvements': improvements,
        'suggestion': suggestion,
        'zero_reason': zero_reason,
    }


def _build_task_details(responses):
    task_details = []
    for response in sorted(
        responses,
        key=lambda item: (
            getattr(getattr(item, 'question', None), 'part', 99),
            getattr(getattr(item, 'question', None), 'order', 99),
        ),
    ):
        feedback_json = response.feedback_json if isinstance(response.feedback_json, dict) else {}
        task_details.append({
            'id': str(response.id),
            'label': getattr(response.question, 'label', 'Question'),
            'part': getattr(response.question, 'part', None),
            'question_type': getattr(response.question, 'question_type', ''),
            'total': int(response.total or 0),
            'max_total': _max_total_for_response(response),
            'scores': response.scores,
            'strengths': response.strengths,
            'improvements': response.improvements,
            'suggestion': response.suggestion,
            'zero_reason': response.zero_reason,
            'mark_status': response.mark_status,
            # FET v2 structured feedback
            'student_level': response.student_level,
            'potential_score': response.potential_score,
            'well_done': response.well_done,
            'practice_task': response.practice_task,
            'criteria': feedback_json.get('criteria') or [],
            'improvements_detail': feedback_json.get('improvements') or [],
        })
    return task_details


class WritingResponseSerializer(serializers.ModelSerializer):
    scores = serializers.ReadOnlyField()
    question_label = serializers.CharField(source='question.label', read_only=True)
    question_part = serializers.IntegerField(source='question.part', read_only=True)
    question_order = serializers.IntegerField(source='question.order', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    max_total = serializers.SerializerMethodField()
    criteria = serializers.SerializerMethodField()
    improvements_detail = serializers.SerializerMethodField()

    def get_max_total(self, obj):
        return _max_total_for_response(obj)

    def get_criteria(self, obj):
        feedback = obj.feedback_json if isinstance(obj.feedback_json, dict) else {}
        return feedback.get('criteria') or []

    def get_improvements_detail(self, obj):
        feedback = obj.feedback_json if isinstance(obj.feedback_json, dict) else {}
        return feedback.get('improvements') or []

    class Meta:
        model = WritingResponse
        fields = ['id', 'question_label', 'question_part', 'question_order', 'question_type', 'text', 'mark_status', 'scores', 'max_total',
                  'total', 'band', 'cefr', 'strengths', 'improvements',
                  'suggestion', 'zero_reason',
                  'student_level', 'potential_score', 'well_done', 'practice_task',
                  'criteria', 'improvements_detail',
                  'submitted_at', 'marked_at']


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
    writing_report = serializers.SerializerMethodField()
    fet_writing_report = serializers.SerializerMethodField()

    def _build_combined_writing_report(self, attempt):
        responses = list(attempt.writing_responses.select_related('question').all())
        if not responses:
            return None

        if any(response.mark_status in (WritingResponse.STATUS_PENDING, WritingResponse.STATUS_MARKING) for response in responses):
            return {
                'id': str(attempt.id),
                'question_label': 'FET Writing Test' if getattr(attempt.exam, 'exam_family', '') == 'fet' else 'Writing Test',
                'question_labels': [getattr(response.question, 'label', 'Question') for response in responses],
                'question_count': len(responses),
                'mark_status': 'marking',
            }

        if any(response.mark_status == WritingResponse.STATUS_FAILED for response in responses):
            return {
                'id': str(attempt.id),
                'question_label': 'FET Writing Test' if getattr(attempt.exam, 'exam_family', '') == 'fet' else 'Writing Test',
                'question_labels': [getattr(response.question, 'label', 'Question') for response in responses],
                'question_count': len(responses),
                'mark_status': 'failed',
                'zero_reason': 'One or more writing answers could not be marked successfully.',
            }

        done_responses = [response for response in responses if response.mark_status == WritingResponse.STATUS_DONE]
        if not done_responses:
            return None

        part1_response = next((response for response in done_responses if getattr(response.question, 'part', None) == 1), None)
        part2_response = next((response for response in done_responses if getattr(response.question, 'part', None) == 2), None)
        part1_question = next((question for question in attempt.exam.questions.all() if question.part == 1), None)
        part2_question = next((question for question in attempt.exam.questions.all() if question.part == 2), None)

        task_breakdown = []
        if part1_question or part1_response:
            task_breakdown.append({
                'label': getattr(getattr(part1_response, 'question', None), 'label', None) or getattr(part1_question, 'label', 'Question 1'),
                'total': int(part1_response.total or 0) if part1_response else 0,
                'max_total': 10,
                'status': 'done' if part1_response else 'not_answered',
            })
        if part2_question or part2_response:
            task_breakdown.append({
                'label': getattr(getattr(part2_response, 'question', None), 'label', None) or getattr(part2_question, 'label', 'Question 2'),
                'total': int(part2_response.total or 0) if part2_response else 0,
                'max_total': 20,
                'status': 'done' if part2_response else 'not_answered',
            })

        total = sum(item['total'] for item in task_breakdown)
        max_total = sum(item['max_total'] for item in task_breakdown)
        feedback = _build_overall_writing_feedback(task_breakdown, done_responses)

        return {
            'id': str(attempt.id),
            'question_label': 'FET Writing Test' if getattr(attempt.exam, 'exam_family', '') == 'fet' else 'Writing Test',
            'question_labels': [getattr(response.question, 'label', 'Question') for response in done_responses],
            'question_count': len(done_responses),
            'mark_status': 'done',
            'total': total,
            'max_total': max_total,
            'band': '',
            'cefr': '',
            'task_breakdown': task_breakdown,
            'task_details': _build_task_details(done_responses),
            'strengths': feedback['strengths'],
            'improvements': feedback['improvements'],
            'suggestion': feedback['suggestion'],
            'zero_reason': feedback['zero_reason'],
        }

    def get_writing_report(self, attempt):
        return self._build_combined_writing_report(attempt)

    def get_fet_writing_report(self, attempt):
        if getattr(attempt.exam, 'exam_family', '') != 'fet':
            return None
        return self._build_combined_writing_report(attempt)

    class Meta:
        model = ExamAttempt
        fields = ['id', 'exam_id', 'exam_title', 'mode', 'status',
                  'started_at', 'completed_at',
                  'writing_responses', 'speaking_responses', 'reading_responses', 'writing_report', 'fet_writing_report']
