"""انتخاب درگاه فعال بر اساس تنظیمات پروژه."""
from django.conf import settings

from .base import PaymentError
from .zarinpal import ZarinpalGateway

GATEWAYS = {
    "zarinpal": ZarinpalGateway,
}


def gateway_available() -> bool:
    """آیا درگاه آنلاین برای نمایش/استفاده فعال است؟"""
    if not getattr(settings, "PAYMENT_GATEWAY_ENABLED", False):
        return False
    if settings.PAYMENT_GATEWAY not in GATEWAYS:
        return False
    # sandbox می‌تواند بدون کلید واقعی کار کند، ولی در حالت واقعی کلید لازم است.
    return settings.ZARINPAL_SANDBOX or bool(settings.ZARINPAL_MERCHANT_ID)


def get_gateway(slug: str | None = None):
    """نمونه درگاه فعال را برمی‌گرداند یا None اگر درگاه خاموش باشد."""
    if not gateway_available():
        return None
    slug = slug or settings.PAYMENT_GATEWAY
    factory = GATEWAYS.get(slug)
    if factory is None:
        raise PaymentError("درگاه پرداخت پشتیبانی نمی‌شود.")
    return factory()
