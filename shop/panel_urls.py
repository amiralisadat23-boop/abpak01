from django.urls import path

from . import panel

app_name = "panel"

urlpatterns = [
    path("", panel.dashboard, name="dashboard"),
    path("settings/", panel.settings_view, name="settings"),
    path("products/", panel.products_view, name="products"),
    path("products/new/", panel.product_create, name="product_create"),
    path("products/<int:pk>/", panel.product_edit, name="product_edit"),
    path("orders/", panel.orders_view, name="orders"),
    path("orders/<str:code>/", panel.order_edit, name="order_edit"),
    path("messages/", panel.messages_view, name="messages"),
    path("messages/<int:pk>/read/", panel.message_read, name="message_read"),
]
