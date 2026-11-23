from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Category, Product, Redirect, Variant
from .pricing import PricingError, compute_price


@receiver(pre_save, sender=Variant)
def set_variant_price(sender, instance, **kwargs):
    try:
        instance.price = compute_price(instance)
    except PricingError:
        # USD variant without an exchange rate yet: keep the previous price.
        pass


@receiver(pre_save, sender=Product)
def set_search_text(sender, instance, **kwargs):
    from .selectors import normalize_query

    category_name = instance.category.name if instance.category_id else ""
    parts = [instance.title, instance.brand, category_name, *instance.keyword_list]
    instance.search_text = " | ".join(normalize_query(p) for p in parts if p)


@receiver(pre_save, sender=Product)
@receiver(pre_save, sender=Category)
def redirect_on_slug_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).values_list("slug", flat=True).first()
    if old is None or old == instance.slug:
        return
    prefix = "/product/" if sender is Product else "/category/"
    old_path, new_path = f"{prefix}{old}/", f"{prefix}{instance.slug}/"
    # Point older redirects straight at the new address (no chains) and drop loops.
    Redirect.objects.filter(new_path=old_path).update(new_path=new_path)
    Redirect.objects.filter(old_path=new_path).delete()
    Redirect.objects.update_or_create(old_path=old_path, defaults={"new_path": new_path})
