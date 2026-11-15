# =============================================================================
# آب پاک | ABPAK — ایمیج اپلیکیشن جنگو
# وب با gunicorn، کارهای پس‌زمینه با celery (هر دو از همین ایمیج اجرا می‌شوند)
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# وابستگی‌های پایتون در یک لایه جدا تا کش بیلد حفظ شود
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# کد پروژه (فایل‌های بی‌مصرف با .dockerignore حذف می‌شوند)
COPY . .

RUN chmod +x entrypoint.sh \
    && mkdir -p /app/media /app/staticfiles

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

# مقدار پیش‌فرض برای سرویس وب؛ ورکر/بیت در docker-compose دستور خودشان را دارند
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
