from django.db import models
import random
import string

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
    serial_number = models.CharField(max_length=18, unique=True)
    pin = models.CharField(max_length=4)
    package = models.ForeignKey(SerialPackage, on_delete=models.CASCADE)
    tokens_total = models.IntegerField()
    tokens_used = models.IntegerField(default=0)
    tokens_remaining = models.IntegerField()
    customer = models.ForeignKey('accounts.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_used_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Serial Key"
        verbose_name_plural = "Serial Keys"
    
    def __str__(self):
        return f"{self.serial_number} - {self.tokens_remaining} tokens left"
    
    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = self.generate_serial()
        if not self.pin:
            self.pin = self.generate_pin()
        if not self.tokens_total:
            self.tokens_total = self.package.tokens_limit
        if not self.tokens_remaining:
            self.tokens_remaining = self.tokens_total - self.tokens_used
        if self.tokens_remaining <= 0:
            self.is_active = False
            self.is_used_up = True
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_serial():
        prefix = 'SC'
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choices(chars, k=16))
        return f"{prefix}{code}"
    
    @staticmethod
    def generate_pin():
        return ''.join(random.choices(string.digits, k=4))
    
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
    serial_key = models.ForeignKey(SerialKey, on_delete=models.CASCADE)
    customer = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE)
    file_name = models.CharField(max_length=200)
    file_type = models.CharField(max_length=20)
    tokens_before = models.IntegerField()
    tokens_after = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Serial Usage"
        verbose_name_plural = "Serial Usages"
    
    def __str__(self):
        return f"{self.serial_key.serial_number} - {self.file_name}"