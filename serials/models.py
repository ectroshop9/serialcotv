from django.db import models
import random
import string

class SerialPackage(models.Model):
    name = models.CharField(max_length=50)
    downloads_limit = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Serial Package"
        verbose_name_plural = "Serial Packages"
    
    def __str__(self):
        return f"{self.name} ({self.downloads_limit} downloads)"


class SerialKey(models.Model):
    serial_number = models.CharField(max_length=18, unique=True)
    pin = models.CharField(max_length=4)
    package = models.ForeignKey(SerialPackage, on_delete=models.CASCADE)
    downloads_total = models.IntegerField()
    downloads_used = models.IntegerField(default=0)
    downloads_remaining = models.IntegerField()
    customer = models.ForeignKey('accounts.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_used_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Serial Key"
        verbose_name_plural = "Serial Keys"
    
    def __str__(self):
        return f"{self.serial_number} - {self.downloads_remaining} left"
    
    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = self.generate_serial()
        if not self.pin:
            self.pin = self.generate_pin()
        if not self.downloads_total:
            self.downloads_total = self.package.downloads_limit
        if not self.downloads_remaining:
            self.downloads_remaining = self.downloads_total - self.downloads_used
        if self.downloads_remaining <= 0:
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
    
    def use_download(self):
        if self.downloads_remaining > 0:
            self.downloads_used += 1
            self.downloads_remaining -= 1
            if self.downloads_remaining <= 0:
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
    downloads_before = models.IntegerField()
    downloads_after = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Serial Usage"
        verbose_name_plural = "Serial Usages"
    
    def __str__(self):
        return f"{self.serial_key.serial_number} - {self.file_name}"