"""قرارداد مشترک درگاه‌های پرداخت و انواع نتیجه."""
from dataclasses import dataclass


class PaymentError(Exception):
    """خطای قابل نمایش به کاربر در جریان پرداخت.

    پیام این خطا مستقیماً در پیام‌های سایت نشان داده می‌شود، پس نباید شامل
    اطلاعات حساس (کلید درگاه، پاسخ خام سرور و ...) باشد.
    """


@dataclass(frozen=True)
class PaymentRequestResult:
    """نتیجه ساخت تراکنش در درگاه."""

    authority: str
    payment_url: str


@dataclass(frozen=True)
class PaymentVerifyResult:
    """نتیجه تأیید (verify) تراکنش."""

    verified: bool
    reference_id: str = ""
    code: int = 0
    message: str = ""


class PaymentGateway:
    """رابط پایه درگاه.

    پیاده‌سازی‌ها فقط باید این دو متد را داشته باشند؛ همه منطق امنیتی
    (اعتبارسنجی مبلغ، ذخیره نتیجه، یکتایی تراکنش) در ویوهای سایت انجام می‌شود.
    """

    slug = "base"
    title = "درگاه پرداخت"

    def request_payment(
        self,
        *,
        amount_toman: int,
        callback_url: str,
        description: str,
        mobile: str = "",
        email: str = "",
    ) -> PaymentRequestResult:
        raise NotImplementedError

    def verify_payment(self, *, authority: str, amount_toman: int) -> PaymentVerifyResult:
        raise NotImplementedError
