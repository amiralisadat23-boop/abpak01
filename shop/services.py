"""لایه سرویس فروشگاه آب پاک.

قاعده معماری این فایل:
    ویوها فقط درخواست را دریافت می‌کنند، داده ورودی را به این سرویس‌ها
    می‌دهند و نتیجه را (context یا dict) به قالب/پاسخ تبدیل می‌کنند.
    هر تصمیم تجاری، کوئری، تراکنش و تغییر موجودی/سفارش فقط اینجاست.

نکته: توابع این ماژول تا حد امکان به ``request`` وابسته نیستند تا از ویوها،
پنل و تسک‌های Celery قابل استفاده مجدد باشند؛ فقط اطلاعات لازم را می‌گیرند.
"""
import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ExpressionWrapper, F, FloatField, Max, Min, Q, Sum
from django.utils import timezone

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
from .payments import PaymentError, get_gateway
from .utils import format_price, to_persian_digits

logger = logging.getLogger(__name__)

SORT_OPTIONS = {
    "newest": "جدیدترین",
    "price_asc": "ارزان‌ترین",
    "price_desc": "گران‌ترین",
    "discount": "بیشترین تخفیف",
}

# تعداد کدهای سفارشی که پس از ثبت/پیگیری در نشست نگه داشته می‌شود
ORDER_ACCESS_LIMIT = 25


# ===========================================================================
# نتایج ساختاریافته
# ===========================================================================
@dataclass
class ServiceResult:
    """نتیجه یک عملیات سرویس که ویو آن را به پیام/ریدایرکت تبدیل می‌کند."""

    ok: bool
    message: str = ""
    level: str = "info"  # برچسب پیام جنگو: success / info / error / warning
    redirect_url: str | None = None
    data: dict = field(default_factory=dict)


# ===========================================================================
# صفحه اصلی
# ===========================================================================
def get_home_context() -> dict:
    products = (
        Product.objects.active()
        .select_related("category", "brand")
        .prefetch_related("images")
    )
    featured = list(products.filter(is_featured=True)[:8])
    if len(featured) < 4:
        extras = list(products.exclude(id__in=[p.id for p in featured])[: 8 - len(featured)])
        featured += extras
    featured_ids = [product.id for product in featured]
    new_arrivals = list(products.exclude(id__in=featured_ids).order_by("-created_at")[:4])
    return {
        "featured_products": featured,
        "new_arrivals": new_arrivals,
        "brands": Brand.objects.all()[:8],
        "total_products": products.count(),
    }


# ===========================================================================
# فهرست محصولات، دسته‌بندی و جستجو
# ===========================================================================
def _parse_price_filter(raw: str) -> int:
    return int("".join(ch for ch in (raw or "") if ch.isdigit()) or 0)


def get_catalog_context(params) -> dict:
    """فیلتر، مرتب‌سازی و صفحه‌بندی محصولات را انجام می‌دهد.

    ``params`` می‌تواند QueryDict یا dict باشد (کلیدهای q، category، brand،
    in_stock، sort، min_price، max_price، page).
    """
    products = (
        Product.objects.active()
        .select_related("category", "brand")
        .prefetch_related("images")
    )
    query = params.get("q", "").strip()
    category_slug = params.get("category", "").strip()
    selected_brands = params.getlist("brand") if hasattr(params, "getlist") else params.get("brand", [])
    stock_filter = params.get("in_stock", "")
    sort = params.get("sort", "newest")
    min_price = params.get("min_price", "").strip()
    max_price = params.get("max_price", "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(brand__name__icontains=query)
        )
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if selected_brands:
        products = products.filter(brand__slug__in=selected_brands)
    if stock_filter == "1":
        products = products.filter(stock__gt=0)

    min_value = _parse_price_filter(min_price)
    max_value = _parse_price_filter(max_price)
    if min_value:
        products = products.filter(price__gte=min_value)
    if max_value:
        products = products.filter(price__lte=max_value)

    products = _apply_sorting(products, sort)

    page_obj = Paginator(products, settings.PRODUCTS_PER_PAGE).get_page(params.get("page"))
    categories = (
        Category.objects.filter(is_active=True)
        .annotate(count=Count("products", filter=Q(products__is_active=True)))
        .order_by("sort_order", "id")
    )
    brands = Brand.objects.annotate(
        count=Count("products", filter=Q(products__is_active=True))
    ).filter(count__gt=0)
    price_range = Product.objects.active().aggregate(low=Min("price"), high=Max("price"))

    return {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "result_count": page_obj.paginator.count,
        "categories": categories,
        "brands": brands,
        "active_category": get_category(category_slug),
        "selected_brands": selected_brands,
        "query": query,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "stock_filter": stock_filter,
        "min_price": min_price,
        "max_price": max_price,
        "min_price_value": price_range["low"] or 0,
        "max_price_value": price_range["high"] or 0,
        "chips": _build_filter_chips(
            query=query,
            active_category=get_category(category_slug),
            brands=brands,
            selected_brands=selected_brands,
            stock_filter=stock_filter,
            min_value=min_value,
            max_value=max_value,
        ),
    }


