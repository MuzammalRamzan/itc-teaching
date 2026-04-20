from decimal import Decimal
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db import ProgrammingError, OperationalError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .credits import create_credit_transaction
from .models import LandingPageSetting, PaymentRecord, PricingPackageContent, Promotion, User
from .serializers import CreditTransactionSerializer, UserSerializer

PLAN_DETAILS = {
    User.PLAN_PROMO: {
        'key': 'promo',
        'name': 'Promo Trial',
        'price': Decimal('5.00'),
        'kind': 'plan',
        'target_plan': User.PLAN_PROMO,
        'credits': 2,
        'headline': 'Limited-time trial',
        'description': 'Full platform access with 2 AI credits.',
    },
    User.PLAN_BASIC: {
        'key': 'basic',
        'name': 'Basic Practice',
        'price': Decimal('50.00'),
        'kind': 'plan',
        'target_plan': User.PLAN_BASIC,
        'credits': 0,
        'headline': 'One-time purchase',
        'description': 'Platform access with reading practice and writing interface.',
    },
    User.PLAN_AI: {
        'key': 'ai',
        'name': 'AI Practice',
        'price': Decimal('150.00'),
        'kind': 'plan',
        'target_plan': User.PLAN_AI,
        'credits': 10,
        'headline': 'Best value',
        'description': 'Full platform access with AI marking and 10 AI credits.',
    },
}

FREE_CREDIT_DEFAULT = {
    'code': 'FREE_CREDITS',
    'included_credits': 5,
    'is_active': True,
}

CREDIT_PACKS = {
    'credits_5': {
        'key': 'credits_5',
        'name': '5 AI Credits',
        'price': Decimal('25.00'),
        'kind': 'credits',
        'credits': 5,
        'description': 'Top up your AI credits by 5.',
    },
    'credits_10': {
        'key': 'credits_10',
        'name': '10 AI Credits',
        'price': Decimal('45.00'),
        'kind': 'credits',
        'credits': 10,
        'description': 'Top up your AI credits by 10.',
    },
    'credits_25': {
        'key': 'credits_25',
        'name': '25 AI Credits',
        'price': Decimal('100.00'),
        'kind': 'credits',
        'credits': 25,
        'description': 'Top up your AI credits by 25.',
    },
}

LANDING_DEFAULTS = {
    'its': {
        'countdown_enabled': False,
        'countdown_target': None,
        'hero_badge_ar': 'تدريب مركز لاختبار القبول',
        'hero_badge_en': 'Focused test prep',
        'hero_title_ar': 'استعد لاختبار القبول بثقة ووضوح',
        'hero_title_en': 'Prepare for the entry test with confidence',
        'hero_subtitle_ar': 'تجربة تدريب حديثة تساعدك تفهم مستواك سريعاً، تركز على نقاط الضعف، وتصل لمستوى B1 بشكل عملي.',
        'hero_subtitle_en': 'A modern prep experience that helps learners understand their level quickly and improve with focus.',
        'primary_cta_ar': 'ابدأ التدريب',
        'primary_cta_en': 'Start training',
        'secondary_cta_ar': 'شاهد كيف يعمل',
        'secondary_cta_en': 'See how it works',
    },
    'fet': {
        'countdown_enabled': True,
        'countdown_target': '2026-06-14T00:00:00+00:00',
        'hero_badge_ar': 'الاستعداد لاختبار FET',
        'hero_badge_en': 'FET exam preparation',
        'hero_title_ar': 'استعد لاجتياز اختبار FET',
        'hero_title_en': 'Get ready to pass the FET exam',
        'hero_subtitle_ar': 'تدريب كتابة مركز مع عد تنازلي وإعداد واضح للاختبار.',
        'hero_subtitle_en': 'Focused writing practice with a live countdown and a clear path to exam day.',
        'primary_cta_ar': 'ابدأ التدريب',
        'primary_cta_en': 'Start practice',
        'secondary_cta_ar': 'استعرض الباقات',
        'secondary_cta_en': 'View plans',
    },
}

