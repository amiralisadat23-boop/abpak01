from django import template

from ..utils import format_price, jalali_date, to_persian_digits

register = template.Library()


@register.filter
def price(value):
    """مبلغ با جداکننده هزارگان و ارقام فارسی"""
    return format_price(value)


@register.filter
def fa(value):
    """تبدیل ارقام به فارسی"""
    return to_persian_digits(value)


@register.filter
def jalali(value):
    return jalali_date(value)


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """پارامترهای فعلی را با مقادیر جدید ترکیب و به‌صورت query string برمی‌گرداند."""
    request = context.get("request")
    params = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode() if hasattr(params, "urlencode") else ""


@register.filter
def index(value, key):
    """دسترسی به مقدار یک کلید در دیکشنری"""
    try:
        return value.get(key)
    except AttributeError:
        return None
