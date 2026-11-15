"""لایه پرداخت ماژولار فروشگاه.

هر درگاه جدید (زرین‌پال، آیدی‌پی، ...) فقط باید قرارداد `PaymentGateway` را
پیاده کند و در `gateways.get_gateway` ثبت شود؛ ویوها و قالب‌ها تغییری لازم
ندارند.
"""
from .base import PaymentError, PaymentGateway, PaymentRequestResult, PaymentVerifyResult
from .gateways import get_gateway

__all__ = [
    "PaymentError",
    "PaymentGateway",
    "PaymentRequestResult",
    "PaymentVerifyResult",
    "get_gateway",
]
