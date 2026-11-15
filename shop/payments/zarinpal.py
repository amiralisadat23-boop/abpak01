"""کلاینت درگاه زرین‌پال (API نسخه ۴ — REST).

مستندات: مبلغ در API به **ریال** است و قیمت‌های سایت به تومان ذخیره می‌شوند،
پس تبدیل در همین لایه و فقط در یک نقطه انجام می‌شود.

امنیت:
- کلید درگاه (merchant_id) فقط از تنظیمات/متغیر محیطی خوانده می‌شود.
- در لاگ‌ها هرگز merchant_id یا پاسخ کامل تراکنش ثبت نمی‌شود.
- هر خطای شبکه/HTTP به `PaymentError` با پیام امن تبدیل می‌شود.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from .base import PaymentError, PaymentGateway, PaymentRequestResult, PaymentVerifyResult

logger = logging.getLogger(__name__)

REQUEST_PATH = "/pg/v4/payment/request.json"
VERIFY_PATH = "/pg/v4/payment/verify.json"
START_PAY_PATH = "/pg/StartPay/"

SUCCESS_CODES = (100,)  # 100: موفق، 101: قبلاً تأیید شده
VERIFY_CODES = (100, 101)


def _error_message(response: dict) -> str:
    """پیام خطای امن از پاسخ درگاه (ساختار errors ممکن است dict یا list باشد)."""
    errors = response.get("errors")
    if isinstance(errors, dict):
        return str(errors.get("message") or "").strip()
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get("message") or "").strip()
    return ""


class ZarinpalGateway(PaymentGateway):
    slug = "zarinpal"
    title = "زرین‌پال"

    def __init__(self, merchant_id=None, sandbox=None, timeout=None):
        self.merchant_id = (
            merchant_id if merchant_id is not None else settings.ZARINPAL_MERCHANT_ID
        ).strip()
        self.sandbox = settings.ZARINPAL_SANDBOX if sandbox is None else bool(sandbox)
        self.timeout = int(timeout or settings.ZARINPAL_TIMEOUT)
        self.base_url = (
            "https://sandbox.zarinpal.com" if self.sandbox else "https://payment.zarinpal.com"
        )

    # ------------------------------------------------------------------ utils
    @property
    def is_configured(self) -> bool:
        return bool(self.merchant_id)

    def _amount_rial(self, amount_toman: int) -> int:
        try:
            amount_toman = int(amount_toman)
        except (TypeError, ValueError):
            raise PaymentError("مبلغ سفارش معتبر نیست.")
        if amount_toman <= 0:
            raise PaymentError("مبلغ سفارش معتبر نیست.")
        return amount_toman * 10

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("zarinpal http error %s on %s", exc.code, path)
            try:
                return json.loads(body)
            except ValueError:
                raise PaymentError("درگاه پرداخت خطا برگرداند. لطفاً بعداً تلاش کنید.")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("zarinpal connection error on %s: %s", path, exc.__class__.__name__)
            raise PaymentError("ارتباط با درگاه پرداخت برقرار نشد. لطفاً دوباره تلاش کنید.")

        try:
            return json.loads(body)
        except ValueError:
            logger.warning("zarinpal invalid json on %s", path)
            raise PaymentError("پاسخ درگاه پرداخت قابل خواندن نبود.")

    # ------------------------------------------------------------------ api
    def request_payment(
        self,
        *,
        amount_toman: int,
        callback_url: str,
        description: str,
        mobile: str = "",
        email: str = "",
    ) -> PaymentRequestResult:
        if not self.is_configured:
            raise PaymentError("درگاه پرداخت هنوز تنظیم نشده است.")

        payload = {
            "merchant_id": self.merchant_id,
            "amount": self._amount_rial(amount_toman),
            "callback_url": callback_url,
            "description": description,
        }
        metadata = {key: value for key, value in {"mobile": mobile, "email": email}.items() if value}
        if metadata:
            payload["metadata"] = metadata

        response = self._post(REQUEST_PATH, payload)
        data = response.get("data") or {}
        code = int(data.get("code") or 0)
        authority = str(data.get("authority") or "").strip()

        if code not in SUCCESS_CODES or not authority:
            logger.warning("zarinpal request failed (code=%s)", code)
            message = _error_message(response) or "درگاه پرداخت درخواست را نپذیرفت."
            raise PaymentError(message)

        return PaymentRequestResult(
            authority=authority,
            payment_url=f"{self.base_url}{START_PAY_PATH}{authority}",
        )

    def verify_payment(self, *, authority: str, amount_toman: int) -> PaymentVerifyResult:
        if not self.is_configured:
            raise PaymentError("درگاه پرداخت هنوز تنظیم نشده است.")
        if not authority:
            raise PaymentError("شناسه تراکنش نامعتبر است.")

        payload = {
            "merchant_id": self.merchant_id,
            "amount": self._amount_rial(amount_toman),
            "authority": authority,
        }
        response = self._post(VERIFY_PATH, payload)
        data = response.get("data") or {}
        code = int(data.get("code") or 0)
        reference_id = str(data.get("ref_id") or "").strip()

        if code in VERIFY_CODES and reference_id:
            return PaymentVerifyResult(
                verified=True,
                reference_id=reference_id,
                code=code,
                message=str(data.get("message") or ""),
            )

        logger.warning("zarinpal verify failed (code=%s)", code)
        return PaymentVerifyResult(
            verified=False,
            code=code,
            message=_error_message(response) or "تأیید پرداخت ناموفق بود.",
        )
