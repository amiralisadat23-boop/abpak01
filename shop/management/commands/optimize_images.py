"""بهینه‌سازی تصاویر محصولات: تغییر اندازه و تبدیل به WebP.

تصاویر اصلی فروشگاه مرجع اغلب ۲۵۰۰ پیکسل و چند صد کیلوبایت هستند،
در حالی که کارت محصول حداکثر ۴۰۰ و گالری ۸۰۰ پیکسل نمایش می‌دهد.
این دستور تصاویر بزرگ را به حداکثر ۱۲۰۰ پیکسل و WebP تبدیل می‌کند
و مسیر فایل را در دیتابیس به‌روز می‌کند.
"""

import io
import os

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from PIL import Image, ImageOps

from shop.models import Brand, Category, ProductImage, SiteSettings


class Command(BaseCommand):
    help = "بهینه‌سازی تصاویر محصولات و برندینگ (تغییر اندازه + WebP)"

    def add_arguments(self, parser):
        parser.add_argument("--max-size", type=int, default=1200, help="حداکثر بُعد تصویر")
        parser.add_argument("--quality", type=int, default=82, help="کیفیت WebP")
        parser.add_argument("--min-kb", type=int, default=50, help="کمترین حجم برای تبدیل (KB)")
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش، بدون تغییر فایل")
        parser.add_argument(
            "--variants",
            action="store_true",
            help="ساخت نسخه‌های ۴۰۰ و ۸۰۰ پیکسلی تصاویر محصول (برای srcset)",
        )

    def handle(self, *args, **options):
        self.max_size = options["max_size"]
        self.quality = options["quality"]
        self.min_bytes = options["min_kb"] * 1024
        self.dry_run = options["dry_run"]

        targets = []
        for obj in ProductImage.objects.exclude(image="").select_related("product"):
            targets.append((obj, "image", ProductImage, f"ProductImage #{obj.pk} ({obj.product.name[:40]})"))
        for obj in Category.objects.exclude(image=""):
            targets.append((obj, "image", Category, f"Category #{obj.pk} ({obj.name})"))
        for obj in Brand.objects.exclude(logo=""):
            targets.append((obj, "logo", Brand, f"Brand #{obj.pk} ({obj.name})"))
        site = SiteSettings.objects.first()
        if site:
            for field in ("logo", "hero_image"):
                if getattr(site, field):
                    targets.append((site, field, SiteSettings, f"SiteSettings ({field})"))

        converted = skipped = 0
        before_total = after_total = 0
        for obj, field, model, label in targets:
            result = self._convert(obj, field, model, label)
            if result is None:
                skipped += 1
            else:
                before, after = result
                converted += 1
                before_total += before
                after_total += after

        if options["variants"] and not self.dry_run:
            self._make_variants(options["quality"])

        cache.delete("abpak:site-settings")
        mode = "پیش‌نمایش (بدون تغییر)" if self.dry_run else "انجام شد"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {converted} تصویر تبدیل شد، {skipped} مورد رد شد | "
                f"{before_total / 1024:.0f}KB → {after_total / 1024:.0f}KB"
            )
        )

    def _make_variants(self, quality):
        """نسخه‌های ۴۰۰ و ۸۰۰ پیکسلی می‌سازد تا مرورگر در موبایل تصویر سبک‌تر بگیرد."""
        created = total_bytes = 0
        for obj in ProductImage.objects.exclude(image="").select_related("product"):
            try:
                path = obj.image.path
            except (ValueError, NotImplementedError):
                continue
            if not os.path.exists(path):
                continue

            stem, _extension = os.path.splitext(path)
            try:
                with Image.open(path) as source:
                    base = ImageOps.exif_transpose(source)
                    source_width = base.width
                    has_alpha = base.mode in ("RGBA", "LA") or (
                        base.mode == "P" and "transparency" in base.info
                    )
                    converted = base.convert("RGBA" if has_alpha else "RGB")

                    for width in (400, 800):
                        if source_width <= width:
                            continue
                        target = f"{stem}-{width}.webp"
                        if os.path.exists(target):
                            continue
                        variant = converted.copy()
                        variant.thumbnail((width, width), Image.LANCZOS)
                        variant.save(target, "WEBP", quality=quality, method=6)
                        created += 1
                        total_bytes += os.path.getsize(target)
            except Exception as exc:  # noqa: BLE001 - یک تصویر خراب کل دستور را متوقف نکند
                self.stderr.write(f"  خطا در ساخت نسخه {path}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(f"نسخه‌های ریسپانسیو: {created} فایل ساخته شد ({total_bytes / 1024:.0f}KB).")
        )

    def _convert(self, obj, field, model, label):
        image_field = getattr(obj, field)
        if not image_field:
            return None
        try:
            path = image_field.path
        except (ValueError, NotImplementedError):
            return None
        if not os.path.exists(path):
            return None

        before = os.path.getsize(path)
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source)
                width, height = image.size
                if (
                    before < self.min_bytes
                    and max(width, height) <= self.max_size
                    and path.lower().endswith(".webp")
                ):
                    return None
                if before < self.min_bytes and max(width, height) <= self.max_size:
                    self.stdout.write(f"  رد شد (کوچک): {label}")
                    return None

                if max(width, height) > self.max_size:
                    image.thumbnail((self.max_size, self.max_size), Image.LANCZOS)
                has_alpha = image.mode in ("RGBA", "LA") or (
                    image.mode == "P" and "transparency" in image.info
                )
                image = image.convert("RGBA" if has_alpha else "RGB")

                target = os.path.splitext(path)[0] + ".webp"
                if os.path.exists(target) and os.path.abspath(target) != os.path.abspath(path):
                    target = os.path.splitext(path)[0] + "-optimized.webp"
                if os.path.exists(target) and os.path.abspath(target) != os.path.abspath(path):
                    self.stdout.write(f"  رد شد (فایل مقصد موجود): {label}")
                    return None

                buffer = io.BytesIO()
                image.save(buffer, "WEBP", quality=self.quality, method=6)
                after = buffer.tell()
                if after >= before * 0.95:
                    self.stdout.write(f"  رد شد (بدون صرفه): {label}")
                    return None
                if self.dry_run:
                    self.stdout.write(
                        f"  [dry] {label}: {before / 1024:.0f}KB → {after / 1024:.0f}KB"
                    )
                    return before, after

                if os.path.abspath(target) == os.path.abspath(path):
                    temp = target + ".tmp"
                    image.save(temp, "WEBP", quality=self.quality, method=6)
                    os.replace(temp, target)
                else:
                    image.save(target, "WEBP", quality=self.quality, method=6)
                    new_name = os.path.relpath(target, settings.MEDIA_ROOT).replace(os.sep, "/")
                    model.objects.filter(pk=obj.pk).update(**{field: new_name})
                    if os.path.abspath(path) != os.path.abspath(target):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
        except Exception as exc:  # noqa: BLE001 - گزارش خطای یک تصویر نباید کل دستور را متوقف کند
            self.stderr.write(f"  خطا در {label}: {exc}")
            return None

        self.stdout.write(f"  تبدیل شد: {label}: {before / 1024:.0f}KB → {after / 1024:.0f}KB")
        return before, after
