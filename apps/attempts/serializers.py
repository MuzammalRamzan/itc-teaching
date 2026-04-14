from rest_framework import serializers
from .models import ExamAttempt, WritingResponse, SpeakingResponse, ReadingResponse


def _band_from_total(total):
    if total >= 18:
        return 'A'
    if total >= 15:
        return 'B'
    if total >= 12:
        return 'C'
    if total >= 10:
        return 'D'
    return 'U'


def _build_overall_strengths(score_content, score_communicative, score_organisation, score_language):
    parts = []

    if score_content >= 4:
        parts.append('You address the task requirements well across the whole test and support your ideas with relevant detail.')
    elif score_content >= 3:
        parts.append('You generally cover the task requirements and include enough supporting detail to communicate your main ideas.')

    if score_communicative >= 4:
        parts.append('Your tone is appropriate for the tasks and your message remains clear and engaging for the reader.')
    elif score_communicative >= 3:
        parts.append('Your writing is generally easy to follow and communicates your purpose clearly in most parts of the test.')

    if score_organisation >= 4:
        parts.append('Your ideas are organised logically, with clear progression from one point to the next.')
    elif score_organisation >= 3:
        parts.append('Your writing has a clear overall structure and is mostly organised in a sensible way.')

    if score_language >= 4:
        parts.append('You show good control of vocabulary and grammar, with a range that supports the tasks well.')
    elif score_language >= 3:
        parts.append('Your language is generally accurate and appropriate, and it usually supports clear communication.')

    if not parts:
        parts.append('You communicate the main ideas across the test and show a clear attempt to respond to the tasks.')

    return ' '.join(parts[:3])


def _build_overall_improvements(score_content, score_communicative, score_organisation, score_language):
    parts = []

    if score_content < 4:
        parts.append('Develop key points a little more fully and make sure every task point is covered with enough specific detail.')
    if score_communicative < 4:
        parts.append('Keep the reader and purpose in mind more consistently so the tone stays strong across the full test.')
    if score_organisation < 4:
        parts.append('Use clearer linking words and smoother paragraph progression to improve the overall flow of ideas.')
    if score_language < 4:
        parts.append('Show more variety in vocabulary and sentence structure while checking grammar carefully for accuracy.')

    if not parts:
        parts.append('To push this result even higher, aim for even more precise vocabulary and more flexible sentence patterns throughout the test.')

    return ' '.join(parts[:3])


def _build_overall_tip(score_content, score_communicative, score_organisation, score_language):
    lowest_area = min(
        [
            ('content', score_content),
            ('communicative', score_communicative),
            ('organisation', score_organisation),
            ('language', score_language),
        ],
        key=lambda item: item[1],
    )[0]

    tips = {
        'content': 'Before writing, quickly note the required points for each task so you can check that every point has been answered clearly.',
        'communicative': 'Before finishing, reread your answer and ask whether the tone, purpose, and message would feel clear to the intended reader.',
        'organisation': 'Plan a simple structure before writing, then use connectors such as "first", "also", "however", and "finally" to guide the reader.',
        'language': 'After drafting, revise a few sentences deliberately to improve vocabulary range and add more variety in sentence patterns.',
    }
    return tips[lowest_area]


class WritingResponseSerializer(serializers.ModelSerializer):
    scores = serializers.ReadOnlyField()
    question_label = serializers.CharField(source='question.label', read_only=True)
    question_part = serializers.IntegerField(source='question.part', read_only=True)
    question_order = serializers.IntegerField(source='question.order', read_only=True)

    class Meta:
        model = WritingResponse
        fields = ['id', 'question_label', 'question_part', 'question_order', 'text', 'mark_status', 'scores',
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
    fet_writing_report = serializers.SerializerMethodField()

    def get_fet_writing_report(self, attempt):
        if getattr(attempt.exam, 'exam_family', '') != 'fet':
            return None

        responses = list(attempt.writing_responses.select_related('question').all())
        if not responses:
            return None

        if any(response.mark_status in (WritingResponse.STATUS_PENDING, WritingResponse.STATUS_MARKING) for response in responses):
            return {
                'id': str(attempt.id),
                'question_label': 'FET Writing Test',
                'question_labels': [getattr(response.question, 'label', 'Question') for response in responses],
                'question_count': len(responses),
                'mark_status': 'marking',
            }

        if any(response.mark_status == WritingResponse.STATUS_FAILED for response in responses):
            return {
                'id': str(attempt.id),
                'question_label': 'FET Writing Test',
                'question_labels': [getattr(response.question, 'label', 'Question') for response in responses],
                'question_count': len(responses),
                'mark_status': 'failed',
                'zero_reason': 'One or more writing answers could not be marked successfully.',
            }

        done_responses = [response for response in responses if response.mark_status == WritingResponse.STATUS_DONE]
        if not done_responses:
            return None

        score_content = round(sum((response.score_content or 0) for response in done_responses) / len(done_responses))
        score_communicative = round(sum((response.score_communicative or 0) for response in done_responses) / len(done_responses))
        score_organisation = round(sum((response.score_organisation or 0) for response in done_responses) / len(done_responses))
        score_language = round(sum((response.score_language or 0) for response in done_responses) / len(done_responses))
        total = score_content + score_communicative + score_organisation + score_language
        cefr = next((response.cefr for response in done_responses if response.cefr), '')

        return {
            'id': str(attempt.id),
            'question_label': 'FET Writing Test',
            'question_labels': [getattr(response.question, 'label', 'Question') for response in done_responses],
            'question_count': len(done_responses),
            'mark_status': 'done',
            'scores': {
                'content': score_content,
                'communicative': score_communicative,
                'organisation': score_organisation,
                'language': score_language,
            },
            'total': total,
            'band': _band_from_total(total),
            'cefr': cefr,
            'strengths': _build_overall_strengths(
                score_content,
                score_communicative,
                score_organisation,
                score_language,
            ),
            'improvements': _build_overall_improvements(
                score_content,
                score_communicative,
                score_organisation,
                score_language,
            ),
            'suggestion': _build_overall_tip(
                score_content,
                score_communicative,
                score_organisation,
                score_language,
            ),
            'zero_reason': '',
        }

    class Meta:
        model = ExamAttempt
        fields = ['id', 'exam_id', 'exam_title', 'mode', 'status',
                  'started_at', 'completed_at',
                  'writing_responses', 'speaking_responses', 'reading_responses', 'fet_writing_report']
