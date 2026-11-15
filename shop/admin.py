from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import (
    Brand,
    Category,
    ContactMessage,
    Order,
    OrderItem,
    Product,
    ProductImage,
    Profile,
    SiteSettings,
)

admin.site.site_header = "مدیریت فروشگاه آب پاک"
admin.site.site_title = "آب پاک"
admin.site.index_title = "پنل مدیریت فروشگاه"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt", "is_primary", "sort_order", "preview")
    readonly_fields = ("preview",)

    @admin.display(description="پیش‌نمایش")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:60px;border-radius:6px" />', obj.image.url)
        return "—"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "brand", "price", "stock", "is_active", "is_featured")
    list_filter = ("category", "brand", "is_active", "is_featured")
    list_editable = ("price", "stock", "is_active", "is_featured")
    search_fields = ("name", "sku", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]
    fieldsets = (
        ("اطلاعات پایه", {"fields": ("name", "slug", "category", "brand", "sku", "is_active", "is_featured")}),
        ("توضیحات", {"fields": ("short_description", "description")}),
        ("قیمت و موجودی", {"fields": ("price", "old_price", "stock")}),
        ("مشخصات", {"fields": ("warranty", "application", "compatible_with", "specs")}),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("name", "unit_price", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "full_name",
        "phone",
        "status",
        "payment_status",
        "payment_gateway",
        "total",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_gateway", "shipping_method", "created_at")
    search_fields = ("code", "full_name", "phone", "payment_ref_id")
    readonly_fields = (
        "code",
        "subtotal",
        "shipping_cost",
        "total",
        "payment_gateway",
        "payment_authority",
        "payment_ref_id",
        "paid_at",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"
    fieldsets = (
        ("سفارش", {"fields": ("code", "user", "status", "created_at", "updated_at")}),
        (
            "اطلاعات گیرنده",
            {"fields": ("full_name", "phone", "province", "city", "address", "postal_code", "note")},
        ),
        ("ارسال", {"fields": ("shipping_method", "tracking_code")}),
        (
            "پرداخت",
            {
                "fields": (
                    "payment_method",
                    "payment_status",
                    "subtotal",
                    "shipping_cost",
                    "total",
                    "payment_gateway",
                    "payment_authority",
                    "payment_ref_id",
                    "paid_at",
                )
            },
        ),
    )


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "subject", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("full_name", "phone", "subject", "message")


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]

    def get_inlines(self, request, obj=None):
        return [ProfileInline]


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, UserAdmin)
