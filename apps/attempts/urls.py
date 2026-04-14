from django.urls import path
from . import views

urlpatterns = [
    path('attempts/', views.create_attempt, name='create-attempt'),
    path('attempts/<uuid:attempt_id>/', views.attempt_detail, name='attempt-detail'),
    path('attempts/<uuid:attempt_id>/writing/', views.submit_writing, name='submit-writing'),
    path('attempts/<uuid:attempt_id>/speaking/', views.submit_speaking, name='submit-speaking'),
    path('attempts/<uuid:attempt_id>/speaking/chat/', views.speaking_chat, name='speaking-chat'),
    path('attempts/<uuid:attempt_id>/reading/', views.submit_reading, name='submit-reading'),
    path('attempts/<uuid:attempt_id>/complete/', views.complete_attempt, name='complete-attempt'),
    path('users/me/attempts/', views.my_attempts, name='my-attempts'),
    path('users/me/fet-attempts/', views.my_fet_attempts, name='my-fet-attempts'),
]
