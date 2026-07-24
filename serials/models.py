import random
import string
from django.db import models


class SerialPackage(models.Model):
    name = models.CharField(max_length=50)
    tokens_limit = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Serial Package"
        verbose_name_plural = "Serial Packages"

    def __str__(self):
        return f"{self.name} ({self.tokens_limit} tokens)"


class SerialKey(models.Model):
    serial_number = models.CharField(max_length=32, unique=True)
    pin = models.CharField(max_length=8)
    package = models.ForeignKey(SerialPackage, on_delete=models.CASCADE)
    tokens_total = models.IntegerField()
    tokens_used = models.IntegerField(default=0)
    tokens_remaining = models.IntegerField()
    customer = models.ForeignKey(
        'accounts.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    is_used_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    
    # ✅✅✅ حقل ضروري لمنع تكرار الـ Webhook
    payment_id = models.CharField(
        max_length=255,
        unique=True,  # منع التكرار على مستوى قاعدة البيانات
        null=True,
        blank=True,
        db_index=True,  # فهرس للبحث السريع
        verbose_name="Payment ID (Chargily)"
    )

    class Meta:
        verbose_name = "Serial Key"
        verbose_name_plural = "Serial Keys"
        indexes = [
            models.Index(fields=['serial_number', 'pin']),  # فهرس مركب لتحسين أداء البحث
        ]

    def __str__(self):
        return f"{self.serial_number} - {self.tokens_remaining} tokens left"

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = self.generate_serial()
        if not self.pin:
            self.pin = self.generate_pin()
        if self.tokens_total is None:
            self.tokens_total = self.package.tokens_limit
        if self.tokens_remaining is None:
            self.tokens_remaining = self.tokens_total - self.tokens_used

        if self.tokens_remaining <= 0:
            self.is_active = False
            self.is_used_up = True

        super().save(*args, **kwargs)

    @staticmethod
    def generate_serial():
        prefix = 'SC'
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choices(chars, k=14))
        return f"{prefix}{code}"

    @staticmethod
    def generate_pin():
        # 🎯 يضمن دائماً 4 أرقام بين 1000 و 9999 لا تبدأ بصفر
        return str(random.randint(1000, 9999))

    def use_tokens(self, amount):
        if self.tokens_remaining >= amount:
            self.tokens_used += amount
            self.tokens_remaining -= amount
            if self.tokens_remaining <= 0:
                self.is_active = False
                self.is_used_up = True
            self.save()
            return True
        return False


class SerialUsage(models.Model):
    serial_key = models.ForeignKey(
        SerialKey, 
        on_delete=models.CASCADE,
        related_name='usages'  # ✅ يسمح بـ serial_key.usages.all()
    )
    customer = models.ForeignKey(
        'accounts.Customer',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='serial_usages'  # ✅ يسمح بـ customer.serial_usages.all()
    )
    file_name = models.CharField(max_length=200)
    file_type = models.CharField(max_length=20, default='unknown')  # ✅ قيمة افتراضية
    tokens_before = models.IntegerField()
    tokens_after = models.IntegerField()
    tokens_used = models.IntegerField(default=1)  # ✅ عدد التوكنز المستخدمة
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Serial Usage"
        verbose_name_plural = "Serial Usages"
        ordering = ['-created_at']  # ✅ ترتيب افتراضي من الأحدث للأقدم

    def __str__(self):
        return f"{self.serial_key.serial_number} - {self.file_name}"

    def save(self, *args, **kwargs):
        # ✅ حساب عدد التوكنز المستخدمة تلقائياً
        if not self.tokens_used:
            self.tokens_used = self.tokens_before - self.tokens_after
        super().save(*args, **kwargs)
