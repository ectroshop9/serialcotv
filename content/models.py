from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Notification
import secrets
from datetime import timedelta
from django.utils import timezone


class TVBrand(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='brands/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "TV Brand"
        verbose_name_plural = "TV Brands"
    
    def __str__(self):
        return self.name


class Firmware(models.Model):
    brand = models.ForeignKey(TVBrand, on_delete=models.CASCADE)
    model_number = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    file = models.FileField(upload_to='firmware/', null=True, blank=True)
    file_url = models.URLField(max_length=500, null=True, blank=True)
    cloud_url = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    token_cost = models.IntegerField(default=500)
    downloads_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Firmware"
        verbose_name_plural = "Firmwares"
    
    def __str__(self):
        return f"{self.brand.name} - {self.model_number} - v{self.version}"


class Schematic(models.Model):
    SCHEMATIC_TYPES = [
        ('power_supply', 'Power Supply'),
        ('main_board', 'Main Board'),
        ('t_con', 'T-Con'),
        ('other', 'Other'),
    ]
    
    brand = models.ForeignKey(TVBrand, on_delete=models.CASCADE)
    model_number = models.CharField(max_length=100)
    schematic_type = models.CharField(max_length=20, choices=SCHEMATIC_TYPES)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='schematics/', null=True, blank=True)
    file_url = models.URLField(max_length=500, null=True, blank=True)
    cloud_url = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    token_cost = models.IntegerField(default=300)
    downloads_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Schematic"
        verbose_name_plural = "Schematics"
    
    def __str__(self):
        return f"{self.brand.name} - {self.model_number} - {self.title}"


class DownloadToken(models.Model):
    token = models.CharField(max_length=64, unique=True)
    file_url = models.URLField(max_length=500)
    file_name = models.CharField(max_length=200)
    customer = models.ForeignKey('accounts.Customer', on_delete=models.CASCADE, null=True, blank=True)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()
    
    @staticmethod
    def generate(file_url, file_name, customer=None):
        token = secrets.token_urlsafe(32)
        return DownloadToken.objects.create(
            token=token,
            file_url=file_url,
            file_name=file_name,
            customer=customer,
            expires_at=timezone.now() + timedelta(minutes=15)
        )
    
    def __str__(self):
        return f"{self.file_name} - {'Used' if self.used else 'Valid'}"


# ==================== Signals ====================
@receiver(post_save, sender=Firmware)
def notify_new_firmware(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title='سوفتوير جديد',
            description=f'تم إضافة {instance.brand.name} - {instance.model_number}',
            notification_type='firmware'
        )

@receiver(post_save, sender=Schematic)
def notify_new_schematic(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title='مخطط جديد',
            description=f'تم إضافة {instance.brand.name} - {instance.title}',
            notification_type='schematic'
        )