from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Notification

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


class TVModel(models.Model):
    brand = models.ForeignKey(TVBrand, on_delete=models.CASCADE)
    model_number = models.CharField(max_length=100)
    chassis = models.CharField(max_length=100, null=True, blank=True)
    screen_size = models.CharField(max_length=20, null=True, blank=True)
    year = models.CharField(max_length=4, null=True, blank=True)
    image = models.ImageField(upload_to='models/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "TV Model"
        verbose_name_plural = "TV Models"
        unique_together = ['brand', 'model_number']
    
    def __str__(self):
        return f"{self.brand.name} - {self.model_number}"


class Firmware(models.Model):
    model = models.ForeignKey(TVModel, on_delete=models.CASCADE)
    version = models.CharField(max_length=50)
    file = models.FileField(upload_to='firmware/', null=True, blank=True)
    file_url = models.URLField(max_length=500, null=True, blank=True)
    cloud_url = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    downloads_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Firmware"
        verbose_name_plural = "Firmwares"
    
    def __str__(self):
        return f"{self.model} - v{self.version}"


class Schematic(models.Model):
    SCHEMATIC_TYPES = [
        ('power_supply', 'Power Supply'),
        ('main_board', 'Main Board'),
        ('t_con', 'T-Con'),
        ('other', 'Other'),
    ]
    
    model = models.ForeignKey(TVModel, on_delete=models.CASCADE)
    schematic_type = models.CharField(max_length=20, choices=SCHEMATIC_TYPES)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='schematics/', null=True, blank=True)
    file_url = models.URLField(max_length=500, null=True, blank=True)
    cloud_url = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    downloads_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Schematic"
        verbose_name_plural = "Schematics"
    
    def __str__(self):
        return f"{self.model} - {self.title}"


# ==================== Signals ====================
@receiver(post_save, sender=Firmware)
def notify_new_firmware(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title='سوفتوير جديد',
            description=f'تم إضافة {instance.model} - v{instance.version}',
            notification_type='firmware'
        )

@receiver(post_save, sender=Schematic)
def notify_new_schematic(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title='مخطط جديد',
            description=f'تم إضافة {instance.model} - {instance.title}',
            notification_type='schematic'
        )