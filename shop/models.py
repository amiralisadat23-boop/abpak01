import os
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone


PROVINCES = [
    ("تهران", "تهران"),
    ("البرز", "البرز"),
    ("اصفهان", "اصفهان"),
    ("فارس", "فارس"),
    ("خراسان رضوی", "خراسان رضوی"),
    ("آذربایجان شرقی", "آذربایجان شرقی"),
    ("آذربایجان غربی", "آذربایجان غربی"),
    ("اردبیل", "اردبیل"),
    ("ایلام", "ایلام"),
    ("بوشهر", "بوشهر"),
    ("چهارمحال و بختیاری", "چهارمحال و بختیاری"),
    ("خراسان جنوبی", "خراسان جنوبی"),
    ("خراسان شمالی", "خراسان شمالی"),
    ("خوزستان", "خوزستان"),
    ("زنجان", "زنجان"),
    ("سمنان", "سمنان"),
    ("سیستان و بلوچستان", "سیستان و بلوچستان"),
    ("قزوین", "قزوین"),
    ("قم", "قم"),
    ("کردستان", "کردستان"),
    ("کرمان", "کرمان"),
    ("کرمانشاه", "کرمانشاه"),
    ("کهگیلویه و بویراحمد", "کهگیلویه و بویراحمد"),
    ("گلستان", "گلستان"),
    ("گیلان", "گیلان"),
    ("لرستان", "لرستان"),
    ("مازندران", "مازندران"),
    ("مرکزی", "مرکزی"),
    ("هرمزگان", "هرمزگان"),
    ("همدان", "همدان"),
    ("یزد", "یزد"),
]


class Category(models.Model):
    """دسته‌بندی تخصصی محصولات تصفیه آب"""

    ICON_CHOICES = [
        ("home", "دستگاه خانگی"),
        ("factory", "دستگاه صنعتی"),
        ("filter", "فیلتر و کارتریج"),
        ("pump", "پمپ"),
        ("tank", "مخزن"),
        ("valve", "شیر و اتصالات"),
        ("membrane", "ممبران"),
    ]

    name = models.CharField("نام دسته", max_length=120)
    slug = models.SlugField("نشانه (slug)", max_length=140, unique=True, allow_unicode=True)
    icon = models.CharField("آیکون", max_length=20, choices=ICON_CHOICES, default="filter")
    short_description = models.CharField("توضیح کوتاه", max_length=200, blank=True)
    description = models.TextField("توضیحات", blank=True)
    image = models.ImageField("تصویر دسته", upload_to="categories/", blank=True, null=True)
    sort_order = models.PositiveSmallIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:category", args=[self.slug])

    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()