PACKAGE_CONTENT_DEFAULTS = {
    'free': {
        'kind': 'free',
        'title_ar': 'رصيد مجاني',
        'title_en': 'Free Credits',
        'subtitle_ar': 'هدية ترحيبية للمستخدم الجديد',
        'subtitle_en': 'Welcome bonus for new users',
        'hook_ar': 'يمكن للمستخدم المؤهل المطالبة بهذا الرصيد مرة واحدة فقط من صفحة الباقات.',
        'hook_en': 'Eligible users can claim this credit bundle once from the pricing page.',
        'description_ar': 'رصيد مجاني يستخدم في ميزات الذكاء الاصطناعي حسب الخطة المفعلة.',
        'description_en': 'Free credits that can be used with AI features based on the active plan.',
        'cta_ar': 'احصل على الرصيد المجاني',
        'cta_en': 'Claim free credits',
        'features_ar': [],
        'features_en': [],
        'badge_ar': '',
        'badge_en': '',
    },
    'promo': {
        'kind': 'plan',
        'title_ar': 'الخطة التجريبية',
        'title_en': 'Promo Trial',
        'subtitle_ar': 'Promo Trial',
        'subtitle_en': 'Promo Trial',
        'hook_ar': 'أفضل طريقة لتجربة المنصة كاملة بسعر رمزي قبل الترقية لاحقاً إلى AI Practice.',
        'hook_en': 'Best for trying the platform at a very low price before upgrading later.',
        'description_ar': 'عرض محدود للمستخدم الجديد مع رصيد AI للتجربة.',
        'description_en': 'Limited entry offer for new users with trial AI credits.',
        'cta_ar': 'ابدأ العرض التجريبي',
        'cta_en': 'Start Promo Trial',
        'features_ar': [
            'دخول كامل للمنصة',
            'القراءة + الكتابة + المحادثة + الاختبار الكامل',
            'يشمل رصيد AI للتجربة',
            'بعد انتهاء الرصيد يلزم الترقية إلى AI Practice',
        ],
        'features_en': [
            'Full platform access',
            'Reading, writing, speaking, and full exam access',
            'Includes AI credits for trial use',
            'Upgrade to AI Practice after credits finish',
        ],
        'badge_ar': 'عرض محدود',
        'badge_en': 'Limited Offer',
    },
    'basic': {
        'kind': 'plan',
        'title_ar': 'تدريب أساسي',
        'title_en': 'Basic Practice',
        'subtitle_ar': 'Basic Practice',
        'subtitle_en': 'Basic Practice',
        'hook_ar': 'خيار مناسب للطالب الذي يريد تدريب ثابت على القراءة والكتابة بدون AI marking أو محادثة.',
        'hook_en': 'For learners who want stable reading and writing practice without AI marking.',
        'description_ar': 'خطة تدريب يدوي بدون مزايا الذكاء الاصطناعي.',
        'description_en': 'Manual practice plan without AI-powered marking features.',
        'cta_ar': 'اختر التدريب الأساسي',
        'cta_en': 'Choose Basic',
        'features_ar': [
            'الوصول إلى المنصة واختبارات القراءة المصححة تلقائياً',
            'واجهة الكتابة + نموذج إجابة للمقارنة',
            'بدون AI marking',
            'بدون Speaking test وبدون شراء credits إضافية',
        ],
        'features_en': [
            'Platform access and auto-marked reading tests',
            'Writing interface with model-answer comparison',
            'No AI marking included',
            'No speaking test and no extra credit purchases',
        ],
        'badge_ar': '',
        'badge_en': '',
    },
    'ai': {
        'kind': 'plan',
        'title_ar': 'تدريب بالذكاء الاصطناعي',
        'title_en': 'AI Practice',
        'subtitle_ar': 'AI Practice',
        'subtitle_en': 'AI Practice',
        'hook_ar': 'الخطة الكاملة: كل شيء في Basic + AI marking + Speaking + إمكانية شراء credits إضافية.',
        'hook_en': 'The full plan: everything in Basic plus AI marking, speaking, and extra credit top-ups.',
        'description_ar': 'الخطة الكاملة مع رصيد AI جاهز من البداية.',
        'description_en': 'Full access plan with AI credits included from the start.',
        'cta_ar': 'فعّل AI Practice',
        'cta_en': 'Activate AI Practice',
        'features_ar': [
            'كل مزايا Basic Practice',
            'AI marking للكتابة وفق المعايير',
            'Speaking test + AI examiner + feedback',
            'يمكن شراء credits إضافية: 5 / 10 / 25',
        ],
        'features_en': [
            'Everything in Basic Practice',
            'AI writing marking aligned to rubric criteria',
            'Speaking test with AI examiner and feedback',
            'Extra credit packs available: 5 / 10 / 25',
        ],
        'badge_ar': 'الأكثر قيمة',
        'badge_en': 'Best Value',
    },
    'credits_5': {
        'kind': 'credits',
        'title_ar': '5 AI Credits',
        'title_en': '5 AI Credits',
        'subtitle_ar': 'باقة رصيد إضافي',
        'subtitle_en': 'Extra credit pack',
        'hook_ar': 'اشحن رصيدك بسرعة عند الحاجة إلى محاولات إضافية.',
        'hook_en': 'Top up quickly when you need a few more AI attempts.',
        'description_ar': 'إضافة 5 أرصدة AI للحساب.',
        'description_en': 'Adds 5 AI credits to the account.',
        'cta_ar': 'اشترِ 5 credits',
        'cta_en': 'Buy 5 credits',
        'features_ar': [],
        'features_en': [],
        'badge_ar': '',
        'badge_en': '',
    },
    'credits_10': {
        'kind': 'credits',
        'title_ar': '10 AI Credits',
        'title_en': '10 AI Credits',
        'subtitle_ar': 'باقة رصيد إضافي',
        'subtitle_en': 'Extra credit pack',
        'hook_ar': 'خيار أفضل للاستخدام المتكرر والتدريب المستمر.',
        'hook_en': 'A better-value option for regular practice and repeat attempts.',
        'description_ar': 'إضافة 10 أرصدة AI للحساب.',
        'description_en': 'Adds 10 AI credits to the account.',
        'cta_ar': 'اشترِ 10 credits',
        'cta_en': 'Buy 10 credits',
        'features_ar': [],
        'features_en': [],
        'badge_ar': '',
        'badge_en': '',
    },
    'credits_25': {
        'kind': 'credits',
        'title_ar': '25 AI Credits',
        'title_en': '25 AI Credits',
        'subtitle_ar': 'أعلى باقة رصيد',
        'subtitle_en': 'Largest credit pack',
        'hook_ar': 'أنسب باقة للمستخدم الثقيل أو للمراكز التدريبية.',
        'hook_en': 'Best suited for heavy users or intensive practice.',
        'description_ar': 'إضافة 25 رصيد AI للحساب.',
        'description_en': 'Adds 25 AI credits to the account.',
        'cta_ar': 'اشترِ 25 credits',
        'cta_en': 'Buy 25 credits',
        'features_ar': [],
        'features_en': [],
        'badge_ar': '',
        'badge_en': '',
    },
}


