"""
Auto-scoring for the Reading section.
No AI needed — compares submitted answers against stored correct answers.
"""

def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def score_reading_part(reading_part, submitted_answers):
    """
    Score a single reading part.
    Returns: {'score': int, 'max': int, 'part_number': int}
    """
    content = as_dict(reading_part.content)
    part = reading_part.part_number
    score = 0
    max_score = 0
    submitted_answers = as_dict(submitted_answers)

    if part == 1:  # Signs MCQ
        for i, sign in enumerate(as_list(content.get('signs'))):
            sign = as_dict(sign)
            max_score += 1
            if submitted_answers.get(f'sign_{i}') == sign.get('answer'):
                score += 1

    elif part == 2:  # Matching
        correct_answers = as_list(content.get('answers'))
        for i, correct in enumerate(correct_answers):
            max_score += 1
            if submitted_answers.get(f'person_{i}') == correct:
                score += 1

    elif part == 3:  # True/False
        for i, stmt in enumerate(as_list(content.get('statements'))):
            stmt = as_dict(stmt)
            max_score += 1
            if submitted_answers.get(f'stmt_{i}') == stmt.get('answer'):
                score += 1

    elif part == 4:  # MCQ Article
        for i, q in enumerate(as_list(content.get('questions'))):
            q = as_dict(q)
            max_score += 1
            if submitted_answers.get(f'q_{i}') == q.get('answer'):
                score += 1

    elif part == 5:  # MCQ Cloze
        for i, blank in enumerate(as_list(content.get('blanks'))):
            blank = as_dict(blank)
            max_score += 1
            if submitted_answers.get(f'blank_{i}') == blank.get('answer'):
                score += 1

    elif part == 6:  # Open Cloze
        for i, answer in enumerate(as_list(content.get('answers'))):
            max_score += 1
            submitted = str(submitted_answers.get(f'open_{i}', '')).strip().lower()
            if submitted == str(answer or '').lower():
                score += 1

    return {'score': score, 'max': max_score, 'part_number': part}


def score_all_reading(exam, submitted_answers_by_part):
    """
    Score all reading parts.
    submitted_answers_by_part: {'1': {...}, '2': {...}, ...}
    Returns: {'total': int, 'max': int, 'percentage': int, 'part_scores': [...]}
    """
    from apps.exams.models import ReadingPart

    parts = ReadingPart.objects.filter(exam=exam, has_content=True)
    total = 0
    max_total = 0
    part_scores = []

    submitted_answers_by_part = as_dict(submitted_answers_by_part)

    for part in parts:
        part_answers = as_dict(submitted_answers_by_part.get(str(part.part_number), {}))
        result = score_reading_part(part, part_answers)
        total += result['score']
        max_total += result['max']
        part_scores.append(result)

    percentage = round((total / max_total * 100) if max_total > 0 else 0)

    return {
        'total': total,
        'max': max_total,
        'percentage': percentage,
        'part_scores': part_scores,
    }