def _apply_sorting(products, sort: str):
    if sort == "price_asc":
        return products.order_by("price")
    if sort == "price_desc":
        return products.order_by("-price")
    if sort == "discount":
        discount_ratio = ExpressionWrapper(
            (F("old_price") - F("price")) * 1.0 / F("old_price"), output_field=FloatField()
        )
        return (
            products.filter(old_price__gt=F("price"))
            .annotate(discount_ratio=discount_ratio)
            .order_by("-discount_ratio")
        )
    return products.order_by("-created_at")


def _build_filter_chips(query, active_category, brands, selected_brands, stock_filter, min_value, max_value) -> list:
    chips = []
    if query:
        chips.append({"label": f"جستجو: {query}", "remove": "q"})
    if active_category:
        chips.append({"label": f"دسته: {active_category.name}", "remove": "category"})
    for brand in brands.filter(slug__in=selected_brands):
        chips.append({"label": f"برند: {brand.name}", "remove": None, "brand_slug": brand.slug})
    if stock_filter == "1":
        chips.append({"label": "فقط کالاهای موجود", "remove": "in_stock"})
    if min_value:
        chips.append({"label": f"از {format_price(min_value)} تومان", "remove": "min_price"})
    if max_value:
        chips.append({"label": f"تا {format_price(max_value)} تومان", "remove": "max_price"})
    return chips


def get_category(slug: str):
    if not slug:
        return None
    return Category.objects.filter(slug=slug, is_active=True).first()


def search_suggestions(query: str) -> list:
    if len(query) < 2:
        return []
    products = (
        Product.objects.active()
        .filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(category__name__icontains=query)
        )
        .select_related("category")[:6]
    )
    return [
        {
            "name": product.name,
            "url": product.get_absolute_url(),
            "category": product.category.name,
            "price": format_price(product.price),
            "in_stock": product.in_stock,
            "icon": product.category.icon,
        }
        for product in products
    ]


def get_product_detail_context(slug: str, cart=None):
    """اطلاعات صفحه محصول؛ اگر محصول فعال نبود ``None`` برمی‌گرداند."""
    product = (
        Product.objects.select_related("category", "brand")
        .prefetch_related("images")
        .filter(slug=slug, is_active=True)
        .first()
    )
    if product is None:
        return None
    related = (
        Product.objects.active()
        .filter(category=product.category)
        .exclude(id=product.id)
        .select_related("category", "brand")
        .prefetch_related("images")[:4]
    )
    return {
        "product": product,
        "related_products": related,
        "specs": product.specs or [],
        "cart_quantity": cart.quantity_of(product) if cart is not None else 0,
    }


# ===========================================================================
# سبد خرید
# ===========================================================================
def normalize_quantity(raw, default: int = 1) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def cart_summary(cart, shipping_method=None) -> dict:
    """خلاصه سبد برای پاسخ‌های AJAX."""
    totals = cart.totals(shipping_method)
    return {
        "cart_count": totals["count"],
        "subtotal": totals["subtotal"],
        "subtotal_display": format_price(totals["subtotal"]),
        "shipping": totals["shipping"],
        "shipping_display": format_price(totals["shipping"]),
        "total": totals["total"],
        "total_display": format_price(totals["total"]),
        "free_shipping_remaining": totals["free_shipping_remaining"],
        "free_shipping_remaining_display": format_price(totals["free_shipping_remaining"]),
    }


def get_cart_context(cart) -> dict:
    items = cart.items()
    recommended = (
        Product.objects.active()
        .filter(stock__gt=0)
        .exclude(id__in=[item["product"].id for item in items])
        .select_related("category", "brand")
        .prefetch_related("images")[:4]
    )
    return {"cart_items": items, "totals": cart.totals(), "recommended": recommended}


