#!/bin/sh
# =============================================================================
# آب پاک | ABPAK — نقطه ورود کانتینر
# فقط سرویس وب با RUN_SETUP=1 مایگریشن و collectstatic را اجرا می‌کند تا
# ورکر و بیت سلری با آن تداخل (و قفل SQLite) نداشته باشند.
# =============================================================================
set -e

if [ "${RUN_SETUP:-0}" = "1" ]; then
  echo "[entrypoint] اعمال مایگریشن‌ها..."
  python manage.py migrate --noinput

  echo "[entrypoint] جمع‌آوری فایل‌های استاتیک..."
  python manage.py collectstatic --noinput
fi

exec "$@"
