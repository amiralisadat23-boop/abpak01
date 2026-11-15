"""ورود محصولات تصفیه آب ACE از فروشگاه مرجع به فروشگاه آب پاک.

داده‌ها از Store API عمومی ووکامرس (acewater.org) خوانده می‌شود و تصاویر
در پوشه media/products/ace ذخیره می‌شوند.

نمونه اجرا:
    python manage.py import_acewater
    python manage.py import_acewater --limit 8
"""

import json
import re
import urllib.request
from html import unescape
from urllib.parse import quote

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from shop.models import Brand, Category, Product, ProductImage

API = "https://acewater.org/wp-json/wc/store/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ABPAK-importer/1.0)"}
IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp)(?:\?|$)", re.I)


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_html(value):
    text = re.sub(r"<(script|style).*?</\1>", " ", value or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def short_text(value, limit=280):
    text = clean_html(value).replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def pick_category(name, slug):
    name = (name or "").strip()
    if "خانگی" in name or "water-purification" in slug:
        options = [("home-water-purifiers", "دستگاه تصفیه آب خانگی", "home")]
    elif "فیلتر" in name:
        options = [("filters-cartridges", "فیلترها و کارتریج‌ها", "filter")]
    else:
        options = [("pumps-accessories", "پمپ و تجهیزات جانبی", "pump")]
    for cat_slug, cat_name, icon in options:
        category = Category.objects.filter(slug=cat_slug).first()
        if category:
            return category
    return Category.objects.create(
        name=options[0][1], slug=options[0][0], icon=options[0][2], is_active=True
    )


class Command(BaseCommand):
    help = "ورود محصولات تصفیه آب ACE همراه با قیمت، مشخصات و تصویر"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="حداکثر تعداد محصول برای ورود")
        parser.add_argument("--keep-seed", action="store_true", help="محصولات قبلی را غیرفعال نکن")

    def handle(self, *args, **options):
        categories = fetch(f"{API}/categories?per_page=100&lang=fa")
        target_categories = [
            category
            for category in categories
            if "خانگی" in category["name"] or "فیلتر" in category["name"] or "جانبی" in category["name"]
        ]
        brand, _ = Brand.objects.get_or_create(
            slug="ace",
            defaults={"name": "ACE", "country": "ایران", "description": "آتیه کاوش افتخار — سازنده تجهیزات تصفیه آب"},
        )

        created = updated = skipped = images = drafts = 0
        limit = options["limit"] or 9999
        seen = 0
        # محصولات قبلی همین برند موقتاً غیرفعال می‌شوند تا ورود دوباره تکراری نسازد.
        Product.objects.filter(sku__startswith="ACE-").update(is_active=False)

        for category in target_categories:
            try:
                items = fetch(f"{API}?category={category['id']}&per_page=100&lang=fa")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"دریافت دسته {category['name']} ناموفق: {exc}")
                continue

            for item in items:
                if seen >= limit:
                    break
                price = int(item.get("prices", {}).get("price") or 0)
                if not item.get("images"):
                    skipped += 1
                    continue
                item_categories = item.get("categories") or []
                category_names = [c.get("name", "") for c in item_categories]
                if any("تصفیه هوا" in name for name in category_names):
                    skipped += 1
                    continue
                seen += 1
                target = pick_category(category.get("name", ""), category.get("slug", ""))
                is_active = price > 0
                if not is_active:
                    drafts += 1
                base_slug = slugify(item["name"], allow_unicode=True)[:170] or "ace"
                product_slug = f"{base_slug}-{item['id']}"
                specs = []
                for attribute in item.get("attributes") or []:
                    terms = ", ".join(term.get("name", "") for term in attribute.get("terms", []))
                    if terms:
                        specs.append({"label": attribute.get("name", ""), "value": terms})

                defaults = {
                    "category": target,
                    "brand": brand,
                    "name": item["name"].strip(),
                    "slug": product_slug,
                    "short_description": short_text(item.get("short_description") or item.get("description")),
                    "description": clean_html(item.get("description")),
                    "price": price,
                    "old_price": int(item.get("prices", {}).get("regular_price") or 0) or None,
                    "stock": 8 if is_active else 0,
                    "warranty": "۱۸ ماه ضمانت اصالت و سلامت کالا",
                    "application": "تصفیه آب شرب خانگی و نیمه‌صنعتی",
                    "compatible_with": "خانگی و نیمه‌صنعتی",
                    "specs": specs,
                    "is_active": is_active,
                }
                if defaults["old_price"] and defaults["old_price"] <= price:
                    defaults["old_price"] = None

                product, is_new = Product.objects.update_or_create(
                    sku=f"ACE-{item['id']}", defaults=defaults
                )
                created += int(is_new)
                updated += int(not is_new)

                if not product.images.exists():
                    src = item["images"][0]["src"].split("?")[0]
                    extension = ".jpg"
                    match = IMAGE_EXT.search(src)
                    if match:
                        extension = "." + match.group(1).lower().replace("jpeg", "jpg")
                    try:
                        safe_src = quote(src, safe=":/?&=%")
                        request = urllib.request.Request(safe_src, headers=HEADERS)
                        with urllib.request.urlopen(request, timeout=30) as response:
                            content = response.read()
                        image = ProductImage(product=product, alt=product.name, is_primary=True)
                        image.image.save(f"ace-{item['id']}{extension}", ContentFile(content), save=True)
                        images += 1
                    except Exception as exc:  # noqa: BLE001
                        self.stderr.write(f"تصویر {product.name} دانلود نشد: {exc}")

            if seen >= limit:
                break

        if not options["keep_seed"]:
            Product.objects.exclude(sku__startswith="ACE-").update(is_active=False)
            Product.objects.filter(sku__startswith="ACE-").update(is_featured=False)
            for index, product in enumerate(
                Product.objects.filter(sku__startswith="ACE-", is_active=True).order_by("price")[:8]
            ):
                product.is_featured = index % 2 == 0
                product.save(update_fields=["is_featured"])

        for cat in Category.objects.filter(is_active=True):
            cat.sort_order = cat.sort_order or 0
            cat.save(update_fields=["sort_order"])

        self.stdout.write(
            self.style.SUCCESS(
                f"محصولات ACE: {created} جدید، {updated} بروزرسانی، {images} تصویر، {drafts} پیش‌نویس استعلامی، {skipped} رد شد."
            )
        )