class Brand(models.Model):
    name = models.CharField("نام برند", max_length=100)
    slug = models.SlugField("نشانه (slug)", max_length=120, unique=True, allow_unicode=True)
    country = models.CharField("کشور", max_length=60, blank=True)
    description = models.CharField("توضیح کوتاه", max_length=250, blank=True)
    logo = models.ImageField("لوگو", upload_to="brands/", blank=True, null=True)

    class Meta:
        verbose_name = "برند"
        verbose_name_plural = "برندها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Product(models.Model):
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی", related_name="products", on_delete=models.PROTECT
    )
    brand = models.ForeignKey(
        Brand, verbose_name="برند", related_name="products", on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField("نام محصول", max_length=220)
    slug = models.SlugField("نشانه (slug)", max_length=240, unique=True, allow_unicode=True)
    sku = models.CharField("کد کالا", max_length=40, blank=True)
    short_description = models.CharField("توضیح کوتاه", max_length=300, blank=True)
    description = models.TextField("توضیحات کامل", blank=True)
    price = models.PositiveBigIntegerField("قیمت (تومان)")
    old_price = models.PositiveBigIntegerField("قیمت قبل از تخفیف (تومان)", null=True, blank=True)
    stock = models.PositiveIntegerField("موجودی", default=0)
    warranty = models.CharField("شرایط گارانتی", max_length=200, blank=True)
    application = models.CharField("کاربرد محصول", max_length=250, blank=True)
    compatible_with = models.CharField("نوع دستگاه سازگار", max_length=250, blank=True)
    specs = models.JSONField("مشخصات فنی", default=list, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    is_featured = models.BooleanField("محصول ویژه", default=False)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["-created_at", "id"]
        indexes = [
            # فهرست‌ها همیشه روی محصولات فعال مرتب‌شده بر اساس تاریخ کار می‌کنند.
            models.Index(fields=["is_active", "-created_at"], name="shop_prod_active_created"),
            # صفحه دسته‌بندی.
            models.Index(fields=["category", "is_active"], name="shop_prod_cat_active"),
            # بلوک «محصولات منتخب» صفحه اصلی.
            models.Index(fields=["is_featured", "is_active"], name="shop_prod_featured"),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.slug])

    @property
    def has_discount(self):
        return bool(self.old_price and self.old_price > self.price)

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return max(1, round((self.old_price - self.price) * 100 / self.old_price))

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def saving(self):
        """مبلغ صرفه‌جویی نسبت به قیمت قبل از تخفیف"""
        if not self.has_discount:
            return 0
        return self.old_price - self.price

    @property
    def main_image(self):
        images = list(self.images.all())
        if not images:
            return None
        for image in images:
            if image.is_primary:
                return image
        return images[0]

    @property
    def gallery(self):
        return self.images.all()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)[:240]
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, verbose_name="محصول", related_name="images", on_delete=models.CASCADE
    )
    image = models.ImageField("فایل تصویر", upload_to="products/%Y/%m/")
    alt = models.CharField("متن جایگزین", max_length=200, blank=True)
    is_primary = models.BooleanField("تصویر اصلی", default=False)
    sort_order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "تصویر محصول"
        verbose_name_plural = "تصاویر محصولات"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["product", "is_primary"], name="shop_img_prod_primary"),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.id}"

    def _variant_url(self, suffix: str) -> str:
        """آدرس نسخه تغییراندازه‌شده تصویر (اگر ساخته شده باشد).

        مثال: media/products/2026/11/ace-1.webp → ace-1-400.webp
        دستور `manage.py optimize_images --variants` این نسخه‌ها را می‌سازد.
        """
        if not self.image:
            return ""
        stem, _extension = os.path.splitext(self.image.name)
        candidate = f"{stem}{suffix}.webp"
        try:
            if self.image.storage.exists(candidate):
                return self.image.storage.url(candidate)
        except Exception:  # noqa: BLE001 - نبود فایل نباید صفحه را خراب کند
            return ""
        return ""

    @property
    def card_url(self) -> str:
        """نسخه ۴۰۰ پیکسلی کارت محصول."""
        return self._variant_url("-400")

    @property
    def large_url(self) -> str:
        """نسخه ۸۰۰ پیکسلی گالری/دسته."""
        return self._variant_url("-800")


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="profile"
    )
    phone = models.CharField("شماره تماس", max_length=11, blank=True)
    province = models.CharField("استان", max_length=50, blank=True, choices=PROVINCES)
    city = models.CharField("شهر", max_length=80, blank=True)
    address = models.TextField("آدرس", blank=True)
    postal_code = models.CharField("کد پستی", max_length=10, blank=True)

    class Meta:
        verbose_name = "پروفایل"
        verbose_name_plural = "پروفایل‌ها"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PROCESSING = "processing"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "در انتظار بررسی"),
        (STATUS_CONFIRMED, "تایید شده"),
        (STATUS_PROCESSING, "در حال آماده‌سازی"),
        (STATUS_SHIPPED, "ارسال شده"),
        (STATUS_DELIVERED, "تحویل داده شده"),
        (STATUS_CANCELED, "لغو شده"),
    ]

    PAYMENT_UNPAID = "unpaid"
    PAYMENT_AWAITING = "awaiting_transfer"
    PAYMENT_PAID = "paid"

    PAYMENT_CHOICES = [
        (PAYMENT_UNPAID, "پرداخت در محل"),
        (PAYMENT_AWAITING, "در انتظار انتقال بانکی"),
        (PAYMENT_PAID, "پرداخت شده"),
    ]

    code = models.CharField("کد سفارش", max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        related_name="orders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField("شماره تماس", max_length=11)
    province = models.CharField("استان", max_length=50)
    city = models.CharField("شهر", max_length=80)
    address = models.TextField("آدرس")
    postal_code = models.CharField("کد پستی", max_length=10)
    note = models.TextField("توضیحات سفارش", blank=True)

    shipping_method = models.CharField("روش ارسال", max_length=20, default="post")
    payment_method = models.CharField("روش پرداخت", max_length=20, default="cod")
    payment_status = models.CharField(
        "وضعیت پرداخت", max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_UNPAID
    )
    status = models.CharField("وضعیت سفارش", max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    subtotal = models.PositiveBigIntegerField("جمع کالاها", default=0)
    shipping_cost = models.PositiveBigIntegerField("هزینه ارسال", default=0)
    total = models.PositiveBigIntegerField("مبلغ نهایی", default=0)
    tracking_code = models.CharField("کد رهگیری مرسوله", max_length=60, blank=True)

    # اطلاعات تراکنش آنلاین (درگاه زرین‌پال). این فیلدها فقط سمت سرور و بعد از
    # تأیید (verify) درگاه پر می‌شوند؛ هیچ مقداری از پارامترهای مرورگر گرفته نمی‌شود.
    payment_gateway = models.CharField("درگاه پرداخت", max_length=30, blank=True)
    payment_authority = models.CharField(
        "شناسه تراکنش درگاه", max_length=80, blank=True, db_index=True
    )
    payment_ref_id = models.CharField("کد پیگیری تراکنش", max_length=80, blank=True)
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        indexes = [
            # «سفارش‌های من» و داشبورد پنل.
            models.Index(fields=["user", "-created_at"], name="shop_order_user_created"),
            models.Index(fields=["status", "-created_at"], name="shop_order_status_created"),
            # پیگیری سفارش با شماره تماس.
            models.Index(fields=["phone"], name="shop_order_phone"),
        ]

    def __str__(self):
        return self.code

    def get_absolute_url(self):
        return reverse("shop:order_detail", args=[self.code])

    @property
    def status_index(self):
        steps = [
            self.STATUS_PENDING,
            self.STATUS_CONFIRMED,
            self.STATUS_PROCESSING,
            self.STATUS_SHIPPED,
            self.STATUS_DELIVERED,
        ]
        if self.status == self.STATUS_CANCELED:
            return -1
        try:
            return steps.index(self.status)
        except ValueError:
            return 0

    @property
    def items_count(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def is_online_payment(self) -> bool:
        """آیا سفارش با درگاه آنلاین ثبت شده است؟"""
        return self.payment_method == "online"

    @property
    def is_paid(self) -> bool:
        return self.payment_status == self.PAYMENT_PAID

    @property
    def shipping_label(self):
        method = settings.SHIPPING_METHODS.get(self.shipping_method, {})
        return method.get("label") or self.shipping_method

    @property
    def payment_label(self):
        return settings.PAYMENT_METHODS.get(self.payment_method, {}).get("label", self.payment_method)

    def save(self, *args, **kwargs):
        if not self.code:
            prefix = timezone.now().strftime("%y%m%d")
            self.code = f"ABP-{prefix}-{uuid.uuid4().hex[:5].upper()}"
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name="سفارش", related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, verbose_name="محصول", related_name="order_items", on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField("نام محصول", max_length=220)
    slug = models.CharField("نشانه محصول", max_length=240, blank=True)
    unit_price = models.PositiveBigIntegerField("قیمت واحد")
    quantity = models.PositiveIntegerField("تعداد", default=1)

    class Meta:
        verbose_name = "آیتم سفارش"
        verbose_name_plural = "آیتم‌های سفارش"

    def __str__(self):
        return f"{self.name} × {self.quantity}"

    @property
    def total_price(self):
        return self.unit_price * self.quantity


class ContactMessage(models.Model):
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField("شماره تماس", max_length=11)
    email = models.EmailField("ایمیل", blank=True)
    subject = models.CharField("موضوع", max_length=150)
    message = models.TextField("متن پیام")
    is_read = models.BooleanField("خوانده شده", default=False)
    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)

    class Meta:
        verbose_name = "پیام تماس"
        verbose_name_plural = "پیام‌های تماس"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_read", "-created_at"], name="shop_msg_read_created"),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.subject}"


class SiteSettings(models.Model):
    """تنظیمات قابل ویرایش سایت از پنل اختصاصی (تک‌نمونه)."""

    FONT_VAZIRMATN = "vazirmatn"
    FONT_TAHOMA = "tahoma"
    FONT_CUSTOM = "custom"
    FONT_CHOICES = [
        (FONT_VAZIRMATN, "وزیرمتن (پیشنهادی)"),
        (FONT_TAHOMA, "تاهوما"),
        (FONT_CUSTOM, "فونت سفارشی (بارگذاری فایل woff2)"),
    ]

    site_name = models.CharField("نام سایت", max_length=80, default="آب پاک")
    site_name_en = models.CharField("نام انگلیسی", max_length=80, default="ABPAK")
    tagline = models.CharField("شعار سایت", max_length=160, default="تجهیزات تصفیه آب خانگی و صنعتی")
    phone = models.CharField("تلفن نمایشی", max_length=40, default="۰۲۱-۹۱۰۰۴۵۶۷")
    phone_raw = models.CharField("تلفن برای تماس", max_length=40, default="02191004567")
    mobile = models.CharField("موبایل", max_length=40, blank=True, default="۰۹۱۲۳۴۵۶۷۸۹")
    email = models.EmailField("ایمیل", blank=True, default="info@abpak.ir")
    address = models.CharField("آدرس", max_length=300, blank=True, default="تهران، خیابان ولیعصر، برج آبان، طبقه ۵")
    working_hours = models.CharField("ساعات پاسخگویی", max_length=120, default="شنبه تا پنجشنبه، ۹ صبح تا ۹ شب")
    tapsi_shop = models.URLField(
        "فروشگاه تپسی‌شاپ",
        blank=True,
        default="https://tapsi.shop/store/1439158740070203392/HIT759060",
    )
    instagram = models.URLField("اینستاگرام", blank=True, default="https://instagram.com/")
    telegram = models.URLField("تلگرام", blank=True, default="https://t.me/")
    whatsapp = models.URLField("واتساپ", blank=True, default="https://wa.me/989123456789")

    CURSOR_DROPLET = "droplet"
    CURSOR_SYSTEM = "system"
    CURSOR_CHOICES = [
        (CURSOR_DROPLET, "کرسر قطره‌ای (سفارشی آب پاک)"),
        (CURSOR_SYSTEM, "کرسر پیش‌فرض سیستم"),
    ]

    font_choice = models.CharField("فونت سایت", max_length=20, choices=FONT_CHOICES, default=FONT_VAZIRMATN)
    custom_font = models.FileField("فایل فونت سفارشی", upload_to="fonts/", blank=True, null=True)
    cursor_style = models.CharField("کرسر موس سایت", max_length=20, choices=CURSOR_CHOICES, default=CURSOR_DROPLET)
    animations_enabled = models.BooleanField("انیمیشن‌های حرکتی و اسکرول", default=True)
    logo = models.ImageField("لوگوی سایت", upload_to="branding/", blank=True, null=True)
    hero_image = models.ImageField("تصویر هیرو (صفحه اصلی)", upload_to="branding/", blank=True, null=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return "تنظیمات سایت"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("abpak:site-settings")

    @classmethod
    def load(cls):
        obj = cache.get("abpak:site-settings")
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set("abpak:site-settings", obj, 600)
        return obj

    @property
    def font_stack(self):
        base = '"Vazirmatn", "Segoe UI", Tahoma, sans-serif'
        if self.font_choice == self.FONT_CUSTOM and self.custom_font:
            return '"ABPAK-Custom", ' + base
        if self.font_choice == self.FONT_TAHOMA:
            return 'Tahoma, "Segoe UI", sans-serif'
        return base
