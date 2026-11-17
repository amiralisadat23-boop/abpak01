"""
تنظیمات پروژه فروشگاه اینترنتی آب پاک (ABPAK)
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    """خواندن متغیرها از فایل .env ریشه پروژه (بدون وابستگی اضافه).

    متغیرهایی که از قبل در محیط سیستم تعیین شده‌اند اولویت دارند و بازنویسی نمی‌شوند،
    بنابراین تنظیمات پروداکشن همیشه بر محتوای فایل .env مقدم است.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-abpak-dev-only-key-change-me-in-production-9f2c7a",
)

DEBUG = env_bool("DJANGO_DEBUG", default=True)

# فهرست دامنه‌های مجاز؛ در پروداکشن باید صریحاً در .env تنظیم شود.
# 127.0.0.1 برای healthcheck داخلی کانتینر و اتصال مستقیم روی لوکال لازم است.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "shop.middleware.StaticCacheMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context_processors.store",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# پایگاه داده
# اتصال از متغیر DATABASE_URL خوانده می‌شود (مثلاً postgres://user:pass@host:5432/db).
# اگر متغیر تنظیم نشده باشد، برای توسعه سریع از SQLite استفاده می‌شود؛ در
# docker-compose مقدار آن همیشه به سرویس postgres اشاره می‌کند.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# فشرده‌سازی و کش فایل‌های استاتیک (در development از finders استفاده می‌شود)
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30
# در پروداکشن اگر collectstatic اجرا نشده باشد، به‌جای خطای 500 فایل اصلی سرو می‌شود.
WHITENOISE_MANIFEST_STRICT = False

# ---------------------------------------------------------------------------
# کش
# پیش‌فرض LocMemCache است (به ازای هر پروسه). برای استقرار چند-پروسه‌ای
# می‌توانید بدون تغییر کد، بک‌اند را با متغیرهای محیطی عوض کنید (مثلا Redis).
# ---------------------------------------------------------------------------
# آدرس Redis مشترک (صف سلری، بک‌اند نتیجه و کش).
# در docker-compose به redis://redis:6379/... و در اجرای مستقیم روی هاست به
# پورت پابلیش‌شده آن اشاره می‌کند.
REDIS_URL = os.environ.get("REDIS_URL", "").strip()

CACHES = {
    "default": {
        # با وجود REDIS_URL، کش بین همه پروسه‌ها/کانتینرها مشترک می‌شود؛
        # در غیر این صورت LocMemCache محلی استفاده می‌شود.
        "BACKEND": os.environ.get(
            "CACHE_BACKEND",
            "django_redis.cache.RedisCache"
            if REDIS_URL
            else "django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": os.environ.get("CACHE_LOCATION", REDIS_URL or "abpak-local"),
        "TIMEOUT": int(os.environ.get("CACHE_TIMEOUT", "900")),
    }
}

# ---------------------------------------------------------------------------
# ذخیره‌سازی فایل‌های استاتیک
# در پروداکشن WhiteNoise فایل‌ها را gzip/brotli می‌کند و نام هش‌دار می‌دهد
# (کش یک‌ساله در مرورگر). نیازمند `manage.py collectstatic` است.
# ---------------------------------------------------------------------------
if DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "shop:login"
LOGIN_REDIRECT_URL = "shop:account"
LOGOUT_REDIRECT_URL = "shop:home"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_SAVE_EVERY_REQUEST = False

# دامنه‌هایی که فرم‌های POST از آن‌ها پذیرفته می‌شود (پیش‌نمایش ابری + دامنه اصلی)
CSRF_TRUSTED_ORIGINS = [
    "https://*.style.dev",
    "https://abpak.ir",
    "https://www.abpak.ir",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
] + env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

CSRF_COOKIE_HTTPONLY = False

# ---------------------------------------------------------------------------
# تنظیمات اختصاصی فروشگاه
# ---------------------------------------------------------------------------
SITE_NAME = "آب پاک"
SITE_NAME_EN = "ABPAK"
SITE_TAGLINE = "تجهیزات تصفیه آب خانگی و صنعتی"
SITE_PHONE = "۰۲۱-۹۱۰۰۴۵۶۷"
SITE_PHONE_RAW = "02191004567"
SITE_MOBILE = "۰۹۱۲۳۴۵۶۷۸۹"
SITE_EMAIL = "info@abpak.ir"
SITE_ADDRESS = "تهران، خیابان ولیعصر، بالاتر از میدان ونک، برج آبان، طبقه ۵، واحد ۱۲"
SITE_WORKING_HOURS = "شنبه تا پنجشنبه، ۹ صبح تا ۹ شب"
SITE_TAPSI_SHOP = "https://tapsi.shop/store/1439158740070203392/HIT759060"
SITE_INSTAGRAM = "https://instagram.com/"
SITE_TELEGRAM = "https://t.me/"
SITE_WHATSAPP = "https://wa.me/989123456789"

SHIPPING_METHODS = {
    "post": {
        "label": "پست پیشتاز",
        "description": "ارسال به تمام نقاط کشور، ۲ تا ۴ روز کاری",
        "cost": 89_000,
    },
    "peyk": {
        "label": "پیک اختصاصی تهران",
        "description": "تحویل در همان روز برای سفارش‌های ثبت‌شده تا ساعت ۱۲",
        "cost": 149_000,
    },
    "freight": {
        "label": "باربری (کالای حجیم)",
        "description": "مناسب دستگاه‌های صنعتی و مخازن بزرگ، هزینه بر اساس مقصد",
        "cost": 250_000,
    },
}
FREE_SHIPPING_THRESHOLD = 5_000_000
DEFAULT_SHIPPING_METHOD = "post"

# ---------------------------------------------------------------------------
# پرداخت آنلاین (ماژول shop/payments)
# پیش‌فرض روی حالت sandbox زرین‌پال است تا بدون پول واقعی قابل تست باشد:
#   ZARINPAL_SANDBOX=1  → آدرس‌های sandbox.zarinpal.com
#   ZARINPAL_MERCHANT_ID → در سایت تست، هر UUID دلخواه ۳۶ کاراکتری قبول است
# برای پرداخت واقعی: ZARINPAL_SANDBOX=0 و merchant id واقعی از پنل زرین‌پال.
# هیچ کلیدی در کد یا قالب نوشته نمی‌شود؛ فقط از متغیر محیطی خوانده می‌شود.
# ---------------------------------------------------------------------------
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "zarinpal")
PAYMENT_GATEWAY_ENABLED = os.environ.get("PAYMENT_GATEWAY_ENABLED", "1") == "1"

