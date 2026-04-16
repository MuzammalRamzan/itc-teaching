from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('google/', views.google_login, name='google-login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', views.me, name='me'),
    path('pricing/', views.pricing_catalog, name='pricing-catalog'),
    path('promotion-admin/', views.promotion_admin_detail, name='promotion-admin'),
    path('free-credits/claim/', views.claim_free_credits, name='claim-free-credits'),
    path('checkout/', views.create_checkout_session, name='create-checkout-session'),
    path('checkout/confirm/', views.confirm_checkout_session, name='confirm-checkout-session'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe-webhook'),
]
