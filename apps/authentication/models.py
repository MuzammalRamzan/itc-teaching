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
    free_credits_claimed_at = models.DateTimeField(null=True, blank=True)
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
        return self.plan in {self.PLAN_PROMO, self.PLAN_BASIC, self.PLAN_AI} or self.ai_credits > 0

    def can_access_speaking(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_AI} and self.ai_credits > 0

    def can_access_full_exam(self):
        return self.plan in {self.PLAN_PROMO, self.PLAN_AI} and self.ai_credits > 0

    def can_use_ai_marking(self):
        return self.ai_credits > 0

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


class PricingPackageContent(models.Model):
    product_key = models.CharField(max_length=50, unique=True)
    kind = models.CharField(max_length=20, default='plan')
    is_active = models.BooleanField(default=True)
    price_override = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    credits_override = models.IntegerField(null=True, blank=True)
    title_ar = models.CharField(max_length=200, blank=True, default='')
    title_en = models.CharField(max_length=200, blank=True, default='')
    subtitle_ar = models.CharField(max_length=200, blank=True, default='')
    subtitle_en = models.CharField(max_length=200, blank=True, default='')
    hook_ar = models.TextField(blank=True, default='')
    hook_en = models.TextField(blank=True, default='')
    description_ar = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    cta_ar = models.CharField(max_length=200, blank=True, default='')
    cta_en = models.CharField(max_length=200, blank=True, default='')
    features_ar = models.JSONField(default=list, blank=True)
    features_en = models.JSONField(default=list, blank=True)
    badge_ar = models.CharField(max_length=120, blank=True, default='')
    badge_en = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_package_contents'
        ordering = ['product_key']

    def __str__(self):
        return self.product_key


class LandingPageSetting(models.Model):
    APP_ITS = 'its'
    APP_FET = 'fet'
    APP_CHOICES = [
        (APP_ITS, 'ITS'),
        (APP_FET, 'FET'),
    ]

    app_key = models.CharField(max_length=20, choices=APP_CHOICES, unique=True)
    countdown_enabled = models.BooleanField(default=False)
    countdown_target = models.DateTimeField(null=True, blank=True)
    hero_badge_ar = models.CharField(max_length=200, blank=True, default='')
    hero_badge_en = models.CharField(max_length=200, blank=True, default='')
    hero_title_ar = models.CharField(max_length=255, blank=True, default='')
    hero_title_en = models.CharField(max_length=255, blank=True, default='')
    hero_subtitle_ar = models.TextField(blank=True, default='')
    hero_subtitle_en = models.TextField(blank=True, default='')
    primary_cta_ar = models.CharField(max_length=200, blank=True, default='')
    primary_cta_en = models.CharField(max_length=200, blank=True, default='')
    secondary_cta_ar = models.CharField(max_length=200, blank=True, default='')
    secondary_cta_en = models.CharField(max_length=200, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'landing_page_settings'
        ordering = ['app_key']

    def __str__(self):
        return self.app_key


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


class CreditTransaction(models.Model):
    TYPE_DEBIT = 'debit'
    TYPE_CREDIT = 'credit'
    TYPE_CHOICES = [
        (TYPE_DEBIT, 'Debit'),
        (TYPE_CREDIT, 'Credit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_transactions')
    entry_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    delta = models.IntegerField()
    balance_after = models.IntegerField(default=0)
    description = models.CharField(max_length=255)
    source_type = models.CharField(max_length=50, blank=True, default='')
    source_id = models.CharField(max_length=100, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'credit_transactions'
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.delta >= 0 else ''
        return f'{self.user.email} · {sign}{self.delta} · {self.description}'
