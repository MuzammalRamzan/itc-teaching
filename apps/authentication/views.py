from decimal import Decimal
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db import transaction
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

from .models import PaymentRecord, Promotion, User
from .serializers import UserSerializer

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
        }
        for item in CREDIT_PACKS.values()
    ]
    return {
        'plans': plans,
        'credit_packs': credit_packs,
        'free_credit_offer': {
            'code': free_credit_offer['code'],
            'credits': free_credit_offer['included_credits'],
            'active': free_credit_offer['active'],
            'claimed': bool(user.free_credits_claimed_at) if user else False,
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
    elif record.kind == PaymentRecord.KIND_CREDITS:
        user.ai_credits += record.credits_amount

    user.save(update_fields=['plan', 'plan_purchased_at', 'ai_credits'])

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
            settings.GOOGLE_CLIENT_ID
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
@permission_classes([AllowAny])
def pricing_catalog(request):
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    payload = serialize_plan_catalog(user)
    payload['current_plan'] = user.plan if user else User.PLAN_FREE
    return Response(payload)


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
    code = request.data.get('code') or (
        'FREE_CREDITS' if plan == User.PLAN_FREE else f'{plan.upper()}_PLAN' if plan != User.PLAN_PROMO else 'PROMO_TRIAL'
    )

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
        'message': 'Package updated successfully.',
        'package': serialize_plan_offer_for_admin(plan),
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
