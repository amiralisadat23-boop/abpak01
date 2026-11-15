"""تسک‌های پس‌زمینه فروشگاه (اجرا توسط سرویس worker در docker-compose)."""
import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name="shop.tasks.clear_expired_sessions")
def clear_expired_sessions() -> str:
    """پاک‌سازی نشست‌های منقضی‌شده؛ در زمان‌بندی شبانه بیت اجرا می‌شود.

    مدیریت خود جنگو (``clearsessions``) این کار را در هر درخواست انجام نمی‌دهد،
    پس اجرای دوره‌ای آن جدول نشست‌ها را سبک نگه می‌دارد.
    """
    call_command("clearsessions", verbosity=0)
    logger.info("نشست‌های منقضی‌شده پاک شدند")
    return "clearsessions done"


@shared_task(name="shop.tasks.ping")
def ping() -> str:
    """بررسی سلامت ورکر؛ خروجی ثابت و بدون عوارض جانبی."""
    return "pong"