def get_package_content(product_key, kind='plan'):
    defaults = PACKAGE_CONTENT_DEFAULTS.get(product_key, {})
    try:
        content, _ = PricingPackageContent.objects.get_or_create(
            product_key=product_key,
            defaults={
                'kind': defaults.get('kind', kind),
                'title_ar': defaults.get('title_ar', ''),
                'title_en': defaults.get('title_en', ''),
                'subtitle_ar': defaults.get('subtitle_ar', ''),
                'subtitle_en': defaults.get('subtitle_en', ''),
                'hook_ar': defaults.get('hook_ar', ''),
                'hook_en': defaults.get('hook_en', ''),
                'description_ar': defaults.get('description_ar', ''),
                'description_en': defaults.get('description_en', ''),
                'cta_ar': defaults.get('cta_ar', ''),
                'cta_en': defaults.get('cta_en', ''),
                'features_ar': defaults.get('features_ar', []),
                'features_en': defaults.get('features_en', []),
                'badge_ar': defaults.get('badge_ar', ''),
                'badge_en': defaults.get('badge_en', ''),
            },
        )
    except (OperationalError, ProgrammingError):
        content = None
    return {
        'title': {'ar': (content.title_ar if content else '') or defaults.get('title_ar', ''), 'en': (content.title_en if content else '') or defaults.get('title_en', '')},
        'subtitle': {'ar': (content.subtitle_ar if content else '') or defaults.get('subtitle_ar', ''), 'en': (content.subtitle_en if content else '') or defaults.get('subtitle_en', '')},
        'hook': {'ar': (content.hook_ar if content else '') or defaults.get('hook_ar', ''), 'en': (content.hook_en if content else '') or defaults.get('hook_en', '')},
        'description': {'ar': (content.description_ar if content else '') or defaults.get('description_ar', ''), 'en': (content.description_en if content else '') or defaults.get('description_en', '')},
        'cta': {'ar': (content.cta_ar if content else '') or defaults.get('cta_ar', ''), 'en': (content.cta_en if content else '') or defaults.get('cta_en', '')},
        'features': {'ar': (content.features_ar if content else None) or defaults.get('features_ar', []), 'en': (content.features_en if content else None) or defaults.get('features_en', [])},
        'badge': {'ar': (content.badge_ar if content else '') or defaults.get('badge_ar', ''), 'en': (content.badge_en if content else '') or defaults.get('badge_en', '')},
    }


def get_landing_setting(app_key):
    defaults = LANDING_DEFAULTS.get(app_key, LANDING_DEFAULTS['its'])
    try:
        setting, _ = LandingPageSetting.objects.get_or_create(
            app_key=app_key,
            defaults=defaults,
        )
    except (OperationalError, ProgrammingError):
        setting = None
    countdown_target = setting.countdown_target.isoformat() if setting and setting.countdown_target else defaults.get('countdown_target')
    return {
        'app_key': app_key,
        'countdown_enabled': setting.countdown_enabled if setting else defaults.get('countdown_enabled', False),
        'countdown_target': countdown_target,
        'hero_badge': {
            'ar': (setting.hero_badge_ar if setting else '') or defaults.get('hero_badge_ar', ''),
            'en': (setting.hero_badge_en if setting else '') or defaults.get('hero_badge_en', ''),
        },
        'hero_title': {
            'ar': (setting.hero_title_ar if setting else '') or defaults.get('hero_title_ar', ''),
            'en': (setting.hero_title_en if setting else '') or defaults.get('hero_title_en', ''),
        },
        'hero_subtitle': {
            'ar': (setting.hero_subtitle_ar if setting else '') or defaults.get('hero_subtitle_ar', ''),
            'en': (setting.hero_subtitle_en if setting else '') or defaults.get('hero_subtitle_en', ''),
        },
        'primary_cta': {
            'ar': (setting.primary_cta_ar if setting else '') or defaults.get('primary_cta_ar', ''),
            'en': (setting.primary_cta_en if setting else '') or defaults.get('primary_cta_en', ''),
        },
        'secondary_cta': {
            'ar': (setting.secondary_cta_ar if setting else '') or defaults.get('secondary_cta_ar', ''),
            'en': (setting.secondary_cta_en if setting else '') or defaults.get('secondary_cta_en', ''),
        },
    }


