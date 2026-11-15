"""گزارش سریع عملکرد فروشگاه.

برای هر صفحه مهم، تعداد کوئری‌های دیتابیس، میانگین زمان پاسخ و حجم HTML را
اندازه می‌گیرد. بعد از هر تغییر در کد یا تنظیمات کش، همین دستور را اجرا کنید
تا مطمئن شوید چیزی کندتر نشده است:

    python manage.py perf_report
    python manage.py perf_report --runs 5
"""

import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from shop.models import Product


class Command(BaseCommand):
    help = "گزارش تعداد کوئری، زمان پاسخ و حجم HTML صفحات کلیدی"

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=3, help="تعداد تکرار برای میانگین‌گیری")

    def handle(self, *args, **options):
        runs = max(1, options["runs"])
        product = Product.objects.filter(is_active=True).first()
        product_path = f"/product/{product.slug}/" if product else "/products/"

        pages = [
            ("/", "صفحه اصلی"),
            ("/products/", "فهرست محصولات"),
            ("/products/?page=2&sort=price_asc", "فهرست صفحه ۲"),
            (product_path, "صفحه محصول"),
            ("/search/?q=%D9%85%D9%85%D8%A8%D8%B1%D8%A7%D9%86", "جستجو"),
            ("/cart/", "سبد خرید"),
            ("/faq/", "سوالات متداول"),
            ("/contact/", "تماس با ما"),
        ]

        client = Client()
        # یک بار گرم‌کردن کش‌ها تا اعداد پایدار باشند.
        for path, _label in pages:
            client.get(path)

        self.stdout.write(f"{'صفحه':28} {'کوئری':>7} {'میانگین ms':>11} {'HTML KB':>9}")
        self.stdout.write("-" * 60)

        for path, label in pages:
            durations = []
            queries = 0
            size = 0
            for _ in range(runs):
                started = time.perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(path)
                durations.append((time.perf_counter() - started) * 1000)
                queries = len(captured)
                size = len(response.content)

            average = sum(durations) / len(durations)
            self.stdout.write(f"{label:28} {queries:7} {average:11.1f} {size / 1024:9.1f}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "نکته: اعداد در حالت DEBUG اندازه‌گیری می‌شوند؛ در پروداکشن با "
                "WhiteNoise و DEBUG=0 سریع‌تر خواهند بود."
            )
        )
