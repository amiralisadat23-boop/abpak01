# =============================================================================
# آب پاک | ABPAK — ایمیج اپلیکیشن جنگو
# وب با gunicorn، کارهای پس‌زمینه با celery (هر دو از همین ایمیج اجرا می‌شوند)
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONFAULTHANDLER=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# وابستگی‌های پایتون در یک لایه جدا تا کش بیلد حفظ شود
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# کد پروژه (فایل‌های بی‌مصرف با .dockerignore حذف می‌شوند)
COPY . .

# اجرا با کاربر غیر روت (UID 1000 هم‌خوان با مالک پوشه media روی هاست/سرور)
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && chmod +x entrypoint.sh \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

# مقدار پیش‌فرض برای سرویس وب؛ ورکر/بیت در docker-compose دستور خودشان را دارند.
# تعداد ورکرها و تایم‌اوت از متغیر محیطی قابل تنظیم است.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout ${GUNICORN_TIMEOUT:-60} --graceful-timeout 30 --access-logfile - --error-logfile -"]
