from rest_framework import serializers
from .models import CreditTransaction, User


class UserSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField()
    # `effective_plan` is what the app should show + gate on. Equals
    # `plan` when active, falls back to 'free' when plan_expires_at has
    # passed. The raw `plan` is also exposed so the pricing screen can
    # tell "promo expired" from "never on promo".
    effective_plan = serializers.ReadOnlyField()
    plan_expired = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'picture', 'is_admin', 'created_at',
            'plan', 'effective_plan', 'plan_purchased_at', 'plan_expires_at',
            'plan_expired', 'ai_credits', 'free_credits_claimed_at', 'capabilities',
        ]
        read_only_fields = fields

    def get_capabilities(self, obj):
        return obj.capability_map()

    def get_plan_expired(self, obj):
        return obj.is_plan_expired()


class CreditTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTransaction
        fields = [
            'id',
            'entry_type',
            'delta',
            'balance_after',
            'description',
            'source_type',
            'source_id',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields
