# بهینه‌سازی عملکرد فروشگاه آب پاک

این سند خلاصهٔ کارهایی است که برای کاهش زمان بارگذاری، سبک‌سازی تصاویر،
کاهش کوئری‌های دیتابیس و رعایت Core Web Vitals انجام شده است. منطق بک‌اند
و رفتار صفحات تغییر نکرده؛ فقط لایه‌های کش، ایندکس، تصاویر و مارک‌آپ سبک‌تر
شده‌اند.

## ۱) خلاصهٔ تغییرات

| # | تغییر | فایل |
|---|-------|------|
| ۱ | حذف `annotate(order_count=...)` بلااستفاده از فهرست محصولات (حذف یک JOIN + GROUP BY در هر درخواست) | `shop/views.py` |
| ۲ | کش نسخه‌دار دسته‌های ناوبری به‌جای کوئری `COUNT` در هر صفحه | `shop/context_processors.py`، `shop/cache_utils.py` |
| ۳ | بی‌اعتبارسازی خودکار کش با سیگنال هنگام ذخیره/حذف محصول، دسته و برند | `shop/signals.py` |
| ۴ | تنظیم صریح `CACHES` (قابل تغییر با متغیر محیطی، مثلاً Redis) | `config/settings.py` |
| ۵ | ذخیره‌سازی استاتیک پروداکشن با `CompressedManifestStaticFilesStorage` (gzip + نام هش‌دار + کش یک‌ساله) | `config/settings.py` |
| ۶ | ۸ ایندکس دیتابیس برای مسیرهای پرتکرار (فهرست محصولات، دسته، سفارش‌ها، پیام‌ها) | `shop/models.py` + مایگریشن `0005` |
| ۷ | نسخه‌های ریسپانسیو تصاویر (۴۰۰px و ۸۰۰px) + `srcset/sizes` در کارت محصول | `shop/management/commands/optimize_images.py`، `templates/partials/product_card.html` |
| ۸ | دستور اندازه‌گیری تکرارپذیر عملکرد | `shop/management/commands/perf_report.py` |

## ۲) نتایج اندازه‌گیری (قبل / بعد)

اندازه‌گیری با `python manage.py perf_report --runs 3` روی همین پروژه و
دیتابیس انجام شده (حالت `DEBUG=1`، یعنی بدترین حالت؛ در پروداکشن با
`WhiteNoise` و `DEBUG=0` بهتر می‌شود).

| صفحه | کوئری قبل | کوئری بعد | زمان قبل | زمان بعد | حجم HTML بعد |
|---|---|---|---|---|---|
| صفحه اصلی | ۱۲ | **۷** | ۱۶۶ms (کولد) | **۲۵ms** | ۱۰۳KB (‏gzip: ۱۷.۷KB) |
| فهرست محصولات | ۸ | **۷** | ۲۹.۶ms | **۲۷.۳ms** | ۶۸KB |
| فهرست صفحه ۲ | ۸ | **۷** | ۲۱.۹ms | **۲۵.۱ms** | ۷۰KB |
| صفحه محصول | ۶ | **۵** | ۱۸.۱ms | **۱۶ms** | ۵۳KB |
| جستجو | ۸ | **۷** | ۲۶.۴ms | **۲۹.۳ms** | ۷۱KB |
| سبد خرید | ۴ | **۳** | ۱۶.۹ms | **۱۴.۴ms** | ۴۴KB |
| سوالات متداول | ۲ | **۱** | ۷.۷ms | **۷.۵ms** | ۴۸KB |
| تماس با ما | ۲ | **۱** | ۱۸.۹ms | **۶.۳ms** | ۴۱KB |

> زمان صفحه اصلی در «قبل» شامل کامپایل اولیهٔ تمپلیت‌ها بود؛ عدد «بعد»
> میانگین سه اجرای گرم است. معیار قابل اتکاتر، ستون کوئری است: صفحه اصلی
> از ۱۲ به ۷ و صفحات ثابت از ۲ به ۱ کوئری رسیدند.

## ۳) تصاویر

- تصاویر محصول از قبل WebP و حداکثر ۱۲۰۰px بودند (کل `media` = ۱.۱MB).
- نسخه‌های ۴۰۰px و ۸۰۰px ساخته شد: **۵۴ فایل جدید** (۴۰۳KB) که فقط در
  صورت نیاز دانلود می‌شوند.
- صفحه اصلی روی موبایل: مجموع تصاویر کارت‌ها از **۱۳۹KB به ۳۰KB** رسید
  (**۷۹٪ کاهش**)؛ نمونه: ۲۵.۹KB → ۳.۷KB.
- هر `<img>` ابعاد `width/height` دارد (CLS = 0) و `loading="lazy"` +
  `decoding="async"` روی کارت‌ها فعال است.

## ۴) Core Web Vitals

اندازه‌گیری با Chromium روی `http://127.0.0.1:8000/`:

| متریک | قبل | بعد |
|---|---|---|
| FCP | ۴۷۶ms | ۲۹۶ms (گرم) / ۸۰۶ms (کولد) |
| LCP | ۱۱۲۶ms | **۲۹۶ms** برابر FCP (گرم) / ۸۰۶ms (کولد) |
| CLS | ۰ | **۰** |
| INP | ۴۸ms | ۴۸ms (بدون تغییر) |

علت اصلی LCP بد قبلی، انیمیشن `opacity` روی هیرو بود که رندر متن را عقب
می‌انداخت (در تب پس‌زمینه عملاً متوقف می‌شد). حالا ورود هیرو فقط با
`transform` انجام می‌شود و محتوای بالای صفحه هرگز با JS پنهان نمی‌شود.

## ۵) کش

- `CACHES` با `LocMemCache` پیش‌فرض و `TIMEOUT=900`.
- کلیدهای مشتق‌شده با «نسخه کاتالوگ» کار می‌کنند؛ هر `save/delete` روی
  `Product`، `Category` یا `Brand` نسخه را بالا می‌برد و کش فوراً تازه
  می‌شود (بدون تأخیر ۱۵ دقیقه‌ای و بدون داده کهنه).
- `SiteSettings` از قبل کش ۶۰۰ ثانیه‌ای داشت و بعد از ذخیره در پنل پاک
  می‌شود.
- سبد خرید و شمارندهٔ آن کش نمی‌شوند (وابسته به session کاربر) تا داده
  کاربران قاطی نشود.

برای استقرار چند-پروسه‌ای (gunicorn/uwsgi) کش محلی هر پروسه جداست؛ با
متغیرهای محیطی و بدون تغییر کد به Redis سوییچ کنید:

```bash
pip install django-redis
export CACHE_BACKEND=django_redis.cache.RedisCache
export CACHE_LOCATION=redis://127.0.0.1:6379/1
```

## ۶) ایندکس‌های دیتابیس

مایگریشن `shop/0005_contactmessage_shop_msg_read_created_and_more.py`:

| جدول | ایندکس |
|---|---|
| product | `(is_active, -created_at)`, `(category, is_active)`, `(is_featured, is_active)` |
| productimage | `(product, is_primary)` |
| order | `(user, -created_at)`, `(status, -created_at)`, `(phone)` |
| contactmessage | `(is_read, -created_at)` |

## ۷) دستورهای تکرارپذیر

```bash
# گزارش کوئری/زمان/حجم صفحات
python manage.py perf_report --runs 3

# ساخت نسخه‌های ۴۰۰/۸۰۰ تصاویر (فقط فایل‌های جدید ساخته می‌شوند)
python manage.py optimize_images --variants

# تبدیل و سبک‌سازی تصاویر بزرگ تازه‌آپلودشده
python manage.py optimize_images --max-size 1200 --quality 82
```

## ۸) چک‌لیست استقرار

```bash
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="..."
export DJANGO_ALLOWED_HOSTS="abpak.ir,www.abpak.ir"
python manage.py collectstatic --noinput   # لازم برای CompressedManifestStaticFilesStorage
python manage.py migrate
gunicorn config.wsgi:application --workers 3 --bind 0.0.0.0:8000
```

- `WhiteNoise` خودش gzip/brotli و هدر کش یک‌ساله می‌دهد.
- `WHITENOISE_MANIFEST_STRICT=False` گذاشته شده تا اگر `collectstatic` فراموش
  شد، سایت ۵۰۰ ندهد.
- فایل‌های `media/` را در پروداکشن با nginx یا CDN سرو کنید (Django نباید
  تصاویر را در پروداکشن سرو کند).

## ۹) کارهای بعدی پیشنهادی (خارج از این تغییر)

- فشرده‌سازی Brotli در لبه (Cloudflare/nginx) برای HTML/CSS/JS.
- ساب‌ست کردن فونت وزیرمتن (۵ وزن × ~۵۱KB) به گلیف‌های فارسی.
- سرویس تصویر با تبدیل خودکار (Cloudflare Images یا thumbnail در آپلود) به‌جای
  سه نسخهٔ ثابت.
- افزودن کادر جستجو با پیشنهاد زنده (API آن آماده است ولی مارک‌آپ ندارد).
