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
    path('calendar/events/', views.calendar_events, name='calendar-events'),
    path('calendar/events/<uuid:event_id>/opt-in/', views.calendar_event_opt_in, name='calendar-event-opt-in'),
    path('calendar/admin/events/', views.calendar_events_admin, name='calendar-events-admin'),
    path('calendar/admin/events/<uuid:event_id>/', views.calendar_event_admin_detail, name='calendar-event-admin-detail'),
]
