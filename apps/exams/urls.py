from django.urls import path
from . import views

urlpatterns = [
    # Exams
    path('exams/', views.exam_list, name='exam-list'),
    path('exams/<uuid:exam_id>/', views.exam_detail, name='exam-detail'),
    # Writing questions
    path('exams/<uuid:exam_id>/questions/', views.add_writing_question, name='add-question'),
    path('exams/<uuid:exam_id>/questions/<uuid:question_id>/', views.update_writing_question, name='update-question'),
    # Speaking parts
    path('exams/<uuid:exam_id>/speaking/', views.add_speaking_part, name='add-speaking'),
    path('exams/<uuid:exam_id>/speaking/<uuid:part_id>/', views.update_speaking_part, name='update-speaking'),
    # Reading parts
    path('exams/<uuid:exam_id>/reading/<int:part_number>/', views.update_reading_part, name='update-reading'),
    # FET admin import
    path('exams/fet-import/', views.import_fet_exam, name='import-fet-exam'),
    path('exams/general-writing-import/', views.import_general_writing_exam, name='import-general-writing-exam'),
]
