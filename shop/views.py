import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ExpressionWrapper, F, FloatField, Max, Min, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .cart import Cart, shipping_cost_for
from .forms import CheckoutForm, ContactForm, LoginForm, OrderTrackForm, ProfileForm, RegisterForm
from .models import Brand, Category, Order, OrderItem, Product, Profile
from .payments import PaymentError, get_gateway
from .utils import format_price, jalali_date, to_persian_digits

logger = logging.getLogger(__name__)

User = get_user_model()

SORT_OPTIONS = {
    "newest": "جدیدترین",
    "price_asc": "ارزان‌ترین",
    "price_desc": "گران‌ترین",
    "discount": "بیشترین تخفیف",
}


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _cart_summary(cart, shipping_method=None):
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


def _grant_order_access(request, order):
    codes = list(request.session.get("order_access", []))
    if order.code not in codes:
        codes.append(order.code)
    request.session["order_access"] = codes[-25:]
    request.session["last_order_code"] = order.code


def _can_view_order(request, order):
    if request.user.is_authenticated and (order.user_id == request.user.id or request.user.is_staff):
        return True
    return order.code in request.session.get("order_access", [])


# ---------------------------------------------------------------------------
# صفحه اصلی
# ---------------------------------------------------------------------------
def home(request):
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
    brands = Brand.objects.all()[:8]
    context = {
        "featured_products": featured,
        "new_arrivals": new_arrivals,
        "brands": brands,
        "total_products": products.count(),
        "page_meta": {
            "title": "آب پاک | فروشگاه تخصصی تجهیزات تصفیه آب خانگی و صنعتی",
            "description": "خرید دستگاه تصفیه آب خانگی و صنعتی، فیلترها، ممبران، پمپ و قطعات اصلی با ضمانت اصالت کالا و ارسال به سراسر ایران.",
        },
    }
    return render(request, "shop/home.html", context)


# ---------------------------------------------------------------------------
# فهرست محصولات، دسته‌بندی و جستجو
# ---------------------------------------------------------------------------
def _filtered_products(request):
    products = (
        Product.objects.active()
        .select_related("category", "brand")
        .prefetch_related("images")
    )
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    selected_brands = request.GET.getlist("brand")
    stock_filter = request.GET.get("in_stock", "")
    sort = request.GET.get("sort", "newest")
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

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
    min_value = int("".join(ch for ch in min_price if ch.isdigit()) or 0)
    max_value = int("".join(ch for ch in max_price if ch.isdigit()) or 0)
    if min_value:
        products = products.filter(price__gte=min_value)
    if max_value:
        products = products.filter(price__lte=max_value)
    if sort == "price_asc":
        products = products.order_by("price")
    elif sort == "price_desc":
        products = products.order_by("-price")
    elif sort == "discount":
        discount_ratio = ExpressionWrapper(
            (F("old_price") - F("price")) * 1.0 / F("old_price"), output_field=FloatField()
        )
        products = products.filter(old_price__gt=F("price")).annotate(discount_ratio=discount_ratio).order_by(
            "-discount_ratio"
        )
    else:
        products = products.order_by("-created_at")

    page_obj = Paginator(products, settings.PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))
    categories = Category.objects.filter(is_active=True).annotate(
        count=Count("products", filter=Q(products__is_active=True))
    ).order_by("sort_order", "id")
    brands = Brand.objects.annotate(
        count=Count("products", filter=Q(products__is_active=True))
    ).filter(count__gt=0)
    price_range = Product.objects.active().aggregate(low=Min("price"), high=Max("price"))
    active_category = None
    if category_slug:
        active_category = Category.objects.filter(slug=category_slug, is_active=True).first()
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

    return {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "result_count": page_obj.paginator.count,
        "categories": categories,
        "brands": brands.filter(count__gt=0),
        "active_category": active_category,
        "selected_brands": selected_brands,
        "query": query,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "stock_filter": stock_filter,
        "min_price": min_price,
        "max_price": max_price,
        "min_price_value": price_range["low"] or 0,
        "max_price_value": price_range["high"] or 0,
        "chips": chips,
    }


