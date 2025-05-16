from azbankgateways.urls import az_bank_gateways_urls
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentGatewayConfigViewSet,
    PaymentViewSet,
    RefundViewSet,
    TransactionViewSet,
    go_to_gateway,
    payment_callback,
)

router = DefaultRouter()
router.register(r"gateways", PaymentGatewayConfigViewSet, basename="gateway")
router.register(r"payments", PaymentViewSet, basename="payment")
router.register(r"transactions", TransactionViewSet, basename="transaction")
router.register(r"refunds", RefundViewSet, basename="refund")

urlpatterns = [
    path("api/", include(router.urls)),
    path("go-to-gateway/", go_to_gateway, name="go-to-bank-gateway"),
    path("callback/", payment_callback, name="callback"),
    path("bankgateways/", az_bank_gateways_urls()),  # azbankgateways URLs
]
