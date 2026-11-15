"""بسته تنظیمات پروژه؛ اپ سلری همراه جنگو بارگذاری می‌شود.

با این کار decorator ``@shared_task`` در همه اپ‌ها به همان اپ سلری وصل می‌شود
و دستور ``celery -A config ...`` اپلیکیشن درست را پیدا می‌کند.
"""
from .celery import app as celery_app

__all__ = ("celery_app",)
