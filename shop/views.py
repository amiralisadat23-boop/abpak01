"""ویوهای فروشگاه آب پاک.

این ماژول فقط لایه HTTP است: دریافت درخواست، اعتبارسنجی فرم، فراخوانی سرویس
مناسب (``shop.services``) و برگرداندن پاسخ. هیچ منطق تجاری/کوئری در اینجا نیست.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import services
from .cart import Cart
from .forms import CheckoutForm, ContactForm, LoginForm, OrderTrackForm, ProfileForm, RegisterForm
from .models import Category, Order, Product

logger = logging.getLogger(__name__)

User = get_user_model()


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


# ---------------------------------------------------------------------------
# صفحه اصلی
# ---------------------------------------------------------------------------
def home(request):
    context = services.get_home_context()
    context["page_meta"] = {
        "title": "آب پاک | فروشگاه تخصصی تجهیزات تصفیه آب خانگی و صنعتی",
        "description": "خرید دستگاه تصفیه آب خانگی و صنعتی، فیلترها، ممبران، پمپ و قطعات اصلی با ضمانت اصالت کالا و ارسال به سراسر ایران.",
    }
    return render(request, "shop/home.html", context)


# ---------------------------------------------------------------------------
# فهرست محصولات، دسته‌بندی و جستجو
# ---------------------------------------------------------------------------
def catalog(request):
    context = services.get_catalog_context(request.GET)
    context["page_meta"] = {
        "title": "همه محصولات | فروشگاه آب پاک",
        "description": "فهرست کامل دستگاه‌های تصفیه آب، فیلترها، ممبران‌ها، پمپ‌ها و تجهیزات جانبی آب پاک.",
        "canonical_path": "/products/",
    }
    context["page_mode"] = "catalog"
    return render(request, "shop/catalog.html", context)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    params = request.GET.copy()
    params["category"] = category.slug
    context = services.get_catalog_context(params)
    context["page_meta"] = {
        "title": f"{category.name} | فروشگاه آب پاک",
        "description": category.short_description or f"خرید {category.name} با ضمانت اصالت کالا از فروشگاه آب پاک.",
    }
    context["page_mode"] = "category"
    return render(request, "shop/catalog.html", context)


def search(request):
    context = services.get_catalog_context(request.GET)
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
    return JsonResponse({"query": query, "results": services.search_suggestions(query)})


# ---------------------------------------------------------------------------
# صفحه محصول
# ---------------------------------------------------------------------------
def product_detail(request, slug):
    context = services.get_product_detail_context(slug, cart=Cart(request))
    if context is None:
        raise Http404("محصول یافت نشد.")
    product = context["product"]
    context["page_meta"] = {
        "title": f"{product.name} | آب پاک",
        "description": product.short_description or product.name,
    }
    return render(request, "shop/product_detail.html", context)


# ---------------------------------------------------------------------------
# سبد خرید
# ---------------------------------------------------------------------------
def cart_detail(request):
    return render(
        request,
        "shop/cart.html",
        {
            **services.get_cart_context(Cart(request)),
            "page_meta": {"title": "سبد خرید | آب پاک", "noindex": True},
        },
    )


@require_POST
def cart_add(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get("product_id"), is_active=True)
    payload = services.add_product_to_cart(cart, product, request.POST.get("quantity", "1"))
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
    payload = services.update_cart_item(cart, product, request.POST.get("quantity", "1"))
    if _is_ajax(request):
        return JsonResponse(payload)
    messages.success(request, "سبد خرید بروزرسانی شد.")
    return redirect("shop:cart")


@require_POST
def cart_remove(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get("product_id"))
    payload = services.remove_cart_item(cart, product)
    if _is_ajax(request):
        return JsonResponse(payload)
    messages.success(request, payload["message"])
    return redirect("shop:cart")


# ---------------------------------------------------------------------------
# پرداخت آنلاین (درگاه زرین‌پال)
# کنترل دسترسی سفارش، اعتبارسنجی Authority و ثبت اتمیک پرداخت در services است.
# ---------------------------------------------------------------------------
def _order_for_payment(request, code: str) -> Order:
    order = get_object_or_404(Order, code=code)
    if not services.can_view_order(request.user, request.session, order):
        raise Http404("سفارش یافت نشد.")
    return order


def _payment_redirect(order: Order):
    return redirect("shop:order_detail", code=order.code)


@require_http_methods(["GET", "POST"])
def payment_start(request, code):
    """ساخت تراکنش در درگاه و انتقال کاربر به صفحه پرداخت."""
    order = _order_for_payment(request, code)
    callback_url = request.build_absolute_uri(reverse("shop:payment_callback", args=[order.code]))
    result = services.start_online_payment(order, callback_url)
    if not result.ok:
        getattr(messages, result.level, messages.info)(request, result.message)
        return _payment_redirect(order)
    return redirect(result.redirect_url)


def payment_callback(request, code):
    """بازگشت کاربر از درگاه: تأیید سمت سرور و ثبت نتیجه."""
    order = get_object_or_404(Order, code=code)
    result = services.handle_payment_callback(
        order,
        authority=(request.GET.get("Authority") or "").strip(),
        status=(request.GET.get("Status") or "").strip(),
    )
    getattr(messages, result.level, messages.info)(request, result.message)
    return _payment_redirect(order)


# ---------------------------------------------------------------------------
# ثبت سفارش
# ---------------------------------------------------------------------------
def checkout(request):
    cart = Cart(request)
    if not cart.items():
        messages.info(request, "سبد خرید شما خالی است. ابتدا محصولی انتخاب کنید.")
        return redirect("shop:catalog")

    initial = {"shipping_method": settings.DEFAULT_SHIPPING_METHOD, "payment_method": "cod"}
    shipping_method = request.POST.get("shipping_method") or settings.DEFAULT_SHIPPING_METHOD

    if request.method == "POST":
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            shipping_method = form.cleaned_data["shipping_method"]
            order, errors = services.place_order(
                request.user, form.cleaned_data, cart, shipping_method
            )
            if errors:
                for error in errors:
                    messages.error(request, error)
                return redirect("shop:cart")
            messages.success(request, f"سفارش شما با کد {order.code} ثبت شد.")
            services.grant_order_access(request.session, order)
            return redirect(services.order_redirect_name(order), code=order.code)
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    else:
        form = CheckoutForm(user=request.user, initial=initial)

    return render(
        request,
        "shop/checkout.html",
        {
            "form": form,
            "cart_items": cart.items(),
            "totals": cart.totals(shipping_method),
            "selected_shipping": shipping_method,
            "page_meta": {"title": "تکمیل سفارش | آب پاک", "noindex": True},
        },
    )


def order_detail(request, code):
    order = get_object_or_404(Order.objects.prefetch_related("items"), code=code)
    if not services.can_view_order(request.user, request.session, order):
        messages.info(request, "برای مشاهده این سفارش، کد سفارش و شماره تماس خود را وارد کنید.")
        return redirect(f"{reverse('shop:track_order')}?code={order.code}")
    return render(
        request,
        "shop/order_detail.html",
        {
            "order": order,
            "items": order.items.all(),
            "is_new": services.is_new_order(request.session, order),
            "page_meta": {"title": f"سفارش {order.code} | آب پاک", "noindex": True},
        },
    )


def track_order(request):
    form = OrderTrackForm(request.GET or None)
    if request.method == "POST":
        form = OrderTrackForm(request.POST)
        if form.is_valid():
            order = services.find_order_for_tracking(
                form.cleaned_data["code"], form.cleaned_data["phone"]
            )
            if order:
                services.grant_order_access(request.session, order)
                messages.success(request, "سفارش شما پیدا شد.")
                return redirect("shop:order_detail", code=order.code)
            form.add_error(None, "سفارشی با این کد و شماره تماس یافت نشد. اطلاعات را بررسی کنید.")
    return render(
        request,
        "shop/track_order.html",
        {
            "form": form,
            "result": None,
            "status_choices": Order.STATUS_CHOICES,
            "page_meta": {"title": "پیگیری سفارش | آب پاک", "noindex": True},
        },
    )


# ---------------------------------------------------------------------------
# حساب کاربری
# ---------------------------------------------------------------------------
@login_required
def account(request):
    profile = services.get_or_create_profile(request.user)
    orders = services.get_user_orders(request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات حساب شما با موفقیت بروزرسانی شد.")
            return redirect("shop:account")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    else:
        form = ProfileForm(instance=profile, user=request.user)
    return render(
        request,
        "shop/account.html",
        {
            "profile": profile,
            "form": form,
            "orders": orders[:4],
            "stats": services.get_order_status_stats(orders),
            "page_meta": {"title": "حساب کاربری | آب پاک", "noindex": True},
        },
    )


@login_required
def account_orders(request):
    status_filter = request.GET.get("status", "")
    page_obj = services.paginate_orders(
        services.get_user_orders(request.user), status_filter, request.GET.get("page")
    )
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
        services.create_contact_message(form.cleaned_data)
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