ZARINPAL_MERCHANT_ID = os.environ.get(
    "ZARINPAL_MERCHANT_ID", "00000000-0000-0000-0000-000000000000"
).strip()
ZARINPAL_SANDBOX = os.environ.get("ZARINPAL_SANDBOX", "1") == "1"
ZARINPAL_TIMEOUT = int(os.environ.get("ZARINPAL_TIMEOUT", "12"))

PAYMENT_METHODS = {}
if PAYMENT_GATEWAY_ENABLED:
    PAYMENT_METHODS["online"] = {
        "label": "پرداخت آنلاین (درگاه زرین‌پال)",
        "description": "انتقال امن به درگاه بانکی؛ در حالت آزمایشی مبلغی از حساب شما کم نمی‌شود",
    }
PAYMENT_METHODS.update(
    {
        "cod": {
            "label": "پرداخت در محل (هنگام تحویل)",
            "description": "پرداخت نقدی یا کارت‌خوان هنگام تحویل کالا",
        },
        "transfer": {
            "label": "کارت به کارت / انتقال بانکی",
            "description": "شماره کارت پس از ثبت سفارش توسط پشتیبانی برای شما ارسال می‌شود",
        },
    }
)

PRODUCTS_PER_PAGE = 12

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# ---------------------------------------------------------------------------
# کارهای پس‌زمینه (Celery + Redis)
# در docker-compose سرویس‌های web/worker/beat همین ایمیج را اجرا می‌کنند و
# آدرس بروکر با متغیرهای محیطی روی سرویس redis تنظیم می‌شود.
# سلری فقط با اجرای worker لازم است؛ خود سایت به آن وابسته نیست.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", REDIS_URL or "redis://127.0.0.1:6379/0"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 10 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 9 * 60
# با بالا آمدن ورکر، تا در دسترس بودن بروکر تلاش مجدد می‌کند (رفتار جدید سلری 6)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_BEAT_SCHEDULE = {
    # هر شب نشست‌های منقضی‌شده پاک می‌شوند (سرویس beat)
    "clear-expired-sessions": {
        "task": "shop.tasks.clear_expired_sessions",
        "schedule": 60 * 60 * 24,
    },
}

# ---------------------------------------------------------------------------
# امنیت و آمادگی استقرار
# مقادیری که سمت مرورگر اثر دارند با متغیر محیطی قابل تغییرند تا با/بدون HTTPS
# قابل استفاده باشند؛ مقادیر پیش‌فرض امن و سازگار با پروکسی (nginx) است.
# ---------------------------------------------------------------------------
# nginx هدر X-Forwarded-Proto را می‌فرستد؛ بدون آن جنگو درخواست را http می‌بیند.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
# سایت در iframe جاسازی نمی‌شود؛ DENY جلوی clickjacking را کامل می‌گیرد.
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# کوکی‌های امن فقط روی HTTPS کار می‌کنند؛ در پروداکشن به‌صورت پیش‌فرض روشن‌اند.
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)

# ریدایرکت HTTPS و HSTS پیش‌فرض خاموش است تا استقرار بدون گواهی تولید را
# قفل نکند؛ بعد از تنظیم TLS مقدارها را روشن کنید (HSTS: 31536000).
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=SECURE_HSTS_SECONDS > 0
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", default=False)

# سرو فایل‌های آپلودی (/media) توسط جنگو فقط وقتی پروکسی/سرور وب جداگانه‌ای
# برای media تنظیم نشده باشد. در ترافیک بالا آن را به nginx/CDN بسپارید.
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", default=False)

# ---------------------------------------------------------------------------
# کنترل‌های سخت‌گیرانه پروداکشن: پیکربندی ناقص باید در استارتاپ خطا بدهد،
# نه اینکه بی‌صدا با کلید ناامن یا SQLite بالا بیاید.
# ---------------------------------------------------------------------------
if not DEBUG:
    if SECRET_KEY.startswith("django-insecure") or len(SECRET_KEY) < 40:
        raise ImproperlyConfigured(
            "در حالت پروداکشن DJANGO_SECRET_KEY قوی و تصادفی لازم است "
            "(python -c \"from django.core.management.utils import get_random_secret_key as k; print(k())\")."
        )
    if not os.environ.get("DJANGO_ALLOWED_HOSTS"):
        raise ImproperlyConfigured(
            "در حالت پروداکشن DJANGO_ALLOWED_HOSTS را تنظیم کنید (مثلاً example.com,www.example.com)."
        )
    if not DATABASE_URL:
        raise ImproperlyConfigured("در حالت پروداکشن DATABASE_URL (PostgreSQL) الزامی است.")

# ---------------------------------------------------------------------------
# لاگ: همه چیز روی stdout/stderr تا در `docker compose logs` دیده شود
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
