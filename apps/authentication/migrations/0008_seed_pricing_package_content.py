from django.db import migrations


PLAN_SEEDS = [
    {
        "plan": "free",
        "code": "FREE_CREDITS",
        "price": "0.00",
        "included_credits": 5,
        "is_active": True,
        "expires_at": None,
    },
    {
        "plan": "promo",
        "code": "PROMO_TRIAL",
        "price": "5.00",
        "included_credits": 2,
        "is_active": True,
        "expires_at": None,
    },
    {
        "plan": "basic",
        "code": "BASIC_PLAN",
        "price": "50.00",
        "included_credits": 0,
        "is_active": True,
        "expires_at": None,
    },
    {
        "plan": "ai",
        "code": "AI_PLAN",
        "price": "150.00",
        "included_credits": 10,
        "is_active": True,
        "expires_at": None,
    },
]


CONTENT_SEEDS = {
    "free": {
        "kind": "free",
        "title_ar": "رصيد مجاني",
        "title_en": "Free Credits",
        "subtitle_ar": "هدية ترحيبية للمستخدم الجديد",
        "subtitle_en": "Welcome bonus for new users",
        "hook_ar": "يمكن للمستخدم المؤهل المطالبة بهذا الرصيد مرة واحدة فقط من صفحة الباقات.",
        "hook_en": "Eligible users can claim this credit bundle once from the pricing page.",
        "description_ar": "رصيد مجاني يستخدم في ميزات الذكاء الاصطناعي حسب الخطة المفعلة.",
        "description_en": "Free credits that can be used with AI features based on the active plan.",
        "cta_ar": "احصل على الرصيد المجاني",
        "cta_en": "Claim free credits",
        "features_ar": [],
        "features_en": [],
        "badge_ar": "",
        "badge_en": "",
    },
    "promo": {
        "kind": "plan",
        "title_ar": "الخطة التجريبية",
        "title_en": "Promo Trial",
        "subtitle_ar": "Promo Trial",
        "subtitle_en": "Promo Trial",
        "hook_ar": "أفضل طريقة لتجربة المنصة كاملة بسعر رمزي قبل الترقية لاحقاً إلى AI Practice.",
        "hook_en": "Best for trying the platform at a very low price before upgrading later.",
        "description_ar": "عرض محدود للمستخدم الجديد مع رصيد AI للتجربة.",
        "description_en": "Limited entry offer for new users with trial AI credits.",
        "cta_ar": "ابدأ العرض التجريبي",
        "cta_en": "Start Promo Trial",
        "features_ar": [
            "دخول كامل للمنصة",
            "القراءة + الكتابة + المحادثة + الاختبار الكامل",
            "يشمل رصيد AI للتجربة",
            "بعد انتهاء الرصيد يلزم الترقية إلى AI Practice",
        ],
        "features_en": [
            "Full platform access",
            "Reading, writing, speaking, and full exam access",
            "Includes AI credits for trial use",
            "Upgrade to AI Practice after credits finish",
        ],
        "badge_ar": "عرض محدود",
        "badge_en": "Limited Offer",
    },
    "basic": {
        "kind": "plan",
        "title_ar": "تدريب أساسي",
        "title_en": "Basic Practice",
        "subtitle_ar": "Basic Practice",
        "subtitle_en": "Basic Practice",
        "hook_ar": "خيار مناسب للطالب الذي يريد تدريب ثابت على القراءة والكتابة بدون AI marking أو محادثة.",
        "hook_en": "For learners who want stable reading and writing practice without AI marking.",
        "description_ar": "خطة تدريب يدوي بدون مزايا الذكاء الاصطناعي.",
        "description_en": "Manual practice plan without AI-powered marking features.",
        "cta_ar": "اختر التدريب الأساسي",
        "cta_en": "Choose Basic",
        "features_ar": [
            "الوصول إلى المنصة واختبارات القراءة المصححة تلقائياً",
            "واجهة الكتابة + نموذج إجابة للمقارنة",
            "بدون AI marking",
            "بدون Speaking test وبدون شراء credits إضافية",
        ],
        "features_en": [
            "Platform access and auto-marked reading tests",
            "Writing interface with model-answer comparison",
            "No AI marking included",
            "No speaking test and no extra credit purchases",
        ],
        "badge_ar": "",
        "badge_en": "",
    },
    "ai": {
        "kind": "plan",
        "title_ar": "تدريب بالذكاء الاصطناعي",
        "title_en": "AI Practice",
        "subtitle_ar": "AI Practice",
        "subtitle_en": "AI Practice",
        "hook_ar": "الخطة الكاملة: كل شيء في Basic + AI marking + Speaking + إمكانية شراء credits إضافية.",
        "hook_en": "The full plan: everything in Basic plus AI marking, speaking, and extra credit top-ups.",
        "description_ar": "الخطة الكاملة مع رصيد AI جاهز من البداية.",
        "description_en": "Full access plan with AI credits included from the start.",
        "cta_ar": "فعّل AI Practice",
        "cta_en": "Activate AI Practice",
        "features_ar": [
            "كل مزايا Basic Practice",
            "AI marking للكتابة وفق المعايير",
            "Speaking test + AI examiner + feedback",
            "يمكن شراء credits إضافية: 5 / 10 / 25",
        ],
        "features_en": [
            "Everything in Basic Practice",
            "AI writing marking aligned to rubric criteria",
            "Speaking test with AI examiner and feedback",
            "Extra credit packs available: 5 / 10 / 25",
        ],
        "badge_ar": "الأكثر قيمة",
        "badge_en": "Best Value",
    },
    "credits_5": {
        "kind": "credits",
        "title_ar": "5 AI Credits",
        "title_en": "5 AI Credits",
        "subtitle_ar": "باقة رصيد إضافي",
        "subtitle_en": "Extra credit pack",
        "hook_ar": "اشحن رصيدك بسرعة عند الحاجة إلى محاولات إضافية.",
        "hook_en": "Top up quickly when you need a few more AI attempts.",
        "description_ar": "إضافة 5 أرصدة AI للحساب.",
        "description_en": "Adds 5 AI credits to the account.",
        "cta_ar": "اشترِ 5 credits",
        "cta_en": "Buy 5 credits",
        "features_ar": [],
        "features_en": [],
        "badge_ar": "",
        "badge_en": "",
    },
    "credits_10": {
        "kind": "credits",
        "title_ar": "10 AI Credits",
        "title_en": "10 AI Credits",
        "subtitle_ar": "باقة رصيد إضافي",
        "subtitle_en": "Extra credit pack",
        "hook_ar": "خيار أفضل للاستخدام المتكرر والتدريب المستمر.",
        "hook_en": "A better-value option for regular practice and repeat attempts.",
        "description_ar": "إضافة 10 أرصدة AI للحساب.",
        "description_en": "Adds 10 AI credits to the account.",
        "cta_ar": "اشترِ 10 credits",
        "cta_en": "Buy 10 credits",
        "features_ar": [],
        "features_en": [],
        "badge_ar": "",
        "badge_en": "",
    },
    "credits_25": {
        "kind": "credits",
        "title_ar": "25 AI Credits",
        "title_en": "25 AI Credits",
        "subtitle_ar": "أعلى باقة رصيد",
        "subtitle_en": "Largest credit pack",
        "hook_ar": "أنسب باقة للمستخدم الثقيل أو للمراكز التدريبية.",
        "hook_en": "Best suited for heavy users or intensive practice.",
        "description_ar": "إضافة 25 رصيد AI للحساب.",
        "description_en": "Adds 25 AI credits to the account.",
        "cta_ar": "اشترِ 25 credits",
        "cta_en": "Buy 25 credits",
        "features_ar": [],
        "features_en": [],
        "badge_ar": "",
        "badge_en": "",
    },
}


def seed_pricing(apps, schema_editor):
    Promotion = apps.get_model("authentication", "Promotion")
    PricingPackageContent = apps.get_model("authentication", "PricingPackageContent")

    for item in PLAN_SEEDS:
        Promotion.objects.update_or_create(
            plan=item["plan"],
            defaults={
                "code": item["code"],
                "price": item["price"],
                "included_credits": item["included_credits"],
                "is_active": item["is_active"],
                "expires_at": item["expires_at"],
            },
        )

    for product_key, defaults in CONTENT_SEEDS.items():
        PricingPackageContent.objects.update_or_create(
            product_key=product_key,
            defaults=defaults,
        )


def unseed_pricing(apps, schema_editor):
    Promotion = apps.get_model("authentication", "Promotion")
    PricingPackageContent = apps.get_model("authentication", "PricingPackageContent")
    Promotion.objects.filter(plan__in=["free", "promo", "basic", "ai"]).delete()
    PricingPackageContent.objects.filter(product_key__in=list(CONTENT_SEEDS.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0007_pricingpackagecontent"),
    ]

    operations = [
        migrations.RunPython(seed_pricing, unseed_pricing),
    ]
