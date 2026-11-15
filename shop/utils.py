"""ابزارهای کمکی فارسی‌سازی اعداد و اعتبارسنجی"""
import re

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
THOUSANDS_SEPARATOR = "٬"


def to_persian_digits(value) -> str:
    text = str(value)
    for index, digit in enumerate("0123456789"):
        text = text.replace(digit, PERSIAN_DIGITS[index])
    return text


def normalize_digits(value: str) -> str:
    """ارقام فارسی/عربی را به لاتین تبدیل می‌کند."""
    if not value:
        return value
    for index, digit in enumerate(PERSIAN_DIGITS):
        value = value.replace(digit, str(index))
    for index, digit in enumerate(ARABIC_DIGITS):
        value = value.replace(digit, str(index))
    return value


def format_price(value) -> str:
    """مبلغ را با جداکننده هزارگان و ارقام فارسی برمی‌گرداند."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "۰"
    grouped = f"{number:,}".replace(",", THOUSANDS_SEPARATOR)
    return to_persian_digits(grouped)


def format_number(value) -> str:
    return to_persian_digits(f"{int(value or 0):,}".replace(",", THOUSANDS_SEPARATOR))


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", normalize_digits(value or ""))


def is_valid_mobile(value: str) -> bool:
    return bool(re.fullmatch(r"09\d{9}", digits_only(value)))


def is_valid_postal_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{10}", digits_only(value)))


def jalali_date(value) -> str:
    """تاریخ شمسی خوانا بدون وابستگی خارجی."""
    if not value:
        return ""
    try:
        import datetime

        if hasattr(value, "date"):
            value = value.date()
        # الگوریتم تبدیل میلادی به جلالی
        gy, gm, gd = value.year, value.month, value.day
        g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        if gy > 1600:
            jy = 979
            gy -= 1600
        else:
            jy = 0
            gy -= 621
        gy2 = gy + 1
        days = (
            365 * gy
            + (gy2 + 3) // 4
            - (gy2 + 99) // 100
            + (gy2 + 399) // 400
            - 80
            + gd
            + g_d_m[gm - 1]
        )
        if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
            days += 1
        jy += 33 * (days // 12053)
        days %= 12053
        jy += 4 * (days // 1461)
        days %= 1461
        if days > 365:
            jy += (days - 1) // 365
            days = (days - 1) % 365
        if days < 186:
            jm = 1 + days // 31
            jd = 1 + days % 31
        else:
            jm = 7 + (days - 186) // 30
            jd = 1 + (days - 186) % 30
        months = [
            "فروردین",
            "اردیبهشت",
            "خرداد",
            "تیر",
            "مرداد",
            "شهریور",
            "مهر",
            "آبان",
            "آذر",
            "دی",
            "بهمن",
            "اسفند",
        ]
        return f"{to_persian_digits(jd)} {months[jm - 1]} {to_persian_digits(jy)}"
    except Exception:
        return ""
