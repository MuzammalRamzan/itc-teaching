from django.contrib import admin

from .models import CalendarEvent, UserBreakOptIn


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('name', 'starts_at', 'ends_at', 'recommended_minutes_per_day', 'accent', 'is_active', 'order')
    list_filter = ('is_active', 'accent')
    search_fields = ('name', 'hint', 'description')
    ordering = ('order', 'starts_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'starts_at', 'ends_at', 'is_active', 'order'),
        }),
        ('Display', {
            'fields': ('accent', 'hint', 'description'),
        }),
        ('Practice plan', {
            'fields': ('recommended_minutes_per_day',),
            'description': '0 = full rest (streak preserved if user marks "I\'ll be away"). 15 = light review. 25 = adjusted hours.',
        }),
    )


@admin.register(UserBreakOptIn)
class UserBreakOptInAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'away', 'updated_at')
    list_filter = ('away',)
    search_fields = ('user__email', 'event__name')
    readonly_fields = ('created_at', 'updated_at')
