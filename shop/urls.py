from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.catalog, name="catalog"),
    path("category/<str:slug>/", views.category_detail, name="category"),
    path("product/<str:slug>/", views.product_detail, name="product_detail"),
    path("search/", views.search, name="search"),
    path("api/search-suggest/", views.search_suggest, name="search_suggest"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/<str:code>/", views.order_detail, name="order_detail"),
    # پرداخت آنلاین (زرین‌پال): شروع تراکنش و بازگشت از درگاه
    path("orders/<str:code>/pay/", views.payment_start, name="payment_start"),
    path("orders/<str:code>/payment/callback/", views.payment_callback, name="payment_callback"),
    path("track-order/", views.track_order, name="track_order"),
    path("account/", views.account, name="account"),
    path("account/orders/", views.account_orders, name="account_orders"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
]
