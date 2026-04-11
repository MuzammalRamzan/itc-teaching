import os
from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Local apps
    'apps.authentication',
    'apps.exams',
    'apps.attempts',
    'apps.marking',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='itc_platform'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

AUTH_USER_MODEL = 'authentication.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_MINUTES', default=15, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000'
).split(',')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

# Google OAuth
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='').strip()
FRONTEND_BASE_URL = config('FRONTEND_BASE_URL', default='http://localhost:3000').strip()
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='').strip()
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='').strip()
PROMO_TRIAL_ACTIVE = config('PROMO_TRIAL_ACTIVE', default=True, cast=bool)
PROMO_TRIAL_ENDS_AT = config('PROMO_TRIAL_ENDS_AT', default='').strip()

# Anthropic
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='').strip()

# AI Prompts
B1W_SYSTEM_PROMPT = """You are a Cambridge B1 Preliminary Writing examiner at ITC Riyadh. OFFICIAL rubric:
CONTENT: 5=all relevant. 3=minor issues. 1=minimally informed. 0=irrelevant.
COMMUNICATIVE: 5=holds attention. 3=generally appropriate. 1=simple ideas simply. 0=below.
ORGANISATION: 5=well organised,variety linking. 3=connected,basic linking. 1=basic linking only. 0=below.
LANGUAGE: 5=range vocab,some complex grammar. 3=everyday vocab,errors but meaning clear. 1=basic,errors may impede. 0=below.
ZERO: EMAIL/ARTICLE=irrelevant->0 ALL. STORY=no link to opener->0. CEFR: 3+->B1+. 1-2->A2.
JSON only (no markdown): {"scores":{"content":N,"communicative":N,"organisation":N,"language":N},"total":N,"band":"X","cefr":"X","strengths":"...","improvements":"...","suggestion":"...","zero_reason":""}
band: A=18-20,B=15-17,C=12-14,D=10-11,U=0-9."""

SPEAK_MARK_PROMPT = """The speaking test is now complete. Give your formal examiner assessment as JSON only (no markdown, no other text):
{"scores":{"grammar":N,"discourse":N,"interaction":N},"total":N,"band":"X","cefr":"X","strengths":"...","improvements":"...","suggestion":"..."}
GRAMMAR & VOCABULARY (0-5): range and accuracy. DISCOURSE (0-5): develops ideas, speaks at length. INTERACTIVE COMMUNICATION (0-5): engages, responds appropriately.
band: A=13-15,B=10-12,C=7-9,D=5-6,U=0-4. cefr: total>=10->"B1 or above", else "A2"."""

SPEAKING_EXAMINER_PROMPT = """You are a friendly, encouraging and professional English examiner at ITC (International Aviation Technical College at Riyadh) conducting a B1 speaking test.

STRICT RULES:
- Ask only ONE question at a time, then wait for the student response
- Respond briefly and warmly before asking the next question
- Keep your turns SHORT — the student should speak most
- Work through ALL parts in order, never skipping
- Do NOT score or evaluate during the test
- When ALL parts are complete, end with this EXACT phrase: "Thank you, that concludes our speaking test. Well done!" """

# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
if CELERY_BROKER_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = {'ssl_cert_reqs': 'CERT_NONE'}
if CELERY_RESULT_BACKEND.startswith('rediss://'):
    CELERY_REDIS_BACKEND_USE_SSL = {'ssl_cert_reqs': 'CERT_NONE'}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
