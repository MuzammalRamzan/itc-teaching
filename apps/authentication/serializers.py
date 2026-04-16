from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'picture', 'is_admin', 'created_at',
            'plan', 'plan_purchased_at', 'ai_credits', 'free_credits_claimed_at', 'capabilities',
        ]
        read_only_fields = fields

    def get_capabilities(self, obj):
        return obj.capability_map()
