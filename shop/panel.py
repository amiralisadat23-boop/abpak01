"""پنل اختصاصی مدیریت و شخصی‌سازی فروشگاه (مخصوص کارکنان).

ویوهای این ماژول فقط فرم/قالب را مدیریت می‌کنند؛ آمار، فیلترها و تغییر
وضعیت سفارش‌ها از ``shop.services`` خوانده/انجام می‌شوند.
"""

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import ContactMessage, Order, Product, SiteSettings


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
            services.apply_primary_image(
                product,
                image=self.cleaned_data.get("main_image"),
                remove=self.cleaned_data.get("remove_image", False),
            )
        return product


class OrderPanelForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ("status", "payment_status", "tracking_code")
        widgets = {"tracking_code": forms.TextInput(attrs={"placeholder": "کد رهگیری پستی / باربری"})}


@staff_member_required
def dashboard(request):
    return render(
        request,
        "panel/dashboard.html",
        {
            **services.get_dashboard_context(),
            "panel_section": "dashboard",
            "page_title": "داشبورد مدیریت",
        },
    )


@staff_member_required
def settings_view(request):
    site = services.load_site_settings()
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
    page_obj, q, category = services.get_panel_products_page(request.GET)
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
    page_obj, status, q = services.get_panel_orders_page(request.GET)
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
        _, errors = services.update_order_details(order, form.cleaned_data)
        for error in errors:
            form.add_error("status", error)
        if not errors:
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
    page_obj, unread = services.get_panel_messages_page(request.GET)
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
        services.toggle_message_read(message)
        messages.success(request, "وضعیت پیام تغییر کرد.")
    return redirect("panel:messages")

