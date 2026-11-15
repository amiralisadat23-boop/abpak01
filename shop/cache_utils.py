"""ابزارهای کش مشترک فروشگاه.

ایده: هر تغییری در محصول/دسته/برند یک «نسخه کاتالوگ» را بالا می‌برد و
کلیدهای کش مشتق‌شده (دسته‌های ناوبری، شمارش‌ها) بلافاصله بی‌اعتبار می‌شوند.
به این ترتیب از یک طرف کوئری‌های تکراری هر درخواست حذف می‌شود و از طرف
دیگر بعد از ویرایش در پنل، تغییرات فوراً روی سایت دیده می‌شوند.
"""
from django.core.cache import cache

CATALOG_VERSION_KEY = "abpak:catalog-version"


def catalog_version() -> int:
    """نسخه فعلی کاتالوگ (برای ساختن کلید کش)."""
    version = cache.get(CATALOG_VERSION_KEY)
    if version is None:
        cache.set(CATALOG_VERSION_KEY, 1, None)
        version = 1
    return version


def bump_catalog_version() -> int:
    """نسخه کاتالوگ را یک واحد بالا می‌برد (بعد از ذخیره محصول/دسته/برند)."""
    try:
        return cache.incr(CATALOG_VERSION_KEY)
    except ValueError:
        cache.set(CATALOG_VERSION_KEY, 1, None)
        return 1


def cached_catalog(key_template: str, builder, timeout: int = 900):
    """مقدار را با کلید نسخه‌دار از کش می‌خواند و در صورت نبود می‌سازد."""
    key = key_template.format(version=catalog_version())
    value = cache.get(key)
    if value is None:
        value = builder()
        cache.set(key, value, timeout)
    return value