def get_credit_pack_offer(product_key):
    item = dict(CREDIT_PACKS[product_key])
    try:
        content = PricingPackageContent.objects.filter(product_key=product_key).first()
    except (OperationalError, ProgrammingError):
        content = None

    if content:
        item['price'] = content.price_override if content.price_override is not None else item['price']
        item['credits'] = content.credits_override if content.credits_override is not None else item['credits']
        item['active'] = content.is_active
        item['source'] = 'database'
    else:
        item['active'] = True
        item['source'] = 'defaults'
    return item


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def serialize_plan_catalog(user=None):
    promo = get_plan_offer(User.PLAN_PROMO)
    basic = get_plan_offer(User.PLAN_BASIC)
    ai = get_plan_offer(User.PLAN_AI)
    free_credit_offer = get_plan_offer(User.PLAN_FREE)
    ai_price = max(ai['price'] - basic['price'], Decimal('0.00')) if user and user.plan == User.PLAN_BASIC else ai['price']
    ai_name = 'Upgrade to AI Practice' if user and user.plan == User.PLAN_BASIC else PLAN_DETAILS[User.PLAN_AI]['name']

    plans = [
        {
            'key': 'promo',
            'name': PLAN_DETAILS[User.PLAN_PROMO]['name'],
            'price': str(promo['price']),
            'kind': 'plan',
            'target_plan': User.PLAN_PROMO,
            'credits': promo['included_credits'],
            'active': promo['active'],
            'expires_at': promo['expires_at'],
            'description': PLAN_DETAILS[User.PLAN_PROMO]['description'],
            'content': get_package_content('promo', 'plan'),
        },
        {
            'key': 'basic',
            'name': PLAN_DETAILS[User.PLAN_BASIC]['name'],
            'price': str(PLAN_DETAILS[User.PLAN_BASIC]['price']),
            'price': str(basic['price']),
            'kind': 'plan',
            'target_plan': User.PLAN_BASIC,
            'credits': basic['included_credits'],
            'active': basic['active'],
            'expires_at': basic['expires_at'],
            'description': PLAN_DETAILS[User.PLAN_BASIC]['description'],
            'content': get_package_content('basic', 'plan'),
        },
        {
            'key': 'ai',
            'name': ai_name,
            'price': str(ai_price),
            'kind': 'plan',
            'target_plan': User.PLAN_AI,
            'credits': ai['included_credits'],
            'active': ai['active'],
            'expires_at': ai['expires_at'],
            'description': PLAN_DETAILS[User.PLAN_AI]['description'],
            'content': get_package_content('ai', 'plan'),
        },
    ]
    credit_packs = [
        {
            'key': item['key'],
            'name': item['name'],
            'price': str(item['price']),
            'kind': item['kind'],
            'credits': item['credits'],
            'description': item['description'],
            'active': item.get('active', True),
            'source': item.get('source', 'defaults'),
            'content': get_package_content(item['key'], 'credits'),
        }
        for item in [get_credit_pack_offer(key) for key in CREDIT_PACKS.keys()]
        if item.get('active', True)
    ]
    return {
        'plans': plans,
        'credit_packs': credit_packs,
        'credit_packs_enabled': bool(credit_packs),
        'free_credit_offer': {
            'code': free_credit_offer['code'],
            'credits': free_credit_offer['included_credits'],
            'active': free_credit_offer['active'],
            'claimed': bool(user.free_credits_claimed_at) if user else False,
            'content': get_package_content('free', 'free'),
        },
    }


def serialize_plan_offer_for_admin(plan):
    offer = get_plan_offer(plan)
    return {
        'id': str(offer['id']) if offer['id'] else None,
        'code': offer['code'],
        'plan': plan,
        'price': str(offer['price']),
        'included_credits': offer['included_credits'],
        'is_active': offer['is_active'],
        'active': offer['active'],
        'expires_at': offer['expires_at'].isoformat() if offer['expires_at'] else None,
        'source': offer['source'],
        'kind': 'free' if plan == User.PLAN_FREE else 'plan',
        'content': get_package_content('free' if plan == User.PLAN_FREE else plan, 'free' if plan == User.PLAN_FREE else 'plan'),
    }


def serialize_credit_pack_for_admin(product_key):
    item = get_credit_pack_offer(product_key)
    return {
        'id': None,
        'code': product_key.upper(),
        'plan': product_key,
        'kind': 'credits',
        'price': str(item['price']),
        'included_credits': item['credits'],
        'is_active': item.get('active', True),
        'active': item.get('active', True),
        'expires_at': None,
        'source': item.get('source', 'defaults'),
        'content': get_package_content(product_key, 'credits'),
    }