def catalog(request):
    context = _filtered_products(request)
    context["page_meta"] = {
        "title": "همه محصولات | فروشگاه آب پاک",
        "description": "فهرست کامل دستگاه‌های تصفیه آب، فیلترها، ممبران‌ها، پمپ‌ها و تجهیزات جانبی آب پاک.",
        "canonical_path": "/products/",
    }
    context["page_mode"] = "catalog"
    return render(request, "shop/catalog.html", context)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    request.GET = request.GET.copy()
    request.GET["category"] = category.slug
    context = _filtered_products(request)
    context["page_meta"] = {
        "title": f"{category.name} | فروشگاه آب پاک",
        "description": category.short_description or f"خرید {category.name} با ضمانت اصالت کالا از فروشگاه آب پاک.",
    }
    context["page_mode"] = "category"
    return render(request, "shop/catalog.html", context)


def search(request):
    context = _filtered_products(request)
    query = context["query"]
    context["page_meta"] = {
        "title": f"جستجو: {query} | آب پاک" if query else "جستجوی محصولات | آب پاک",
        "description": "جستجوی محصولات تصفیه آب در فروشگاه آب پاک.",
        "noindex": True,
    }
    context["page_mode"] = "search"
    return render(request, "shop/catalog.html", context)


@require_GET
def search_suggest(request):
    query = request.GET.get("q", "").strip()
    results = []
    if len(query) >= 2:
        products = (
            Product.objects.active()
            .filter(Q(name__icontains=query) | Q(short_description__icontains=query) | Q(category__name__icontains=query))
            .select_related("category")[:6]
        )
        for product in products:
            results.append(
                {
                    "name": product.name,
                    "url": product.get_absolute_url(),
                    "category": product.category.name,
                    "price": format_price(product.price),
                    "in_stock": product.in_stock,
                    "icon": product.category.icon,
                }
            )
    return JsonResponse({"query": query, "results": results})


# ---------------------------------------------------------------------------
# صفحه محصول
# ---------------------------------------------------------------------------
def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category", "brand").prefetch_related("images"),
        slug=slug,
        is_active=True,
    )
    related = (
        Product.objects.active()
        .filter(category=product.category)
        .exclude(id=product.id)
        .select_related("category", "brand")
        .prefetch_related("images")[:4]
    )
    cart = Cart(request)
    context = {
        "product": product,
        "related_products": related,
        "cart_quantity": cart.quantity_of(product),
        "specs": product.specs or [],
        "page_meta": {
            "title": f"{product.name} | آب پاک",
            "description": product.short_description or product.name,
        },
    }
    return render(request, "shop/product_detail.html", context)


# ---------------------------------------------------------------------------
# سبد خرید
# ---------------------------------------------------------------------------
def cart_detail(request):
    cart = Cart(request)
    items = cart.items()
    totals = cart.totals()
    recommended = (
        Product.objects.active()
        .filter(stock__gt=0)
        .exclude(id__in=[item["product"].id for item in items])
        .select_related("category", "brand")
        .prefetch_related("images")[:4]
    )
    return render(
        request,
        "shop/cart.html",
        {
            "cart_items": items,
            "totals": totals,
            "recommended": recommended,
            "page_meta": {"title": "سبد خرید | آب پاک", "noindex": True},
        },
    )


@require_POST
def cart_add(request):
    cart = Cart(request)
    product_id = request.POST.get("product_id")
    quantity_raw = request.POST.get("quantity", "1")
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        quantity = 1
    product = get_object_or_404(Product, id=product_id, is_active=True)
    if not product.in_stock:
        payload = {"ok": False, "message": "این محصول در حال حاضر ناموجود است."}
    else:
        cart.add(product, quantity)
        payload = {
            "ok": True,
            "message": f"«{product.name}» به سبد خرید اضافه شد.",
            "quantity": cart.quantity_of(product),
            **_cart_summary(cart),
        }
    if _is_ajax(request):
        return JsonResponse(payload, status=200 if payload["ok"] else 400)
    if payload["ok"]:
        messages.success(request, payload["message"])
    else:
        messages.error(request, payload["message"])
    if request.POST.get("redirect_to") == "checkout" and payload["ok"]:
        return redirect("shop:checkout")
    return redirect(request.POST.get("next") or "shop:cart")


