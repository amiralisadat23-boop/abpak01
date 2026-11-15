from django.conf import settings


class StaticCacheMiddleware:
    """کش مرورگر برای فایل‌های استاتیک و تصاویر در حالت توسعه/پیش‌نمایش.

    در استقرار واقعی معمولاً Nginx این هدرها را می‌دهد؛ این میان‌افزار
    مطمئن می‌شود پیش‌نمایش Django هم فایل‌های تکراری را دوباره دانلود نکند.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.static_prefix = "/" + settings.STATIC_URL.lstrip("/")
        self.media_prefix = "/" + settings.MEDIA_URL.lstrip("/")

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 200 and request.path.startswith(
            (self.static_prefix, self.media_prefix)
        ):
            response["Cache-Control"] = "public, max-age=2592000"
        return response