def get_plan_offer(plan):
    if plan == User.PLAN_FREE:
        offer = Promotion.objects.filter(plan=plan).order_by('-created_at').first()
        if offer:
            return {
                'plan': plan,
                'code': offer.code,
                'active': offer.is_active and offer.included_credits > 0,
                'is_active': offer.is_active,
                'price': Decimal('0.00'),
                'included_credits': offer.included_credits,
                'expires_at': None,
                'source': 'database',
                'id': offer.id,
            }
        return {
            'plan': plan,
            'code': FREE_CREDIT_DEFAULT['code'],
            'active': FREE_CREDIT_DEFAULT['is_active'] and FREE_CREDIT_DEFAULT['included_credits'] > 0,
            'is_active': FREE_CREDIT_DEFAULT['is_active'],
            'price': Decimal('0.00'),
            'included_credits': FREE_CREDIT_DEFAULT['included_credits'],
            'expires_at': None,
            'source': 'defaults',
            'id': None,
        }

    offer = Promotion.objects.filter(plan=plan).order_by('-created_at').first()
    now = timezone.now()

    if offer:
        active = offer.is_active
        if offer.expires_at and offer.expires_at <= now:
            active = False
        return {
            'plan': plan,
            'code': offer.code,
            'active': active,
            'is_active': offer.is_active,
            'price': Decimal(offer.price),
            'included_credits': offer.included_credits,
            'expires_at': offer.expires_at,
            'source': 'database',
            'id': offer.id,
        }

    if plan == User.PLAN_PROMO:
        ends_at = parse_datetime(settings.PROMO_TRIAL_ENDS_AT) if settings.PROMO_TRIAL_ENDS_AT else None
        active = settings.PROMO_TRIAL_ACTIVE and (not ends_at or now < ends_at)
        return {
            'plan': plan,
            'code': 'PROMO_TRIAL',
            'active': active,
            'is_active': settings.PROMO_TRIAL_ACTIVE,
            'price': Decimal('5.00'),
            'included_credits': PLAN_DETAILS[plan]['credits'],
            'expires_at': ends_at,
            'source': 'settings',
            'id': None,
        }

    item = PLAN_DETAILS[plan]
    return {
        'plan': plan,
        'code': f'{plan.upper()}_PLAN',
        'active': True,
        'is_active': True,
        'price': Decimal(item['price']),
        'included_credits': item['credits'],
        'expires_at': None,
        'source': 'defaults',
        'id': None,
    }


def get_checkout_item_for_user(user, product_key):
    promo = get_plan_offer(User.PLAN_PROMO)
    basic = get_plan_offer(User.PLAN_BASIC)
    ai = get_plan_offer(User.PLAN_AI)

    if product_key == 'promo':
        if not promo['active']:
            return None, 'Promo Trial is no longer available.'
        if user.plan != User.PLAN_FREE:
            return None, 'Promo Trial is only available to new users on the free plan.'
        item = dict(PLAN_DETAILS[User.PLAN_PROMO])
        item['price'] = promo['price']
        item['credits'] = promo['included_credits']
        return item, None

    if product_key == 'basic':
        if not basic['active']:
            return None, 'Basic Practice is not available right now.'
        if user.plan == User.PLAN_AI:
            return None, 'You already have AI Practice.'
        if user.plan == User.PLAN_BASIC:
            return None, 'You already have Basic Practice.'
        if user.plan == User.PLAN_PROMO:
            return None, 'Promo users should upgrade directly to AI Practice.'
        item = dict(PLAN_DETAILS[User.PLAN_BASIC])
        item['price'] = basic['price']
        item['credits'] = basic['included_credits']
        return item, None

    if product_key == 'ai':
        if not ai['active']:
            return None, 'AI Practice is not available right now.'
        if user.plan == User.PLAN_AI:
            return None, 'You already have AI Practice.'
        item = dict(PLAN_DETAILS[User.PLAN_AI])
        item['price'] = ai['price']
        item['credits'] = ai['included_credits']
        if user.plan == User.PLAN_BASIC:
            item['price'] = max(ai['price'] - basic['price'], Decimal('0.00'))
            item['name'] = 'Upgrade to AI Practice'
            item['description'] = f"Upgrade from Basic Practice to AI Practice with {ai['included_credits']} AI credits."
        return item, None

    if product_key in CREDIT_PACKS:
        if not user.can_buy_credits():
            return None, 'Only AI Practice users can buy more credits.'
        return dict(CREDIT_PACKS[product_key]), None

    return None, 'Unknown product.'


def sanitize_checkout_return_path(value):
    if not isinstance(value, str):
        return '/platform'
    value = value.strip()
    if not value.startswith('/') or value.startswith('//'):
        return '/platform'
    return value or '/platform'


def sanitize_checkout_frontend_base_url(value):
    if not isinstance(value, str):
        return settings.CHECKOUT_FRONTEND_BASE_URL
    value = value.strip().rstrip('/')
    if not value:
        return settings.CHECKOUT_FRONTEND_BASE_URL
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.path not in {'', '/'}:
        return settings.CHECKOUT_FRONTEND_BASE_URL
    return f'{parsed.scheme}://{parsed.netloc}'