@require_POST
def cart_update(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get("product_id"), is_active=True)
    try:
        quantity = int(request.POST.get("quantity", "1"))
    except (TypeError, ValueError):
        quantity = 1
    new_quantity = cart.update(product, quantity)
    limited = 0 < product.stock < quantity
    payload = {
        "ok": True,
        "quantity": new_quantity,
        "item_total": product.price * new_quantity,
        "item_total_display": format_price(product.price * new_quantity),
        "limited": limited,
        "stock": product.stock,
        "message": f"حداکثر موجودی این محصول {to_persian_digits(product.stock)} عدد است." if limited else "",
        **_cart_summary(cart),
    }
    if _is_ajax(request):
        return JsonResponse(payload)
    messages.success(request, "سبد خرید بروزرسانی شد.")
    return redirect("shop:cart")


@require_POST
def cart_remove(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get("product_id"))
    cart.remove(product)
    payload = {"ok": True, "message": "محصول از سبد خرید حذف شد.", **_cart_summary(cart)}
    if _is_ajax(request):
        return JsonResponse(payload)
    messages.success(request, payload["message"])
    return redirect("shop:cart")


# ---------------------------------------------------------------------------
# پرداخت آنلاین (درگاه زرین‌پال)
# منطق امنیتی:
#   1) فقط صاحب سفارش/جلسه مجاز است پرداخت را شروع کند.
#   2) بازگشت از درگاه فقط وقتی پذیرفته می‌شود که Authority دقیقاً همان تراکنش
#      ذخیره‌شده روی همین سفارش باشد (جلوگیری از دست‌کاری سفارش دیگر).
#   3) مبلغ همیشه از دیتابیس خوانده می‌شود، نه از پارامترهای مرورگر.
#   4) پرداخت فقط بعد از پاسخ موفق verify درگاه و به‌صورت اتمیک ثبت می‌شود
#      (ایمن در برابر دوبار ارسال شدن callback).
# ---------------------------------------------------------------------------
def _order_for_payment(request, code: str) -> Order:
    """سفارش را با همان کنترل دسترسی صفحه جزئیات برمی‌گرداند."""
    order = get_object_or_404(Order, code=code)
    if not _can_view_order(request, order):
        raise Http404("سفارش یافت نشد.")
    return order


def _payment_redirect(order: Order):
    return redirect("shop:order_detail", code=order.code)


@require_http_methods(["GET", "POST"])
def payment_start(request, code):
    """ساخت تراکنش در درگاه و انتقال کاربر به صفحه پرداخت."""
    order = _order_for_payment(request, code)

    if not order.is_online_payment:
        messages.info(request, "این سفارش برای پرداخت آنلاین ثبت نشده است.")
        return _payment_redirect(order)
    if order.is_paid:
        messages.info(request, "این سفارش قبلاً پرداخت شده است.")
        return _payment_redirect(order)
    if order.status == Order.STATUS_CANCELED:
        messages.error(request, "سفارش لغو شده قابل پرداخت نیست.")
        return _payment_redirect(order)

    gateway = get_gateway()
    if gateway is None:
        messages.error(request, "درگاه پرداخت آنلاین در حال حاضر فعال نیست.")
        return _payment_redirect(order)

    callback_url = request.build_absolute_uri(reverse("shop:payment_callback", args=[order.code]))
    try:
        payment = gateway.request_payment(
            amount_toman=order.total,
            callback_url=callback_url,
            description=f"سفارش {order.code} — {settings.SITE_NAME}",
            mobile=order.phone,
        )
    except PaymentError as exc:
        logger.warning("payment start failed (order=%s): %s", order.code, exc)
        messages.error(request, str(exc))
        return _payment_redirect(order)

    Order.objects.filter(pk=order.pk).update(
        payment_gateway=gateway.slug,
        payment_authority=payment.authority,
    )
    return redirect(payment.payment_url)


