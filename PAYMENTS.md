# درگاه پرداخت آنلاین (زرین‌پال — sandbox)

پرداخت آنلاین فروشگاه به‌صورت **ماژولار** پیاده شده است: منطق درگاه در پکیج
`shop/payments` قرار دارد و بقیه پروژه فقط با رابط `PaymentGateway` کار می‌کند.
هیچ کلید یا شناسه‌ای داخل کد، قالب یا فایل استاتیک نوشته نشده؛ همه از
تنظیمات/متغیر محیطی خوانده می‌شوند.

## ساختار

| فایل | نقش |
|---|---|
| `shop/payments/base.py` | قرارداد مشترک `PaymentGateway` + `PaymentRequestResult` / `PaymentVerifyResult` + خطای `PaymentError` |
| `shop/payments/zarinpal.py` | کلاینت زرین‌پال API v4 (request / StartPay / verify) |
| `shop/payments/gateways.py` | انتخاب درگاه فعال بر اساس تنظیمات (`get_gateway`, `gateway_available`) |
| `shop/views.py` → `payment_start`, `payment_callback` | شروع تراکنش و تأیید سمت سرور |

مسیرها:

- `POST /orders/<code>/pay/` → نام `shop:payment_start`
- `GET /orders/<code>/payment/callback/` → نام `shop:payment_callback` (callback درگاه)

## تنظیمات (متغیر محیطی)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `PAYMENT_GATEWAY_ENABLED` | `1` | `0` یعنی روش «پرداخت آنلاین» از صفحه تسویه و سایت حذف می‌شود |
| `PAYMENT_GATEWAY` | `zarinpal` | درگاه فعال (کلید ثبت‌شده در `shop/payments/gateways.py`) |
| `ZARINPAL_MERCHANT_ID` | UUID صفر | merchant id از پنل زرین‌پال؛ در sandbox هر UUID ۳۶ کاراکتری پذیرفته می‌شود |
| `ZARINPAL_SANDBOX` | `1` | `1` → `sandbox.zarinpal.com` ، `0` → `payment.zarinpal.com` (پرداخت واقعی) |
| `ZARINPAL_TIMEOUT` | `12` | مهلت اتصال به درگاه (ثانیه) |

نمونه اجرا با sandbox:

```bash
export ZARINPAL_SANDBOX=1
export ZARINPAL_MERCHANT_ID=11111111-1111-1111-1111-111111111111
export PAYMENT_GATEWAY_ENABLED=1
python manage.py runserver 127.0.0.1:8000
```

برای پرداخت واقعی، `ZARINPAL_SANDBOX=0` و merchant id واقعی را از پنل زرین‌پال
قرار دهید (روش پیشنهادی: یک فایل محیطی خارج از مخزن یا متغیر محیطی سیستم).
هیچ‌کدام از این مقادیر نباید commit شوند.

## جریان پرداخت

1. کاربر در صفحه تسویه، «پرداخت آنلاین» را انتخاب و سفارش را ثبت می‌کند.
2. `checkout` سفارش را می‌سازد و کاربر را به `payment_start` می‌فرستد.
3. `payment_start`: مبلغ از دیتابیس، `amount = total × 10` (تبدیل تومان به ریال
   در یک نقطه در `zarinpal.py`)؛ پاسخ درگاه (`authority`) روی سفارش ذخیره و
   کاربر به صفحه بانک هدایت می‌شود.
4. بازگشت از درگاه با `?Authority=...&Status=OK|NOK` به `payment_callback`.
5. `payment_callback` فقط اگر `Authority` **دقیقاً برابر مقدار ذخیره‌شده همان
   سفارش** باشد ادامه می‌دهد، سپس با مبلغ سرور `verify` می‌زند (کد `100` یا
   `101`) و در یک تراکنش اتمیک سفارش را «پرداخت‌شده» و «تأیید‌شده» می‌کند.

## نکات امنیتی

- **callback تأییدشده:** پرداخت هرگز با پارامترهای مرورگر (Status/Authority) نهایی
  نمی‌شود؛ بدون پاسخ موفق `verify` هیچ سفارشی پرداخت‌شده ثبت نمی‌شود.
- **تطبیق تراکنش:** authority ناشناخته یا متعلق به سفارش دیگر رد می‌شود (جلوگیری
  از جعل callback برای سفارش دیگران).
- **مبلغ سمت سرور:** مبلغ verify از `order.total` خوانده می‌شود، نه از ورودی کاربر.
- **idempotent:** ارسال دوباره callback (رفرش صفحه یا retry درگاه) وضعیت را تغییر
  نمی‌دهد؛ رکورد پرداخت‌شده بازنویسی نمی‌شود و تراکنش دوم برای سفارش پرداخت‌شده
  ساخته نمی‌شود.
- **کنترل دسترسی:** شروع پرداخت فقط برای صاحب سفارش یا session دارای دسترسی
  مجاز است؛ در غیر این صورت ۴۰۴.
- **لاگ امن:** فقط کد خطا و کد سفارش لاگ می‌شود؛ merchant id و پاسخ کامل درگاه
  هرگز لاگ نمی‌شوند. خطای شبکه به پیام فارسی امن تبدیل می‌شود.
- **سفارش لغوشده** قابل پرداخت نیست؛ سفارش غیرآنلاین هم به درگاه نمی‌رود.

## تست

```bash
python manage.py test shop.tests_payment -v 2
```

آزمون‌ها بدون تماس با شبکه اجرا می‌شوند و این موارد را پوشش می‌دهند: ساخت تراکنش
و ذخیره authority، تبدیل تومان به ریال، callback موفق، authority نامعتبر،
`Status=NOK`، verify ناموفق، idempotency، جلوگیری از تراکنش دوم، ۴۰۴ برای سفارش
دیگران و پذیرش کد `101` در verify.

تست دستی sandbox:

1. یک محصول به سبد اضافه کنید و در تسویه، «پرداخت آنلاین» را بزنید.
2. در صفحه sandbox زرین‌پال، «پرداخت» را تأیید کنید (یا «انصراف» برای بررسی
   مسیر ناموفق).
3. بعد از بازگشت باید پیام «پرداخت با موفقیت انجام شد» و کد پیگیری تراکنش روی
   صفحه سفارش نمایش داده شود و وضعیت سفارش «تأیید شده» و پرداخت «پرداخت شده» باشد.
4. در پنل `/admin/` سفارش → بخش «پرداخت» همان `authority`، `ref_id` و زمان پرداخت
   را نشان می‌دهد.

## افزودن درگاه جدید

1. کلاسی بسازید که `PaymentGateway` را پیاده کند (`request_payment` و
   `verify_payment`).
2. آن را در `GATEWAYS` داخل `shop/payments/gateways.py` ثبت کنید.
3. `PAYMENT_GATEWAY` را در تنظیمات به همان slug تغییر دهید.

ویوها، قالب‌ها و فیلدهای مدل تغییری لازم ندارند.

## فیلدهای مدل سفارش

`payment_gateway`, `payment_authority` (ایندکس‌دار), `payment_ref_id`, `paid_at`
— مایگریشن `shop/0006_order_paid_at_order_payment_authority_and_more.py`.