def add_product_to_cart(cart, product: Product, quantity) -> dict:
    """محصول را به سبد اضافه می‌کند و پیام/تعداد نهایی را برمی‌گرداند."""
    quantity = normalize_quantity(quantity)
    if not product.in_stock:
        return {"ok": False, "message": "این محصول در حال حاضر ناموجود است."}
    cart.add(product, quantity)
    return {
        "ok": True,
        "message": f"«{product.name}» به سبد خرید اضافه شد.",
        "quantity": cart.quantity_of(product),
        **cart_summary(cart),
    }


def update_cart_item(cart, product: Product, quantity) -> dict:
    quantity = normalize_quantity(quantity)
    new_quantity = cart.update(product, quantity)
    limited = 0 < product.stock < quantity
    return {
        "ok": True,
        "quantity": new_quantity,
        "item_total": product.price * new_quantity,
        "item_total_display": format_price(product.price * new_quantity),
        "limited": limited,
        "stock": product.stock,
        "message": (
            f"حداکثر موجودی این محصول {to_persian_digits(product.stock)} عدد است."
            if limited
            else ""
        ),
        **cart_summary(cart),
    }


def remove_cart_item(cart, product: Product) -> dict:
    cart.remove(product)
    return {"ok": True, "message": "محصول از سبد خرید حذف شد.", **cart_summary(cart)}


# ===========================================================================
# سفارش‌ها و پرداخت
# ===========================================================================
def grant_order_access(session, order: Order) -> None:
    """دسترسی به سفارش را در نشست ثبت می‌کند (خرید مهمان)."""
    codes = list(session.get("order_access", []))
    if order.code not in codes:
        codes.append(order.code)
    session["order_access"] = codes[-ORDER_ACCESS_LIMIT:]
    session["last_order_code"] = order.code


def can_view_order(user, session, order: Order) -> bool:
    if user.is_authenticated and (order.user_id == user.id or user.is_staff):
        return True
    return order.code in session.get("order_access", [])


def is_new_order(session, order: Order) -> bool:
    return session.get("last_order_code") == order.code


def find_order_for_tracking(code: str, phone: str):
    return (
        Order.objects.prefetch_related("items")
        .filter(code__iexact=code, phone=phone)
        .first()
    )


def get_order_for_payment(code: str):
    return Order.objects.filter(code=code).first()


def start_online_payment(order: Order, callback_url: str) -> ServiceResult:
    """تراکنش درگاه را می‌سازد و آدرس انتقال کاربر را برمی‌گرداند."""
    if not order.is_online_payment:
        return ServiceResult(False, "این سفارش برای پرداخت آنلاین ثبت نشده است.")
    if order.is_paid:
        return ServiceResult(False, "این سفارش قبلاً پرداخت شده است.")
    if order.status == Order.STATUS_CANCELED:
        return ServiceResult(False, "سفارش لغو شده قابل پرداخت نیست.", level="error")

    gateway = get_gateway()
    if gateway is None:
        return ServiceResult(False, "درگاه پرداخت آنلاین در حال حاضر فعال نیست.", level="error")

    try:
        payment = gateway.request_payment(
            amount_toman=order.total,
            callback_url=callback_url,
            description=f"سفارش {order.code} — {settings.SITE_NAME}",
            mobile=order.phone,
        )
    except PaymentError as exc:
        logger.warning("payment start failed (order=%s): %s", order.code, exc)
        return ServiceResult(False, str(exc), level="error")

    Order.objects.filter(pk=order.pk).update(
        payment_gateway=gateway.slug,
        payment_authority=payment.authority,
    )
    return ServiceResult(True, redirect_url=payment.payment_url)


def handle_payment_callback(order: Order, authority: str, status: str) -> ServiceResult:
    """پاسخ درگاه را تأیید و نتیجه پرداخت را اتمیک ثبت می‌کند."""
    if not authority or authority != (order.payment_authority or ""):
        logger.warning("payment callback with unknown authority (order=%s)", order.code)
        return ServiceResult(False, "پاسخ درگاه معتبر نیست.", level="error")

    if order.is_paid:
        return ServiceResult(False, "این سفارش قبلاً پرداخت شده است.")

    if status != "OK":
        logger.info("payment not completed (order=%s, status=%s)", order.code, status)
        return ServiceResult(
            False,
            "پرداخت لغو شد یا ناموفق بود. اگر مبلغی از حساب شما کسر شده باشد، طی ۷۲ ساعت بازگشت داده می‌شود.",
            level="error",
        )

    gateway = get_gateway()
    if gateway is None:
        return ServiceResult(False, "درگاه پرداخت آنلاین فعال نیست.", level="error")

    try:
        verification = gateway.verify_payment(authority=authority, amount_toman=order.total)
    except PaymentError as exc:
        logger.warning("payment verify error (order=%s): %s", order.code, exc)
        return ServiceResult(False, str(exc), level="error")

    if not verification.verified:
        return ServiceResult(
            False, "پرداخت تأیید نشد. در صورت کسر مبلغ با پشتیبانی تماس بگیرید.", level="error"
        )

    with transaction.atomic():
        updated = (
            Order.objects.filter(pk=order.pk)
            .exclude(payment_status=Order.PAYMENT_PAID)
            .update(
                payment_status=Order.PAYMENT_PAID,
                payment_ref_id=verification.reference_id,
                paid_at=timezone.now(),
                status=Order.STATUS_CONFIRMED,
            )
        )

    if not updated:
        return ServiceResult(False, "این سفارش قبلاً پرداخت شده است.")

    logger.info("order %s paid (ref=%s)", order.code, verification.reference_id)
    return ServiceResult(
        True,
        f"پرداخت با موفقیت انجام شد. کد پیگیری تراکنش: {verification.reference_id}",
        level="success",
        data={"reference_id": verification.reference_id},
    )