def payment_callback(request, code):
    """بازگشت کاربر از درگاه: تأیید سمت سرور و ثبت نتیجه."""
    order = get_object_or_404(Order, code=code)
    authority = (request.GET.get("Authority") or "").strip()
    status = (request.GET.get("Status") or "").strip()

    if not authority or authority != (order.payment_authority or ""):
        logger.warning("payment callback with unknown authority (order=%s)", order.code)
        messages.error(request, "پاسخ درگاه معتبر نیست.")
        return _payment_redirect(order)

    if order.is_paid:
        messages.info(request, "این سفارش قبلاً پرداخت شده است.")
        return _payment_redirect(order)

    if status != "OK":
        logger.info("payment not completed (order=%s, status=%s)", order.code, status)
        messages.error(
            request,
            "پرداخت لغو شد یا ناموفق بود. اگر مبلغی از حساب شما کسر شده باشد، طی ۷۲ ساعت بازگشت داده می‌شود.",
        )
        return _payment_redirect(order)

    gateway = get_gateway()
    if gateway is None:
        messages.error(request, "درگاه پرداخت آنلاین فعال نیست.")
        return _payment_redirect(order)

    try:
        verification = gateway.verify_payment(authority=authority, amount_toman=order.total)
    except PaymentError as exc:
        logger.warning("payment verify error (order=%s): %s", order.code, exc)
        messages.error(request, str(exc))
        return _payment_redirect(order)

    if not verification.verified:
        messages.error(request, "پرداخت تأیید نشد. در صورت کسر مبلغ با پشتیبانی تماس بگیرید.")
        return _payment_redirect(order)

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

    if updated:
        logger.info("order %s paid (ref=%s)", order.code, verification.reference_id)
        messages.success(
            request,
            f"پرداخت با موفقیت انجام شد. کد پیگیری تراکنش: {verification.reference_id}",
        )
    else:
        messages.info(request, "این سفارش قبلاً پرداخت شده است.")
    return _payment_redirect(order)


