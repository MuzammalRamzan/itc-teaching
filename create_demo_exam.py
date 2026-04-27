import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import uuid
from django.db import transaction

from apps.authentication.models import User
from apps.exams.models import Exam, ReadingPart, SpeakingPart, WritingQuestion


def main():
    admin_user = User.objects.filter(is_admin=True).first() or User.objects.first()
    if not admin_user:
        raise SystemExit("No users found in DB. Please login once so a user record is created.")

    with transaction.atomic():
        exam_title = f"B1 Mock Test (Demo) — {str(uuid.uuid4())[:8]}"

        exam = Exam.objects.create(
            title=exam_title,
            description="Demo exam for end-to-end testing (Writing + Speaking + Reading).",
            time_mins=45,
            created_by=admin_user,
            is_active=True,
        )

        WritingQuestion.objects.create(
            exam=exam,
            part=1,
            question_type=WritingQuestion.TYPE_EMAIL,
            label="Part 1 — Email to a friend",
            instruction="Write an email to your friend.",
            write_instruction="Write about 100 words.",
            word_count=100,
            required=True,
            order=1,
            email_from="Ali",
            email_subject="Weekend plans",
            email_body="Hi!\n\nAre you free this weekend? I want to go out in Riyadh.\n\nWhat do you want to do?\n\nSee you!",
            notes=["Suggest a plan", "Suggest a time", "Ask a question"],
        )

        WritingQuestion.objects.create(
            exam=exam,
            part=2,
            question_type=WritingQuestion.TYPE_STORY,
            label="Part 2 — Short story",
            instruction="Write a story.",
            write_instruction="Write about 100 words.",
            word_count=120,
            required=False,
            order=2,
            story_opener="When I opened the door, I couldn't believe what I saw.",
        )

        SpeakingPart.objects.create(
            exam=exam,
            part="1",
            label="Part 1 - Interview",
            instruction="Answer the examiner's questions.",
            order=1,
            questions=[
                "What is your name?",
                "Where are you from?",
                "What do you do every day?",
                "What do you like about learning English?",
            ],
        )

        SpeakingPart.objects.create(
            exam=exam,
            part="2",
            label="Part 2 - Long Turn",
            instruction="Compare the two situations. Speak for about 1 minute.",
            order=2,
            situation_a="A student studying in a quiet library.",
            situation_b="A student studying with friends in a cafe.",
        )

        SpeakingPart.objects.create(
            exam=exam,
            part="3",
            label="Part 3 - Collaborative Task",
            instruction="Discuss the options and choose the best one.",
            order=3,
            central_question="How can we improve English practice at home?",
            options=["Watch short videos", "Speak with a partner", "Read simple stories", "Use flashcards"],
        )

        SpeakingPart.objects.create(
            exam=exam,
            part="4",
            label="Part 4 - Discussion",
            instruction="Answer the examiner's questions.",
            order=4,
            questions=[
                "Do you think English is important for work? Why?",
                "What is the best way to learn new words?",
            ],
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=1,
            has_content=True,
            content={
                "signs": [
                    {
                        "text": "No Entry",
                        "optA": "You cannot go in here",
                        "optB": "You must pay here",
                        "optC": "You can park here",
                        "answer": "A",
                    },
                    {
                        "text": "Keep Off The Grass",
                        "optA": "Sit here",
                        "optB": "Do not walk on the grass",
                        "optC": "Buy food here",
                        "answer": "B",
                    },
                    {
                        "text": "Staff Only",
                        "optA": "Only workers may enter",
                        "optB": "Customers must wait here",
                        "optC": "Students should study here",
                        "answer": "A",
                    },
                ]
            },
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=2,
            has_content=True,
            content={
                "people": [
                    {"name": "Ahmed", "desc": "He wants to exercise after work and needs a place open in the evening."},
                    {"name": "Sara", "desc": "She wants to learn something creative at the weekend."},
                    {"name": "Mona", "desc": "She wants an activity where she can watch a film with friends."},
                ],
                "activities": [
                    {"id": "A", "title": "City Gym", "text": "Open until 11pm every day. Fitness classes and modern equipment."},
                    {"id": "B", "title": "Weekend Art Club", "text": "Saturday drawing and painting lessons for beginners."},
                    {"id": "C", "title": "Moonlight Cinema", "text": "New films every week with evening shows and group tickets."},
                    {"id": "D", "title": "Book Corner", "text": "A quiet place to read magazines and borrow books."},
                ],
                "answers": ["A", "B", "C"],
            },
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=3,
            has_content=True,
            content={
                "passage": "Sara moved to a new city last year. At first she felt nervous, but she joined a sports club and made new friends. Now she enjoys living there.",
                "statements": [
                    {"text": "Sara moved last year.", "answer": "T"},
                    {"text": "Sara felt confident from the first day.", "answer": "F"},
                    {"text": "Sara made friends by joining a club.", "answer": "T"},
                ],
            },
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=4,
            has_content=True,
            content={
                "title": "Learning English Online",
                "passage": "Many students learn English online. Some use videos, others use apps. Teachers often say that practising a little every day helps people improve faster. Students can also join online speaking groups to build confidence and use new vocabulary in real conversations.",
                "questions": [
                    {
                        "text": "What is the text mainly about?",
                        "optA": "Learning English online",
                        "optB": "Travelling abroad",
                        "optC": "Cooking food",
                        "optD": "Playing sports",
                        "answer": "A",
                    },
                    {
                        "text": "What helps people improve faster?",
                        "optA": "Practising every day",
                        "optB": "Studying once a month",
                        "optC": "Not using apps",
                        "optD": "Watching no videos",
                        "answer": "A",
                    },
                    {
                        "text": "Why do students join online speaking groups?",
                        "optA": "To avoid homework",
                        "optB": "To build confidence",
                        "optC": "To learn cooking",
                        "optD": "To travel abroad",
                        "answer": "A",
                    },
                ],
            },
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=5,
            has_content=True,
            content={
                "text": "I [1] to school every day. My friend [2] the bus because he lives far away.",
                "blanks": [
                    {"optA": "go", "optB": "goes", "optC": "gone", "optD": "going", "answer": "A"},
                    {"optA": "take", "optB": "takes", "optC": "took", "optD": "taking", "answer": "B"},
                ],
            },
        )

        ReadingPart.objects.create(
            exam=exam,
            part_number=6,
            has_content=True,
            content={"text": "My name is Ahmed and I live ____ Riyadh.", "answers": ["in"]},
        )

    print("Created demo exam")
    print("Exam ID:", exam.id)
    print("Title:", exam.title)
    print("Writing questions:", exam.questions.count())
    print("Speaking parts:", exam.speaking_parts.count())
    print("Reading parts:", exam.reading_parts.count())


if __name__ == "__main__":
    main()
