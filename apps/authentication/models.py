import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, name, google_id, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, google_id=google_id, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, google_id='admin', **extra_fields):
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, name, google_id, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    PLAN_FREE = 'free'
    PLAN_PROMO = 'promo'
    PLAN_BASIC = 'basic'
    PLAN_AI = 'ai'
    PLAN_CHOICES = [
        (PLAN_FREE, 'Free'),
        (PLAN_PROMO, 'Promo Trial'),
        (PLAN_BASIC, 'Basic Practice'),
        (PLAN_AI, 'AI Practice'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    picture = models.URLField(blank=True, default='')
    google_id = models.CharField(max_length=200, unique=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_FREE)
    plan_purchased_at = models.DateTimeField(null=True, blank=True)
    ai_credits = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    objects = UserManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f'{self.name} <{self.email}>'

    def can_access_reading(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_BASIC, self.PLAN_AI}

    def can_access_writing(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_BASIC, self.PLAN_AI}

    def can_access_speaking(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_AI} and self.ai_credits > 0

    def can_access_full_exam(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_AI} and self.ai_credits > 0

    def can_use_ai_marking(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_AI} and self.ai_credits > 0

    def can_buy_credits(self):
        return self.plan == self.PLAN_AI

    def capability_map(self):
        return {
            'reading': self.can_access_reading(),
            'writing': self.can_access_writing(),
            'speaking': self.can_access_speaking(),
            'full_exam': self.can_access_full_exam(),
            'ai_marking': self.can_use_ai_marking(),
            'buy_credits': self.can_buy_credits(),
        }


class Promotion(models.Model):
    code = models.CharField(max_length=100, unique=True)
    plan = models.CharField(max_length=20, choices=User.PLAN_CHOICES, default=User.PLAN_PROMO)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    included_credits = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'promotions'
        ordering = ['-created_at']

    def __str__(self):
        return self.code


class PaymentRecord(models.Model):
    KIND_PLAN = 'plan'
    KIND_CREDITS = 'credits'
    KIND_CHOICES = [
        (KIND_PLAN, 'Plan'),
        (KIND_CREDITS, 'Credits'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_records')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    target_plan = models.CharField(max_length=20, choices=User.PLAN_CHOICES, blank=True, default='')
    credits_amount = models.IntegerField(default=0)
    amount_sar = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=10, default='sar')
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    metadata = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_records'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} · {self.kind} · {self.amount_sar} SAR'