# ===========================================================================
# ثبت سفارش
# ===========================================================================
def place_order(user, cleaned_data: dict, cart, shipping_method: str):
    """سفارش را با موجودی به‌روز ثبت می‌کند.

    خروجی: ``(order, errors)``؛ اگر ``order`` باشد، ``errors`` خالی است و اگر
    موجودی کالایی تغییر کرده باشد ``order`` برابر ``None`` و ``errors`` حاوی
    پیام‌های قابل نمایش است.
    """
    items = cart.items()
    totals = cart.totals(shipping_method)
    stock_errors = [item["product"] for item in items if item["quantity"] > item["product"].stock]
    if stock_errors:
        return None, [
            f"موجودی «{product.name}» تغییر کرده است. سبد خرید را بروزرسانی کنید."
            for product in stock_errors
        ]

    with transaction.atomic():
        order = Order.objects.create(
            user=user if user.is_authenticated else None,
            full_name=cleaned_data["full_name"],
            phone=cleaned_data["phone"],
            province=cleaned_data["province"],
            city=cleaned_data["city"],
            address=cleaned_data["address"],
            postal_code=cleaned_data["postal_code"],
            note=cleaned_data["note"],
            shipping_method=shipping_method,
            payment_method=cleaned_data["payment_method"],
            payment_status=(
                Order.PAYMENT_AWAITING
                if cleaned_data["payment_method"] == "transfer"
                else Order.PAYMENT_UNPAID
            ),
            subtotal=totals["subtotal"],
            shipping_cost=totals["shipping"],
            total=totals["total"],
            status=Order.STATUS_PENDING,
        )
        for item in items:
            product = Product.objects.select_for_update().get(id=item["product"].id)
            OrderItem.objects.create(
                order=order,
                product=product,
                name=product.name,
                slug=product.slug,
                unit_price=product.price,
                quantity=item["quantity"],
            )
            product.stock = max(0, product.stock - item["quantity"])
            product.save(update_fields=["stock"])
        if user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile:
                profile.phone = cleaned_data["phone"]
                profile.province = cleaned_data["province"]
                profile.city = cleaned_data["city"]
                profile.address = cleaned_data["address"]
                profile.postal_code = cleaned_data["postal_code"]
                profile.save()
        cart.clear()
    return order, []


def order_redirect_name(order: Order) -> str:
    """نام URL مقصد بعد از ثبت سفارش (درگاه برای سفارش آنلاین)."""
    if order.is_online_payment and get_gateway() is not None:
        return "shop:payment_start"
    return "shop:order_detail"


def get_order_status_stats(orders) -> dict:
    return {
        "orders": orders.count(),
        "in_progress": orders.filter(
            status__in=[
                Order.STATUS_PENDING,
                Order.STATUS_CONFIRMED,
                Order.STATUS_PROCESSING,
                Order.STATUS_SHIPPED,
            ]
        ).count(),
        "delivered": orders.filter(status=Order.STATUS_DELIVERED).count(),
    }


# ===========================================================================
# حساب کاربری
# ===========================================================================
def get_or_create_profile(user) -> Profile:
    profile, _ = Profile.objects.get_or_create(user=user, defaults={"phone": user.username})
    return profile


def get_user_orders(user):
    return user.orders.prefetch_related("items")


def paginate_orders(orders, status_filter: str, page, per_page: int = 8):
    if status_filter in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status_filter)
    return Paginator(orders, per_page).get_page(page)


# ===========================================================================
# تماس با ما
# ===========================================================================
def create_contact_message(cleaned_data: dict) -> ContactMessage:
    return ContactMessage.objects.create(**cleaned_data)


