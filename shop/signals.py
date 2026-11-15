from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache_utils import bump_catalog_version
from .models import Brand, Category, Product, Profile

User = get_user_model()


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance, defaults={"phone": instance.username})


# ---------------------------------------------------------------------------
# کش: هر تغییر در کاتالوگ، کلیدهای مشتق‌شده را بی‌اعتبار می‌کند.
# ---------------------------------------------------------------------------
@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
@receiver(post_save, sender=Brand)
@receiver(post_delete, sender=Brand)
def invalidate_catalog_cache(sender, **kwargs):
    bump_catalog_version()
