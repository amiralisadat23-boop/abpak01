"""پنل اختصاصی مدیریت و شخصی‌سازی فروشگاه (مخصوص کارکنان)."""

from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ContactMessage, Order, Product, ProductImage, SiteSettings


class StyledModelForm(forms.ModelForm):
    """اعمال کلاس‌های طراحی روی همه فیلدها."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox__input")
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " field__input").strip()


class SiteSettingsForm(StyledModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "site_name",
            "site_name_en",
            "tagline",
            "logo",
            "hero_image",
            "font_choice",
            "custom_font",
            "cursor_style",
            "animations_enabled",
            "phone",
            "phone_raw",
            "mobile",
            "email",
            "address",
            "working_hours",
            "tapsi_shop",
            "instagram",
            "telegram",
            "whatsapp",
        )
        widgets = {
            "address": forms.TextInput(attrs={"placeholder": "آدرس فروشگاه"}),
            "tagline": forms.TextInput(attrs={"placeholder": "شعار کوتاه سایت"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("font_choice") == SiteSettings.FONT_CUSTOM and not (
            cleaned.get("custom_font") or (self.instance and self.instance.custom_font)
        ):
            self.add_error("custom_font", "برای فونت سفارشی، فایل woff2 را بارگذاری کنید.")
        if cleaned.get("whatsapp") and not str(cleaned["whatsapp"]).startswith(("http://", "https://")):
            self.add_error("whatsapp", "لینک باید با http یا https شروع شود.")
        return cleaned


class ProductPanelForm(StyledModelForm):
    main_image = forms.ImageField(label="تصویر اصلی جدید", required=False)
    remove_image = forms.BooleanField(label="حذف تصویر اصلی فعلی", required=False)

    class Meta:
        model = Product
        fields = (
            "name",
            "category",
            "brand",
            "sku",
            "price",
            "old_price",
            "stock",
            "short_description",
            "description",
            "warranty",
            "application",
            "is_active",
            "is_featured",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "short_description": forms.TextInput(attrs={"placeholder": "یک جمله کوتاه درباره محصول"}),
        }

    def save(self, commit=True):
        product = super().save(commit=commit)
        if commit:
            image = self.cleaned_data.get("main_image")
            if image:
                ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
                ProductImage.objects.create(product=product, image=image, is_primary=True, alt=product.name)
            elif self.cleaned_data.get("remove_image"):
                ProductImage.objects.filter(product=product, is_primary=True).delete()
                first = product.images.first()
                if first:
                    first.is_primary = True
                    first.save(update_fields=["is_primary"])
        return product


class OrderPanelForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ("status", "payment_status", "tracking_code")
        widgets = {"tracking_code": forms.TextInput(attrs={"placeholder": "کد رهگیری پستی / باربری"})}


def _restore_order_stock(order):
    """موجودی اقلام سفارش لغوشده را به انبار برمی‌گرداند."""
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)


def _reapply_order_stock(order):
    """موجودی سفارش را دوباره کسر می‌کند و در صورت کمبود، نام کالاها را برمی‌گرداند."""
    needed = {}
    names = {}
    for item in order.items.all():
        if not item.product_id:
            continue
        needed[item.product_id] = needed.get(item.product_id, 0) + item.quantity
        names[item.product_id] = item.name
    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=needed.keys())
    }
    shortages = [
        f"{names[product_id]} ({products[product_id].stock} عدد موجود)"
        for product_id, quantity in needed.items()
        if product_id in products and products[product_id].stock < quantity
    ]
    if shortages:
        return shortages
    for product_id, quantity in needed.items():
        if product_id in products:
            products[product_id].stock -= quantity
    Product.objects.bulk_update(products.values(), ["stock"])
    return []


@staff_member_required
def dashboard(request):
    now = timezone.now()
    today = now.date()
    stats = {
        "orders": Order.objects.count(),
        "today_orders": Order.objects.filter(created_at__date=today).count(),
        "pending": Order.objects.filter(Q(status=Order.STATUS_PENDING) | Q(status=Order.STATUS_CONFIRMED)).count(),
        "revenue": Order.objects.exclude(status=Order.STATUS_CANCELED).aggregate(total=Sum("total"))["total"] or 0,
        "products": Product.objects.filter(is_active=True).count(),
        "low_stock": Product.objects.filter(is_active=True, stock__lte=2).count(),
        "unread": ContactMessage.objects.filter(is_read=False).count(),
    }
    recent_orders = Order.objects.order_by("-created_at")[:6]
    low_stock = Product.objects.filter(is_active=True, stock__lte=2).order_by("stock")[:6]
    return render(
        request,
        "panel/dashboard.html",
        {
            "stats": stats,
            "recent_orders": recent_orders,
            "low_stock": low_stock,
            "panel_section": "dashboard",
            "page_title": "داشبورد مدیریت",
        },
    )


@staff_member_required
def settings_view(request):
    site = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, request.FILES or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تنظیمات سایت با موفقیت ذخیره شد.")
        return redirect("panel:settings")
    if request.method == "POST":
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    return render(
        request,
        "panel/settings.html",
        {"form": form, "site": site, "panel_section": "settings", "page_title": "شخصی‌سازی سایت"},
    )


@staff_member_required
def product_create(request):
    form = ProductPanelForm(
        request.POST or None,
        request.FILES or None,
        initial={"is_active": True},
    )
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, f"محصول «{product.name}» اضافه شد.")
        return redirect("panel:product_edit", pk=product.pk)
    if request.method == "POST":
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    return render(
        request,
        "panel/product_form.html",
        {
            "form": form,
            "product": None,
            "is_create": True,
            "panel_section": "products",
            "page_title": "افزودن محصول",
        },
    )


@staff_member_required
def products_view(request):
    products = Product.objects.select_related("category", "brand").prefetch_related("images")
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category:
        products = products.filter(category__slug=category)
    page_obj = Paginator(products, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "panel/products.html",
        {
            "page_obj": page_obj,
            "products": page_obj.object_list,
            "q": q,
            "category": category,
            "panel_section": "products",
            "page_title": "مدیریت محصولات",
        },
    )


@staff_member_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductPanelForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "محصول با موفقیت ذخیره شد.")
        return redirect("panel:products")
    if request.method == "POST":
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    return render(
        request,
        "panel/product_form.html",
        {
            "form": form,
            "product": product,
            "panel_section": "products",
            "page_title": f"ویرایش: {product.name}",
        },
    )


@staff_member_required
def orders_view(request):
    orders = Order.objects.prefetch_related("items")
    status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()
    if status in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status)
    if q:
        orders = orders.filter(Q(code__icontains=q) | Q(phone__icontains=q) | Q(full_name__icontains=q))
    page_obj = Paginator(orders, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "panel/orders.html",
        {
            "page_obj": page_obj,
            "orders": page_obj.object_list,
            "status": status,
            "q": q,
            "status_choices": Order.STATUS_CHOICES,
            "panel_section": "orders",
            "page_title": "مدیریت سفارش‌ها",
        },
    )


@staff_member_required
def order_edit(request, code):
    order = get_object_or_404(Order.objects.prefetch_related("items"), code=code)
    form = OrderPanelForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = Order.objects.select_for_update().prefetch_related("items").get(pk=order.pk)
            new_status = form.cleaned_data["status"]
            if locked.status != new_status:
                if new_status == Order.STATUS_CANCELED:
                    _restore_order_stock(locked)
                    locked.status = new_status
                elif locked.status == Order.STATUS_CANCELED:
                    shortages = _reapply_order_stock(locked)
                    if shortages:
                        form.add_error(
                            "status",
                            "برای بازفعال‌سازی، موجودی این کالاها کافی نیست: " + "، ".join(shortages),
                        )
                    else:
                        locked.status = new_status
                else:
                    locked.status = new_status
            locked.payment_status = form.cleaned_data["payment_status"]
            locked.tracking_code = form.cleaned_data["tracking_code"]
            if not form.errors:
                locked.save()
        if not form.errors:
            messages.success(request, "وضعیت سفارش بروزرسانی شد.")
            return redirect("panel:order_edit", code=order.code)
    if request.method == "POST":
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    return render(
        request,
        "panel/order_form.html",
        {
            "order": order,
            "form": form,
            "items": order.items.all(),
            "panel_section": "orders",
            "page_title": f"سفارش {order.code}",
        },
    )


@staff_member_required
def messages_view(request):
    items = ContactMessage.objects.all()
    unread = request.GET.get("unread") == "1"
    if unread:
        items = items.filter(is_read=False)
    page_obj = Paginator(items, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "panel/messages.html",
        {
            "page_obj": page_obj,
            "messages_list": page_obj.object_list,
            "unread": unread,
            "panel_section": "messages",
            "page_title": "پیام‌های مشتریان",
        },
    )


@staff_member_required
@require_POST
def message_read(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    if request.method == "POST":
        message.is_read = not message.is_read
        message.save(update_fields=["is_read"])
        messages.success(request, "وضعیت پیام تغییر کرد.")
    return redirect("panel:messages")