# ---------------------------------------------------------------------------
# ثبت سفارش
# ---------------------------------------------------------------------------
def checkout(request):
    cart = Cart(request)
    items = cart.items()
    if not items:
        messages.info(request, "سبد خرید شما خالی است. ابتدا محصولی انتخاب کنید.")
        return redirect("shop:catalog")

    initial = {"shipping_method": settings.DEFAULT_SHIPPING_METHOD, "payment_method": "cod"}
    shipping_method = request.POST.get("shipping_method") or settings.DEFAULT_SHIPPING_METHOD

    if request.method == "POST":
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            shipping_method = form.cleaned_data["shipping_method"]
            totals = cart.totals(shipping_method)
            stock_errors = [
                item["product"] for item in items if item["quantity"] > item["product"].stock
            ]
            if stock_errors:
                for product in stock_errors:
                    messages.error(request, f"موجودی «{product.name}» تغییر کرده است. سبد خرید را بروزرسانی کنید.")
                return redirect("shop:cart")
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    full_name=form.cleaned_data["full_name"],
                    phone=form.cleaned_data["phone"],
                    province=form.cleaned_data["province"],
                    city=form.cleaned_data["city"],
                    address=form.cleaned_data["address"],
                    postal_code=form.cleaned_data["postal_code"],
                    note=form.cleaned_data["note"],
                    shipping_method=shipping_method,
                    payment_method=form.cleaned_data["payment_method"],
                    payment_status=(
                        Order.PAYMENT_AWAITING
                        if form.cleaned_data["payment_method"] == "transfer"
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
                if request.user.is_authenticated:
                    profile = getattr(request.user, "profile", None)
                    if profile:
                        profile.phone = form.cleaned_data["phone"]
                        profile.province = form.cleaned_data["province"]
                        profile.city = form.cleaned_data["city"]
                        profile.address = form.cleaned_data["address"]
                        profile.postal_code = form.cleaned_data["postal_code"]
                        profile.save()
                cart.clear()
                _grant_order_access(request, order)
            messages.success(request, f"سفارش شما با کد {order.code} ثبت شد.")
            # سفارش‌های آنلاین مستقیم به درگاه می‌روند؛ بقیه به صفحه سفارش.
            if order.is_online_payment and get_gateway() is not None:
                return redirect("shop:payment_start", code=order.code)
            return redirect("shop:order_detail", code=order.code)
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    else:
        form = CheckoutForm(user=request.user, initial=initial)

    totals = cart.totals(shipping_method)
    return render(
        request,
        "shop/checkout.html",
        {
            "form": form,
            "cart_items": items,
            "totals": totals,
            "selected_shipping": shipping_method,
            "page_meta": {"title": "تکمیل سفارش | آب پاک", "noindex": True},
        },
    )


def order_detail(request, code):
    order = get_object_or_404(Order.objects.prefetch_related("items"), code=code)
    if not _can_view_order(request, order):
        messages.info(request, "برای مشاهده این سفارش، کد سفارش و شماره تماس خود را وارد کنید.")
        return redirect(f"{reverse('shop:track_order')}?code={order.code}")
    return render(
        request,
        "shop/order_detail.html",
        {
            "order": order,
            "items": order.items.all(),
            "is_new": request.session.get("last_order_code") == order.code,
            "page_meta": {"title": f"سفارش {order.code} | آب پاک", "noindex": True},
        },
    )


def track_order(request):
    result = None
    form = OrderTrackForm(request.GET or None)
    if request.method == "POST":
        form = OrderTrackForm(request.POST)
        if form.is_valid():
            order = (
                Order.objects.prefetch_related("items")
                .filter(code__iexact=form.cleaned_data["code"], phone=form.cleaned_data["phone"])
                .first()
            )
            if order:
                _grant_order_access(request, order)
                messages.success(request, "سفارش شما پیدا شد.")
                return redirect("shop:order_detail", code=order.code)
            form.add_error(None, "سفارشی با این کد و شماره تماس یافت نشد. اطلاعات را بررسی کنید.")
    return render(
        request,
        "shop/track_order.html",
        {
            "form": form,
            "result": result,
            "status_choices": Order.STATUS_CHOICES,
            "page_meta": {"title": "پیگیری سفارش | آب پاک", "noindex": True},
        },
    )


# ---------------------------------------------------------------------------
# حساب کاربری
# ---------------------------------------------------------------------------
@login_required
def account(request):
    profile, _ = Profile.objects.get_or_create(user=request.user, defaults={"phone": request.user.username})
    orders = request.user.orders.prefetch_related("items")
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات حساب شما با موفقیت بروزرسانی شد.")
            return redirect("shop:account")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    else:
        form = ProfileForm(instance=profile, user=request.user)
    stats = {
        "orders": orders.count(),
        "in_progress": orders.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_CONFIRMED, Order.STATUS_PROCESSING, Order.STATUS_SHIPPED]
        ).count(),
        "delivered": orders.filter(status=Order.STATUS_DELIVERED).count(),
    }
    return render(
        request,
        "shop/account.html",
        {
            "profile": profile,
            "form": form,
            "orders": orders[:4],
            "stats": stats,
            "page_meta": {"title": "حساب کاربری | آب پاک", "noindex": True},
        },
    )


@login_required
def account_orders(request):
    orders = request.user.orders.prefetch_related("items")
    status_filter = request.GET.get("status", "")
    if status_filter in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status_filter)
    page_obj = Paginator(orders, 8).get_page(request.GET.get("page"))
    return render(
        request,
        "shop/account_orders.html",
        {
            "page_obj": page_obj,
            "orders": page_obj.object_list,
            "status_filter": status_filter,
            "status_choices": Order.STATUS_CHOICES,
            "page_meta": {"title": "سفارش‌های من | آب پاک", "noindex": True},
        },
    )


