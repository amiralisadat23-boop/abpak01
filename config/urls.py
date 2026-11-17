import mimetypes

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

# ایمیج‌های slim لینوکس جدول MIME کامل ندارند؛ بدون این خط webp با
# application/octet-stream سرو می‌شد و با nosniff در مرورگر بلاک می‌شد.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("font/woff2", ".woff2")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", include("shop.panel_urls")),
    path("", include("shop.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")
elif getattr(settings, "SERVE_MEDIA", False):
    # پروداکشن بدون پروکسی/سرور مجزا: فایل‌های آپلودی با همان ویوی امن جنگو
    # سرو می‌شوند (جلوگیری از path traversal و بدون فهرست پوشه‌ها).
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            static_serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]

handler404 = "shop.views.error_404"