# ===========================================================================
# پنل مدیریت
# ===========================================================================
def get_dashboard_context() -> dict:
    today = timezone.now().date()
    return {
        "stats": {
            "orders": Order.objects.count(),
            "today_orders": Order.objects.filter(created_at__date=today).count(),
            "pending": Order.objects.filter(
                Q(status=Order.STATUS_PENDING) | Q(status=Order.STATUS_CONFIRMED)
            ).count(),
            "revenue": Order.objects.exclude(status=Order.STATUS_CANCELED).aggregate(
                total=Sum("total")
            )["total"]
            or 0,
            "products": Product.objects.filter(is_active=True).count(),
            "low_stock": Product.objects.filter(is_active=True, stock__lte=2).count(),
            "unread": ContactMessage.objects.filter(is_read=False).count(),
        },
        "recent_orders": Order.objects.order_by("-created_at")[:6],
        "low_stock": Product.objects.filter(is_active=True, stock__lte=2).order_by("stock")[:6],
    }


def get_panel_products_page(params, per_page: int = 20):
    products = Product.objects.select_related("category", "brand").prefetch_related("images")
    q = params.get("q", "").strip()
    category = params.get("category", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category:
        products = products.filter(category__slug=category)
    return Paginator(products, per_page).get_page(params.get("page")), q, category


def get_panel_orders_page(params, per_page: int = 20):
    orders = Order.objects.prefetch_related("items")
    status = params.get("status", "").strip()
    q = params.get("q", "").strip()
    if status in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status)
    if q:
        orders = orders.filter(
            Q(code__icontains=q) | Q(phone__icontains=q) | Q(full_name__icontains=q)
        )
    return Paginator(orders, per_page).get_page(params.get("page")), status, q


def get_panel_messages_page(params, per_page: int = 20):
    items = ContactMessage.objects.all()
    unread = params.get("unread") == "1"
    if unread:
        items = items.filter(is_read=False)
    return Paginator(items, per_page).get_page(params.get("page")), unread


def restore_order_stock(order: Order) -> None:
    """موجودی اقلام سفارش لغوشده را به انبار برمی‌گرداند."""
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)


def reapply_order_stock(order: Order) -> list:
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


def update_order_details(order: Order, cleaned_data: dict):
    """وضعیت/پرداخت/رهگیری سفارش را با مدیریت برگشت موجودی به‌روز می‌کند.

    خروجی: ``(order, errors)``؛ ``errors`` فهرست پیام‌های خطای اعتبارسنجی است.
    """
    errors = []
    with transaction.atomic():
        locked = Order.objects.select_for_update().prefetch_related("items").get(pk=order.pk)
        new_status = cleaned_data["status"]
        if locked.status != new_status:
            if new_status == Order.STATUS_CANCELED:
                restore_order_stock(locked)
                locked.status = new_status
            elif locked.status == Order.STATUS_CANCELED:
                shortages = reapply_order_stock(locked)
                if shortages:
                    errors.append(
                        "برای بازفعال‌سازی، موجودی این کالاها کافی نیست: " + "، ".join(shortages)
                    )
                else:
                    locked.status = new_status
            else:
                locked.status = new_status
        locked.payment_status = cleaned_data["payment_status"]
        locked.tracking_code = cleaned_data["tracking_code"]
        if not errors:
            locked.save()
    return locked, errors


def apply_primary_image(product: Product, image=None, remove: bool = False) -> None:
    """تصویر اصلی محصول را جایگزین/حذف می‌کند و تصویر بعدی را اصلی می‌کند."""
    if image:
        ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        ProductImage.objects.create(product=product, image=image, is_primary=True, alt=product.name)
    elif remove:
        ProductImage.objects.filter(product=product, is_primary=True).delete()
        first = product.images.first()
        if first:
            first.is_primary = True
            first.save(update_fields=["is_primary"])


def toggle_message_read(message: ContactMessage) -> ContactMessage:
    message.is_read = not message.is_read
    message.save(update_fields=["is_read"])
    return message


def load_site_settings() -> SiteSettings:
    return SiteSettings.load()


# ===========================================================================
# وظایف پس‌زمینه (Celery Taskها این توابع را صدا می‌زنند)
# ===========================================================================
def clear_expired_sessions() -> str:
    """نشست‌های منقضی‌شده را پاک می‌کند."""
    call_command("clearsessions", verbosity=0)
    logger.info("نشست‌های منقضی‌شده پاک شدند")
    return "clearsessions done"