# ---------------------------------------------------------------------------
# ورود و ثبت‌نام
# ---------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("shop:account")
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = LoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.user)
        messages.success(request, f"{form.user.get_full_name() or 'کاربر'} عزیز، خوش آمدید.")
        if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
            return redirect(next_url)
        return redirect("shop:account")
    return render(
        request,
        "shop/auth.html",
        {
            "login_form": form,
            "register_form": RegisterForm(),
            "active_tab": "login",
            "next_url": next_url,
            "page_meta": {"title": "ورود به حساب | آب پاک", "noindex": True},
        },
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect("shop:account")
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "حساب کاربری شما ساخته شد. خوش آمدید!")
        if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
            return redirect(next_url)
        return redirect("shop:account")
    return render(
        request,
        "shop/auth.html",
        {
            "login_form": LoginForm(request=request),
            "register_form": form,
            "active_tab": "register",
            "next_url": next_url,
            "page_meta": {"title": "ثبت‌نام | آب پاک", "noindex": True},
        },
    )


@require_http_methods(["POST"])
def logout_view(request):
    auth_logout(request)
    messages.success(request, "از حساب کاربری خارج شدید.")
    return redirect("shop:home")


# ---------------------------------------------------------------------------
# صفحات ثابت
# ---------------------------------------------------------------------------
def about(request):
    return render(
        request,
        "shop/about.html",
        {
            "page_meta": {
                "title": "درباره آب پاک | تخصص در تجهیزات تصفیه آب",
                "description": "آب پاک با بیش از یک دهه تجربه در تأمین دستگاه‌های تصفیه آب خانگی و صنعتی، فیلتر و قطعات تخصصی در کنار شماست.",
            }
        },
    )


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "پیام شما ثبت شد. کارشناسان آب پاک در اولین فرصت با شما تماس می‌گیرند.")
        return redirect("shop:contact")
    return render(
        request,
        "shop/contact.html",
        {"form": form, "page_meta": {"title": "تماس با ما | آب پاک", "description": "راه‌های ارتباط با فروشگاه آب پاک و فرم ارسال پیام."}},
    )