def apply_payment_record(record, session):
    if record.applied_at:
        return

    user = record.user
    now = timezone.now()

    if record.kind == PaymentRecord.KIND_PLAN:
        user.plan = record.target_plan
        user.plan_purchased_at = now
        user.ai_credits += record.credits_amount
        description = f'{record.credits_amount} credits added from {record.target_plan.upper()} plan purchase.'
    elif record.kind == PaymentRecord.KIND_CREDITS:
        user.ai_credits += record.credits_amount
        description = f'{record.credits_amount} credits added from credit pack purchase.'
    else:
        description = f'{record.credits_amount} credits added.'

    user.save(update_fields=['plan', 'plan_purchased_at', 'ai_credits'])
    if record.credits_amount:
        create_credit_transaction(
            user=user,
            delta=record.credits_amount,
            description=description,
            source_type='payment_record',
            source_id=record.id,
            metadata={
                'payment_record_id': str(record.id),
                'kind': record.kind,
                'target_plan': record.target_plan,
                'product_key': record.metadata.get('product_key', ''),
            },
        )

    record.status = PaymentRecord.STATUS_COMPLETED
    record.applied_at = now
    record.stripe_payment_intent = session.get('payment_intent') or ''
    record.metadata = {**record.metadata, 'stripe_status': session.get('payment_status', '')}
    record.save(update_fields=['status', 'applied_at', 'stripe_payment_intent', 'metadata', 'updated_at'])


