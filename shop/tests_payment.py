"""تست‌های درگاه پرداخت زرین‌پال.

هیچ تستی به شبکه واقعی وصل نمی‌شود: هم لایه درگاه و هم فراخوانی درگاه در
ویوها mock می‌شوند تا رفتار امنیتی (ذخیره authority، تأیید مبلغ، یکتایی
تراکنش و کنترل دسترسی) مستقل از sandbox بررسی شود.
"""
import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from shop.models import Category, Order, Product
from shop.payments.base import PaymentRequestResult, PaymentVerifyResult
from shop.payments.zarinpal import ZarinpalGateway

AUTHORITY = "S" * 36


@override_settings(
    PAYMENT_GATEWAY_ENABLED=True,
    PAYMENT_GATEWAY="zarinpal",
    ZARINPAL_SANDBOX=True,
    ZARINPAL_MERCHANT_ID="11111111-1111-1111-1111-111111111111",
)
class PaymentFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="09121234567", password="Test-pass-1404")
        self.order = Order.objects.create(
            user=self.user,
            full_name="تست کاربر",
            phone="09121234567",
            province="تهران",
            city="تهران",
            address="خیابان تست، پلاک ۱",
            postal_code="1234567890",
            payment_method="online",
            subtotal=1_000_000,
            shipping_cost=0,
            total=1_000_000,
        )
        self.client.force_login(self.user)

    # ------------------------------------------------------------------ helpers
    def _start(self, authority=AUTHORITY):
        with patch("shop.services.get_gateway") as factory:
            factory.return_value.slug = "zarinpal"
            factory.return_value.request_payment.return_value = PaymentRequestResult(
                authority=authority,
                payment_url=f"https://sandbox.zarinpal.com/pg/StartPay/{authority}",
            )
            return self.client.get(reverse("shop:payment_start", args=[self.order.code]))

    def _callback(self, *, status="OK", authority=AUTHORITY, verified=True, ref="123456"):
        with patch("shop.services.get_gateway") as factory:
            factory.return_value.verify_payment.return_value = PaymentVerifyResult(
                verified=verified, reference_id=ref, code=100 if verified else -50
            )
            url = reverse("shop:payment_callback", args=[self.order.code])
            return self.client.get(f"{url}?Status={status}&Authority={authority}")

    # ------------------------------------------------------------------ tests
    def test_start_creates_transaction_and_redirects_to_gateway(self):
        response = self._start()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pg/StartPay/", response["Location"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_authority, AUTHORITY)
        self.assertEqual(self.order.payment_gateway, "zarinpal")
        self.assertFalse(self.order.is_paid)

    def test_callback_success_marks_order_paid(self):
        self._start()
        response = self._callback()
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.payment_ref_id, "123456")
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.order.status, Order.STATUS_CONFIRMED)

    def test_callback_rejects_authority_of_another_transaction(self):
        self._start(authority=AUTHORITY)
        self._callback(authority="X" * 36)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)
        self.assertEqual(self.order.payment_ref_id, "")

    def test_callback_without_authority_changes_nothing(self):
        self._start()
        with patch("shop.services.get_gateway") as factory:
            self.client.get(reverse("shop:payment_callback", args=[self.order.code]) + "?Status=OK")
            factory.assert_not_called()
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_failed_status_does_not_mark_paid(self):
        self._start()
        self._callback(status="NOK")
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_failed_verification_does_not_mark_paid(self):
        self._start()
        self._callback(verified=False)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_second_callback_is_idempotent(self):
        self._start()
        self._callback(ref="111")
        first_paid_at = Order.objects.get(pk=self.order.pk).paid_at
        self._callback(ref="999")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_ref_id, "111")
        self.assertEqual(self.order.paid_at, first_paid_at)

    def test_paid_order_does_not_start_new_transaction(self):
        self._start()
        self._callback()
        with patch("shop.services.get_gateway") as factory:
            self.client.get(reverse("shop:payment_start", args=[self.order.code]))
            factory.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_ref_id, "123456")

    def test_payment_start_of_another_user_returns_404(self):
        stranger = get_user_model().objects.create_user(username="09129999999", password="Test-pass-1404")
        self.client.force_login(stranger)
        response = self.client.get(reverse("shop:payment_start", args=[self.order.code]))
        self.assertEqual(response.status_code, 404)

    def test_online_checkout_redirects_to_payment_start(self):
        category = Category.objects.create(name="فیلتر تست", slug="filter-test")
        product = Product.objects.create(
            category=category, name="فیلتر تست", slug="filter-test-product", price=200_000, stock=5
        )
        session = self.client.session
        session["cart"] = {str(product.id): {"quantity": 1}}
        session.save()
        form_data = {
            "full_name": "تست کاربر",
            "phone": "09121234567",
            "province": "تهران",
            "city": "تهران",
            "address": "خیابان تست، پلاک ۱",
            "postal_code": "1234567890",
            "note": "",
            "shipping_method": settings.DEFAULT_SHIPPING_METHOD,
            "payment_method": "online",
        }
        with patch("shop.services.get_gateway") as factory:
            factory.return_value = object()
            response = self.client.post(reverse("shop:checkout"), form_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pay/", response["Location"])
        order = Order.objects.exclude(pk=self.order.pk).get()
        self.assertEqual(order.payment_method, "online")

    def test_non_online_order_is_redirected_without_gateway(self):
        self.order.payment_method = "cod"
        self.order.save(update_fields=["payment_method"])
        with patch("shop.services.get_gateway") as factory:
            response = self.client.get(reverse("shop:payment_start", args=[self.order.code]))
            factory.assert_not_called()
        self.assertEqual(response.status_code, 302)


@override_settings(
    PAYMENT_GATEWAY_ENABLED=True,
    ZARINPAL_SANDBOX=True,
    ZARINPAL_MERCHANT_ID="22222222-2222-2222-2222-222222222222",
)
class ZarinpalClientTests(TestCase):
    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

    def _call(self, payload, **kwargs):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return self._FakeResponse(payload)

        with patch("shop.payments.zarinpal.urllib.request.urlopen", fake_urlopen):
            result = ZarinpalGateway().request_payment(**kwargs)
        return result, captured

    def test_request_converts_toman_to_rial_and_builds_startpay_url(self):
        result, captured = self._call(
            {"data": {"code": 100, "authority": AUTHORITY}, "errors": []},
            amount_toman=50_000,
            callback_url="http://127.0.0.1:8000/orders/ABP-1/payment/callback/",
            description="سفارش تست",
            mobile="09121234567",
        )
        self.assertEqual(captured["body"]["amount"], 500_000)  # تومان → ریال
        self.assertIn("sandbox.zarinpal.com", captured["url"])
        self.assertEqual(captured["body"]["metadata"]["mobile"], "09121234567")
        self.assertEqual(result.authority, AUTHORITY)
        self.assertTrue(result.payment_url.endswith(f"/pg/StartPay/{AUTHORITY}"))

    def test_request_error_raises_payment_error(self):
        with self.assertRaisesMessage(Exception, "نپذیرفت"):
            self._call(
                {"data": [], "errors": {"code": -9, "message": "درخواست نپذیرفت"}},
                amount_toman=1_000,
                callback_url="http://x/cb/",
                description="تست",
            )

    def test_verify_accepts_already_verified_code_101(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return self._FakeResponse({"data": {"code": 101, "ref_id": 987654}, "errors": []})

        with patch("shop.payments.zarinpal.urllib.request.urlopen", fake_urlopen):
            result = ZarinpalGateway().verify_payment(authority=AUTHORITY, amount_toman=1_000)

        self.assertTrue(result.verified)
        self.assertEqual(result.reference_id, "987654")
        self.assertEqual(captured["body"]["amount"], 10_000)
