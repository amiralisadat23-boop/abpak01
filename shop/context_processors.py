from django.conf import settings
from django.db.models import Count, Q

from .cache_utils import cached_catalog
from .cart import Cart
from .models import Category, SiteSettings
from .utils import to_persian_digits


# دسته‌های ناوبری در هر صفحه لازم‌اند؛ یک‌بار محاسبه و تا تغییر بعدی کاتالوگ کش می‌شوند.
def _nav_categories():
    return list(
        Category.objects.filter(is_active=True)
        .annotate(active_count=Count("products", filter=Q(products__is_active=True)))
        .order_by("sort_order", "id")
    )


def store(request):
    """اطلاعات مشترک همه صفحات: دسته‌ها، شمارنده سبد، تنظیمات قابل ویرایش سایت."""
    cart = Cart(request)
    try:
        site = SiteSettings.load()
    except Exception:  # قبل از اجرای مایگریشن‌ها
        site = None

    store_info = {
        "name": site.site_name if site else settings.SITE_NAME,
        "name_en": site.site_name_en if site else settings.SITE_NAME_EN,
        "tagline": site.tagline if site else settings.SITE_TAGLINE,
        "phone": site.phone if site else settings.SITE_PHONE,
        "phone_raw": site.phone_raw if site else settings.SITE_PHONE_RAW,
        "mobile": site.mobile if site else settings.SITE_MOBILE,
        "email": site.email if site else settings.SITE_EMAIL,
        "address": site.address if site else settings.SITE_ADDRESS,
        "hours": site.working_hours if site else settings.SITE_WORKING_HOURS,
        "tapsi_shop": (getattr(site, "tapsi_shop", "") if site else "") or settings.SITE_TAPSI_SHOP,
        "instagram": site.instagram if site else settings.SITE_INSTAGRAM,
        "telegram": site.telegram if site else settings.SITE_TELEGRAM,
        "whatsapp": site.whatsapp if site else settings.SITE_WHATSAPP,
    }
    if site is None:
        site = SiteSettings()

    return {
        "site": site,
        "nav_categories": cached_catalog("abpak:nav-categories:v{version}", _nav_categories),
        "cart_count": len(cart),
        "STORE": store_info,
        "SHIPPING_METHODS": settings.SHIPPING_METHODS,
        "PAYMENT_METHODS": settings.PAYMENT_METHODS,
        "FREE_SHIPPING_THRESHOLD": settings.FREE_SHIPPING_THRESHOLD,
        "FREE_SHIPPING_THRESHOLD_FA": to_persian_digits(f"{settings.FREE_SHIPPING_THRESHOLD:,}").replace(",", "٬"),
        "PAYMENT_GATEWAY_ENABLED": settings.PAYMENT_GATEWAY_ENABLED,
    }