@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    credential = request.data.get('credential')
    if not credential:
        return Response({'error': 'credential is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        idinfo = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as e:
        return Response({'error': f'Invalid token: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    google_id = idinfo['sub']
    email = idinfo['email']
    name = idinfo.get('name', email.split('@')[0])
    picture = idinfo.get('picture', '')

    user, created = User.objects.get_or_create(
        google_id=google_id,
        defaults={'email': email, 'name': name, 'picture': picture, 'last_login': timezone.now()}
    )

    if not created:
        user.name = name
        user.picture = picture
        user.last_login = timezone.now()
        user.save(update_fields=['name', 'picture', 'last_login'])

    tokens = get_tokens_for_user(user)
    return Response({
        **tokens,
        'user': UserSerializer(user).data,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def credit_history(request):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get('page_size', 20))
    except (TypeError, ValueError):
        page_size = 20
    page_size = max(10, min(page_size, 100))

    queryset = request.user.credit_transactions.all()
    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = queryset[start:end]

    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total_count + page_size - 1) // page_size),
        'has_previous': page > 1,
        'has_next': end < total_count,
        'results': CreditTransactionSerializer(items, many=True).data,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def pricing_catalog(request):
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    payload = serialize_plan_catalog(user)
    payload['current_plan'] = user.plan if user else User.PLAN_FREE
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def landing_config(request):
    app_key = (request.query_params.get('app') or 'its').strip().lower()
    if app_key not in {'its', 'fet'}:
        app_key = 'its'
    return Response(get_landing_setting(app_key))


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def promotion_admin_detail(request):
    if not request.user.is_admin:
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({
            'packages': [
                serialize_plan_offer_for_admin(User.PLAN_FREE),
                serialize_plan_offer_for_admin(User.PLAN_PROMO),
                serialize_plan_offer_for_admin(User.PLAN_BASIC),
                serialize_plan_offer_for_admin(User.PLAN_AI),
                serialize_credit_pack_for_admin('credits_5'),
                serialize_credit_pack_for_admin('credits_10'),
                serialize_credit_pack_for_admin('credits_25'),
            ]
        })

    expires_at_value = request.data.get('expires_at')
    expires_at = None
    if expires_at_value:
        expires_at = parse_datetime(expires_at_value)
        if expires_at is None:
            return Response({'error': 'Invalid expiry datetime.'}, status=status.HTTP_400_BAD_REQUEST)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())

    plan = request.data.get('plan') or User.PLAN_PROMO
    kind = request.data.get('kind') or ('credits' if str(plan).startswith('credits_') else 'plan')
    code = request.data.get('code') or (
        'FREE_CREDITS' if plan == User.PLAN_FREE else f'{plan.upper()}_PLAN' if plan != User.PLAN_PROMO else 'PROMO_TRIAL'
    )

    content_save_available = True
    try:
        content, _ = PricingPackageContent.objects.get_or_create(
            product_key='free' if plan == User.PLAN_FREE else plan,
            defaults={'kind': kind},
        )
        content.kind = kind
        content.title_ar = request.data.get('title_ar', content.title_ar)
        content.title_en = request.data.get('title_en', content.title_en)
        content.is_active = bool(request.data.get('is_active', content.is_active))
        if 'price' in request.data and str(request.data.get('price', '')).strip() != '':
            content.price_override = Decimal(str(request.data.get('price')))
        if 'included_credits' in request.data and str(request.data.get('included_credits', '')).strip() != '':
            content.credits_override = int(request.data.get('included_credits'))
        content.subtitle_ar = request.data.get('subtitle_ar', content.subtitle_ar)
        content.subtitle_en = request.data.get('subtitle_en', content.subtitle_en)
        content.hook_ar = request.data.get('hook_ar', content.hook_ar)
        content.hook_en = request.data.get('hook_en', content.hook_en)
        content.description_ar = request.data.get('description_ar', content.description_ar)
        content.description_en = request.data.get('description_en', content.description_en)
        content.cta_ar = request.data.get('cta_ar', content.cta_ar)
        content.cta_en = request.data.get('cta_en', content.cta_en)
        content.badge_ar = request.data.get('badge_ar', content.badge_ar)
        content.badge_en = request.data.get('badge_en', content.badge_en)
        if 'features_ar' in request.data:
            content.features_ar = request.data.get('features_ar') or []
        if 'features_en' in request.data:
            content.features_en = request.data.get('features_en') or []
        content.save()
    except (OperationalError, ProgrammingError):
        content_save_available = False

    if kind == 'credits':
        return Response({
            'message': 'Package updated successfully.' if content_save_available else 'Package pricing saved. Run the latest migration to enable editable package text.',
            'package': serialize_credit_pack_for_admin(plan),
        })

    with transaction.atomic():
        promo, _ = Promotion.objects.select_for_update().get_or_create(
            plan=plan,
            defaults={
                'code': code,
                'plan': plan,
                'price': Decimal('0.00') if plan == User.PLAN_FREE else request.data.get('price') or Decimal('5.00'),
                'included_credits': int(request.data.get('included_credits', 0) or 0),
                'is_active': bool(request.data.get('is_active', True)),
                'expires_at': expires_at,
            },
        )
        promo.code = code
        promo.plan = plan
        promo.price = Decimal('0.00') if plan == User.PLAN_FREE else request.data.get('price') or promo.price
        promo.included_credits = int(request.data.get('included_credits', promo.included_credits) or 0)
        promo.is_active = bool(request.data.get('is_active', True))
        promo.expires_at = expires_at if plan == User.PLAN_PROMO else None
        promo.save(update_fields=['code', 'plan', 'price', 'included_credits', 'is_active', 'expires_at'])

    return Response({
        'message': 'Package updated successfully.' if content_save_available else 'Package pricing saved. Run the latest migration to enable editable package text.',
        'package': serialize_plan_offer_for_admin(plan),
    })


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def landing_admin_detail(request):
    if not request.user.is_admin:
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({
            'settings': [
                get_landing_setting('its'),
                get_landing_setting('fet'),
            ]
        })

    app_key = (request.data.get('app_key') or 'its').strip().lower()
    if app_key not in {'its', 'fet'}:
        return Response({'error': 'Invalid app key.'}, status=status.HTTP_400_BAD_REQUEST)

    countdown_target = None
    countdown_target_value = request.data.get('countdown_target')
    if countdown_target_value:
        countdown_target = parse_datetime(countdown_target_value)
        if countdown_target is None:
            return Response({'error': 'Invalid countdown datetime.'}, status=status.HTTP_400_BAD_REQUEST)
        if timezone.is_naive(countdown_target):
            countdown_target = timezone.make_aware(countdown_target, timezone.get_current_timezone())

    defaults = LANDING_DEFAULTS[app_key]
    setting, _ = LandingPageSetting.objects.get_or_create(app_key=app_key, defaults=defaults)
    setting.countdown_enabled = bool(request.data.get('countdown_enabled', setting.countdown_enabled))
    setting.countdown_target = countdown_target if countdown_target_value else None
    setting.hero_badge_ar = request.data.get('hero_badge_ar', setting.hero_badge_ar)
    setting.hero_badge_en = request.data.get('hero_badge_en', setting.hero_badge_en)
    setting.hero_title_ar = request.data.get('hero_title_ar', setting.hero_title_ar)
    setting.hero_title_en = request.data.get('hero_title_en', setting.hero_title_en)
    setting.hero_subtitle_ar = request.data.get('hero_subtitle_ar', setting.hero_subtitle_ar)
    setting.hero_subtitle_en = request.data.get('hero_subtitle_en', setting.hero_subtitle_en)
    setting.primary_cta_ar = request.data.get('primary_cta_ar', setting.primary_cta_ar)
    setting.primary_cta_en = request.data.get('primary_cta_en', setting.primary_cta_en)
    setting.secondary_cta_ar = request.data.get('secondary_cta_ar', setting.secondary_cta_ar)
    setting.secondary_cta_en = request.data.get('secondary_cta_en', setting.secondary_cta_en)
    setting.save()
    return Response({
        'message': 'Landing settings updated successfully.',
        'setting': get_landing_setting(app_key),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def claim_free_credits(request):
    offer = get_plan_offer(User.PLAN_FREE)
    if not offer['active'] or offer['included_credits'] <= 0:
        return Response({'error': 'Free credits are not available right now.'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if user.free_credits_claimed_at:
            return Response({'error': 'You have already claimed your free credits.'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        user.ai_credits += offer['included_credits']
        user.free_credits_claimed_at = now
        user.save(update_fields=['ai_credits', 'free_credits_claimed_at'])
        create_credit_transaction(
            user=user,
            delta=offer['included_credits'],
            description=f'{offer["included_credits"]} free credits claimed.',
            source_type='free_claim',
            metadata={'product_key': 'free_credits_claim'},
        )

        PaymentRecord.objects.create(
            user=user,
            kind=PaymentRecord.KIND_CREDITS,
            credits_amount=offer['included_credits'],
            amount_sar=Decimal('0.00'),
            status=PaymentRecord.STATUS_COMPLETED,
            applied_at=now,
            metadata={'product_key': 'free_credits_claim', 'mode': 'free_claim'},
        )

    return Response({
        'message': f"You claimed {offer['included_credits']} free credits successfully.",
        'user': UserSerializer(user).data,
        'credits': offer['included_credits'],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    item, error = get_checkout_item_for_user(request.user, request.data.get('product_key', '').strip())
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

    return_to = sanitize_checkout_return_path(request.data.get('return_to', '/platform'))
    frontend_base_url = sanitize_checkout_frontend_base_url(request.data.get('frontend_base_url', ''))
    encoded_return_to = quote(return_to, safe='')

    if not settings.STRIPE_SECRET_KEY:
        with transaction.atomic():
            record = PaymentRecord.objects.create(
                user=request.user,
                kind=item['kind'],
                target_plan=item.get('target_plan', ''),
                credits_amount=item.get('credits', 0),
                amount_sar=item['price'],
                status=PaymentRecord.STATUS_COMPLETED,
                metadata={'product_key': item['key'], 'mode': 'mock'},
            )
            apply_payment_record(
                record,
                {
                    'id': f'mock_{record.id}',
                    'payment_intent': '',
                    'payment_status': 'paid',
                },
            )
        return Response({
            'mode': 'mock',
            'status': 'completed',
            'record_id': str(record.id),
            'message': 'Mock checkout completed locally.',
            'return_to': return_to,
        }, status=status.HTTP_201_CREATED)

    try:
        import stripe
    except ImportError:
        return Response({'error': 'Stripe package is not installed on the backend.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    with transaction.atomic():
        record = PaymentRecord.objects.create(
            user=request.user,
            kind=item['kind'],
            target_plan=item.get('target_plan', ''),
            credits_amount=item.get('credits', 0),
            amount_sar=item['price'],
            metadata={'product_key': item['key']},
        )

        session = stripe.checkout.Session.create(
            mode='payment',
            customer_email=request.user.email,
            success_url=f"{frontend_base_url}/pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&return_to={encoded_return_to}",
            cancel_url=f"{frontend_base_url}/pricing?checkout=cancelled&return_to={encoded_return_to}",
            metadata={
                'record_id': str(record.id),
                'user_id': str(request.user.id),
                'kind': item['kind'],
                'target_plan': item.get('target_plan', ''),
                'credits': str(item.get('credits', 0)),
                'product_key': item['key'],
            },
            line_items=[
                {
                    'price_data': {
                        'currency': 'sar',
                        'unit_amount': int(item['price'] * 100),
                        'product_data': {
                            'name': item['name'],
                            'description': item['description'],
                        },
                    },
                    'quantity': 1,
                }
            ],
        )

        record.stripe_session_id = session.id
        record.save(update_fields=['stripe_session_id', 'updated_at'])

    return Response({
        'mode': 'stripe',
        'checkout_url': session.url,
        'record_id': str(record.id),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_checkout_session(request):
    session_id = (request.data.get('session_id') or '').strip()
    if not session_id:
        return Response({'error': 'session_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not settings.STRIPE_SECRET_KEY:
        return Response({'error': 'Stripe is not configured yet.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        import stripe
    except ImportError:
        return Response({'error': 'Stripe package is not installed on the backend.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        return Response({'error': f'Unable to retrieve checkout session: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

    metadata = session.get('metadata') or {}
    record_id = metadata.get('record_id')
    if not record_id:
        return Response({'error': 'No payment record found for this session.'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        try:
            record = PaymentRecord.objects.select_for_update().select_related('user').get(id=record_id, user=request.user)
        except PaymentRecord.DoesNotExist:
            return Response({'error': 'Payment record not found.'}, status=status.HTTP_404_NOT_FOUND)

        if session.get('payment_status') == 'paid':
            record.stripe_session_id = session.get('id')
            apply_payment_record(record, session)
            request.user.refresh_from_db()
            return Response({
                'status': 'completed',
                'user': UserSerializer(request.user).data,
            })

        return Response({
            'status': 'pending',
            'payment_status': session.get('payment_status', ''),
        }, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        return Response({'error': 'Stripe webhook is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        import stripe
    except ImportError:
        return Response({'error': 'Stripe package is not installed on the backend.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    payload = request.body
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        return HttpResponse(status=400)

    event_type = event['type']
    session = event['data']['object']
    metadata = session.get('metadata') or {}
    record_id = metadata.get('record_id')

    if not record_id:
        return HttpResponse(status=200)

    with transaction.atomic():
        try:
            record = PaymentRecord.objects.select_for_update().select_related('user').get(id=record_id)
        except PaymentRecord.DoesNotExist:
            return HttpResponse(status=200)

        if event_type == 'checkout.session.completed':
            record.stripe_session_id = session.get('id')
            apply_payment_record(record, session)
        elif event_type == 'checkout.session.expired':
            record.status = PaymentRecord.STATUS_EXPIRED
            record.save(update_fields=['status', 'updated_at'])
        elif event_type == 'checkout.session.async_payment_failed':
            record.status = PaymentRecord.STATUS_FAILED
            record.save(update_fields=['status', 'updated_at'])

    return HttpResponse(status=200)
