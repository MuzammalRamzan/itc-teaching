from django.contrib import admin

from .models import PaymentRecord, Promotion, User


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('code', 'plan', 'price', 'included_credits', 'is_active', 'expires_at', 'created_at')
    list_filter = ('plan', 'is_active')
    search_fields = ('code',)
    list_editable = ('price', 'included_credits', 'is_active', 'expires_at')
    ordering = ('-created_at',)

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_staff)


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kind', 'target_plan', 'credits_amount', 'amount_sar', 'status', 'created_at')
    list_filter = ('kind', 'status', 'target_plan')
    search_fields = ('user__email', 'stripe_session_id', 'stripe_payment_intent')
    readonly_fields = ('id', 'created_at', 'updated_at', 'applied_at')
    ordering = ('-created_at',)

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_staff)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'plan', 'ai_credits', 'is_admin', 'last_login')
    list_filter = ('plan', 'is_admin')
    search_fields = ('email', 'name')
    list_editable = ('plan', 'ai_credits', 'is_admin')
    ordering = ('email',)

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_staff)
