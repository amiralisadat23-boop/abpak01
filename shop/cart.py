"""سبد خرید مبتنی بر Session"""
from django.conf import settings

from .models import Product

CART_SESSION_KEY = "cart"


def shipping_cost_for(subtotal: int, method: str = None) -> tuple[int, int]:
    """هزینه ارسال و سقف ارسال رایگان را برمی‌گرداند."""
    method = method or settings.DEFAULT_SHIPPING_METHOD
    config = settings.SHIPPING_METHODS.get(method, settings.SHIPPING_METHODS[settings.DEFAULT_SHIPPING_METHOD])
    cost = config["cost"]
    threshold = settings.FREE_SHIPPING_THRESHOLD
    if method == settings.DEFAULT_SHIPPING_METHOD and subtotal >= threshold:
        cost = 0
    return cost, threshold


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if not isinstance(cart, dict):
            cart = {}
            self.session[CART_SESSION_KEY] = cart
        self.cart = cart

    # ------------------------------------------------------------------ utils
    def _save(self):
        self.session[CART_SESSION_KEY] = self.cart
        self.session.modified = True

    def _available(self, product) -> int:
        return max(0, int(product.stock))

    # ------------------------------------------------------------------ mutate
    def add(self, product: Product, quantity: int = 1, replace: bool = False) -> int:
        """محصول را اضافه می‌کند و تعداد نهایی را برمی‌گرداند."""
        quantity = max(1, int(quantity))
        key = str(product.id)
        limit = self._available(product)
        if limit == 0:
            return 0
        current = self.cart.get(key, {}).get("quantity", 0)
        new_quantity = quantity if replace else current + quantity
        new_quantity = min(new_quantity, limit)
        self.cart[key] = {"quantity": new_quantity}
        self._save()
        return new_quantity

    def update(self, product: Product, quantity: int) -> int:
        quantity = int(quantity)
        key = str(product.id)
        if quantity <= 0:
            self.remove(product)
            return 0
        quantity = min(quantity, self._available(product))
        if quantity <= 0:
            self.remove(product)
            return 0
        self.cart[key] = {"quantity": quantity}
        self._save()
        return quantity

    def remove(self, product_or_id) -> None:
        key = product_or_id if isinstance(product_or_id, str) else str(product_or_id.id)
        if key in self.cart:
            del self.cart[key]
            self._save()

    def clear(self) -> None:
        self.cart = {}
        self._save()

    # ------------------------------------------------------------------ read
    def __len__(self) -> int:
        return sum(item.get("quantity", 0) for item in self.cart.values())

    def __contains__(self, product) -> bool:
        return str(product.id) in self.cart

    def quantity_of(self, product) -> int:
        return self.cart.get(str(product.id), {}).get("quantity", 0)

    def __iter__(self):
        products = (
            Product.objects.filter(id__in=self.cart.keys(), is_active=True)
            .select_related("category", "brand")
            .prefetch_related("images")
        )
        mapping = {str(product.id): product for product in products}
        for key, item in list(self.cart.items()):
            product = mapping.get(key)
            if product is None:
                self.remove(key)
                continue
            quantity = min(int(item.get("quantity", 0)), max(product.stock, 0))
            if quantity <= 0:
                self.remove(key)
                continue
            yield {
                "product": product,
                "quantity": quantity,
                "unit_price": product.price,
                "total_price": product.price * quantity,
            }

    def items(self) -> list:
        return list(self)

    def subtotal(self) -> int:
        return sum(item["total_price"] for item in self)

    def totals(self, shipping_method: str = None) -> dict:
        subtotal = self.subtotal()
        cost, threshold = shipping_cost_for(subtotal, shipping_method)
        return {
            "subtotal": subtotal,
            "shipping": cost,
            "shipping_threshold": threshold,
            "free_shipping_remaining": max(0, threshold - subtotal),
            "total": subtotal + cost,
            "count": len(self),
            "unique_count": len(self.cart),
        }
