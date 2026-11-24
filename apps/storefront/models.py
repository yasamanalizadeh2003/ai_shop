from django.db import models


class HomeBanner(models.Model):
    STYLES = [
        ("navy", "سرمه‌ای"),
        ("midnight", "سرمه‌ای تیره"),
    ]

    title = models.CharField("تیتر", max_length=80)
    highlight = models.CharField("خط دوم (رنگ روشن)", max_length=80, blank=True)
    badge = models.CharField("برچسب کوچک بالا", max_length=60, blank=True)
    button_text = models.CharField("متن دکمه", max_length=30, default="مشاهده و خرید")
    link = models.CharField("لینک", max_length=300, help_text="مثلاً ‎/product/اشتراک-جمینای/‎")
    image = models.ImageField("تصویر (اختیاری)", upload_to="banners/", blank=True,
                              help_text="اگر تصویر بگذارید، به‌جای پس‌زمینه رنگی نمایش داده می‌شود. نسبت پیشنهادی ۴ به ۱.")
    style = models.CharField("رنگ پس‌زمینه", max_length=10, choices=STYLES, default="navy")
    sort_order = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "بنر صفحه اصلی"
        verbose_name_plural = "بنرهای صفحه اصلی"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title
