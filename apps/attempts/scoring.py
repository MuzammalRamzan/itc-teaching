"""
Auto-scoring for the Reading section.
No AI needed — compares submitted answers against stored correct answers.

The 5-part layout (see ReadingPart.PART_TYPES) maps to these submission keys:
    Part 1 — Signs & Notices       sign_{i} → letter ('A'/'B'/'C')
    Part 2 — Gap Fill              gap_{i}  → option string ('even')
    Part 3 — Text Matching         q_{i}    → person id ('ali')
    Part 4 — People ↔ Place        q_{i}    → person id ('p2')
    Part 5 — Long Reading          q_{i}    → letter ('A'/'B'/'C'/'D')
"""


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def _norm(value):
    return str(value or '').strip().lower()


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

    if part == 1:  # Signs & Notices — single MCQ per sign
        for i, sign in enumerate(as_list(content.get('signs'))):
            sign = as_dict(sign)
            max_score += 1
            if _norm(submitted_answers.get(f'sign_{i}')) == _norm(sign.get('correct') or sign.get('answer')):
                score += 1

    elif part == 2:  # Gap Fill — pick from 3 options for each gap
        for i, gap in enumerate(as_list(content.get('gaps'))):
            gap = as_dict(gap)
            max_score += 1
            if _norm(submitted_answers.get(f'gap_{i}')) == _norm(gap.get('correct')):
                score += 1

    elif part == 3:  # Text Matching — match a question to one of N people
        for i, q in enumerate(as_list(content.get('questions'))):
            q = as_dict(q)
            max_score += 1
            if _norm(submitted_answers.get(f'q_{i}')) == _norm(q.get('correct')):
                score += 1

    elif part == 4:  # People ↔ Place — pick the person who fits the place
        for i, item in enumerate(as_list(content.get('items'))):
            item = as_dict(item)
            max_score += 1
            if _norm(submitted_answers.get(f'q_{i}')) == _norm(item.get('correct')):
                score += 1

    elif part == 5:  # Long Reading — A/B/C/D MCQ on the article
        for i, q in enumerate(as_list(content.get('questions'))):
            q = as_dict(q)
            max_score += 1
            if _norm(submitted_answers.get(f'q_{i}')) == _norm(q.get('correct')):
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