FAQ_GROUPS = [
    {
        "title": "خرید و ثبت سفارش",
        "icon": "cart",
        "items": [
            {
                "q": "چطور می‌توانم سفارش خود را ثبت کنم؟",
                "a": "محصول مورد نظر را به سبد خرید اضافه کنید، سپس از صفحه سبد خرید روی «ادامه فرآیند خرید» بزنید و اطلاعات تحویل را تکمیل کنید. پس از ثبت، کد سفارش برای شما نمایش داده می‌شود و از همین سایت قابل پیگیری است.",
            },
            {
                "q": "برای خرید حتماً باید حساب کاربری داشته باشم؟",
                "a": "خیر. ثبت سفارش بدون عضویت هم امکان‌پذیر است. اما با ساخت حساب کاربری می‌توانید سفارش‌های خود را در یک‌جا ببینید و اطلاعات تحویل را برای خریدهای بعدی ذخیره کنید.",
            },
            {
                "q": "آیا امکان خرید عمده یا همکاری با فروشگاه‌ها وجود دارد؟",
                "a": "بله. برای خرید عمده، تجهیزات صنعتی یا همکاری با مجموعه‌ها با شماره پشتیبانی تماس بگیرید یا از فرم تماس با ما درخواست خود را ثبت کنید تا کارشناس فروش با شما هماهنگ کند.",
            },
        ],
    },
    {
        "title": "دستگاه‌های تصفیه آب",
        "icon": "home",
        "items": [
            {
                "q": "دستگاه تصفیه آب خانگی چند مرحله تصفیه دارد؟",
                "a": "دستگاه‌های خانگی معمولاً بین ۵ تا ۸ مرحله تصفیه دارند: رسوب‌گیر، کربن، ممبران اسمز معکوس، پست‌کربن و در مدل‌های پیشرفته فیلتر مینرال، قلیایی‌ساز و UV. تعداد مراحل در صفحه هر محصول به‌طور کامل ذکر شده است.",
            },
            {
                "q": "هر چند وقت یک‌بار فیلترها را تعویض کنم؟",
                "a": "فیلترهای رسوب‌گیر و کربن معمولاً هر ۶ ماه، ممبران هر ۱۸ تا ۲۴ ماه و فیلترهای مینرال و پست‌کربن هر ۱۲ ماه تعویض می‌شوند. این بازه به کیفیت آب ورودی و میزان مصرف بستگی دارد.",
            },
            {
                "q": "تفاوت دستگاه خانگی و صنعتی چیست؟",
                "a": "دستگاه‌های خانگی برای تأمین آب آشامیدنی با ظرفیت روزانه محدود طراحی شده‌اند، در حالی که سیستم‌های صنعتی برای دبی بالا، کارکرد پیوسته و کاربری تجاری یا تولیدی ساخته می‌شوند. انتخاب درست به میزان مصرف روزانه و آنالیز آب شما بستگی دارد.",
            },
            {
                "q": "مشاوره انتخاب دستگاه چگونه است؟",
                "a": "کارشناسان ما با توجه به کیفیت آب منطقه، تعداد نفرات و میزان مصرف، دستگاه مناسب را پیشنهاد می‌دهند. برای دریافت مشاوره رایگان با شماره فروشگاه تماس بگیرید.",
            },
        ],
    },
    {
        "title": "نصب، راه‌اندازی و گارانتی",
        "icon": "shield",
        "items": [
            {
                "q": "نصب دستگاه تصفیه آب چگونه انجام می‌شود؟",
                "a": "دستگاه‌های خانگی زیرسینکی پس از هماهنگی توسط تکنسین نصب می‌شوند. در تهران نصب توسط همکاران ما انجام می‌شود و برای سایر شهرها راهنمای تصویری نصب همراه محصول ارسال می‌گردد.",
            },
            {
                "q": "گارانتی محصولات شامل چه مواردی است؟",
                "a": "گارانتی هر محصول در صفحه آن ذکر شده است و شامل ایرادات فنی و عملکردی دستگاه می‌شود. مصرفی‌هایی مانند فیلتر و کارتریج مشمول گارانتی نیستند، مگر اینکه در زمان تحویل معیوب باشند.",
            },
            {
                "q": "اگر قطعه‌ای در حین ارسال آسیب ببیند چه کنم؟",
                "a": "لطفاً هنگام تحویل، بسته را بررسی کنید و در صورت آسیب، مرسوله را تحویل نگیرید یا حداکثر تا ۴۸ ساعت با پشتیبانی تماس بگیرید تا تعویض انجام شود.",
            },
        ],
    },
    {
        "title": "ارسال و پرداخت",
        "icon": "truck",
        "items": [
            {
                "q": "هزینه ارسال چقدر است؟",
                "a": "برای سفارش‌های بالای ۵ میلیون تومان ارسال با پست پیشتاز رایگان است. برای سایر سفارش‌ها هزینه ارسال در صفحه تکمیل سفارش و پیش از پرداخت به‌طور شفاف نمایش داده می‌شود.",
            },
            {
                "q": "چه روش‌های پرداختی پشتیبانی می‌شود؟",
                "a": "در حال حاضر پرداخت در محل (هنگام تحویل) و انتقال بانکی/کارت به کارت فعال است. پرداخت آنلاین پس از اتصال درگاه بانکی در همین صفحه فعال خواهد شد.",
            },
            {
                "q": "زمان تحویل سفارش چقدر است؟",
                "a": "سفارش‌های تهران با پیک در همان روز یا روز کاری بعد و سایر شهرها با پست پیشتاز بین ۲ تا ۴ روز کاری تحویل داده می‌شوند. کالاهای حجیم ممکن است زمان بیشتری نیاز داشته باشند.",
            },
            {
                "q": "آیا امکان لغو سفارش وجود دارد؟",
                "a": "تا زمانی که سفارش به مرحله ارسال نرسیده باشد، با تماس با پشتیبانی و اعلام کد سفارش قابل لغو است.",
            },
        ],
    },
]


def faq(request):
    return render(
        request,
        "shop/faq.html",
        {
            "faq_groups": FAQ_GROUPS,
            "page_meta": {
                "title": "سوالات متداول تصفیه آب | آب پاک",
                "description": "پاسخ پرتکرارترین سوالات درباره خرید، نصب، گارانتی و ارسال دستگاه‌های تصفیه آب.",
            },
        },
    )


def error_404(request, exception=None):
    return render(
        request,
        "404.html",
        {"page_meta": {"title": "صفحه پیدا نشد | آب پاک", "noindex": True}},
        status=404,
    )

