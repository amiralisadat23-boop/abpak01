"""اپلیکیشن سلری پروژه آب پاک.

اجرا:
    celery -A config worker -l info
    celery -A config beat -l info
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("abpak")

# همه تنظیمات با پیشوند CELERY_ از config/settings.py خوانده می‌شوند
app.config_from_object("django.conf:settings", namespace="CELERY")

# تسک‌های داخل shop/tasks.py و هر اپ نصب‌شده به‌صورت خودکار پیدا می‌شوند
app.autodiscover_tasks()


@app.task(bind=True, name="config.debug_task")
def debug_task(self):
    """تسک ساده برای بررسی اتصال ورکر (سلری به آن نیاز ندارد)."""
    return f"celery ok: {self.request.id}"
