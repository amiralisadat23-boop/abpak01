"""تسک‌های پس‌زمینه فروشگاه (اجرا توسط سرویس worker در docker-compose).

تسک‌ها فقط پوسته اجرای غیرهم‌زمان هستند؛ منطق واقعی در ``shop.services`` است.
"""
from celery import shared_task

from . import services


@shared_task(name="shop.tasks.clear_expired_sessions")
def clear_expired_sessions() -> str:
    """پاک‌سازی نشست‌های منقضی‌شده؛ در زمان‌بندی شبانه بیت اجرا می‌شود."""
    return services.clear_expired_sessions()


@shared_task(name="shop.tasks.ping")
def ping() -> str:
    """بررسی سلامت ورکر؛ خروجی ثابت و بدون عوارض جانبی."""
    return "pong"
