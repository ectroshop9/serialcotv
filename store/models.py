from django.db import models
from accounts.models import Customer

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return self.name


class Product(models.Model):
    PRODUCT_TYPES = [
        ('physical', 'منتج مادي'),
        ('digital', 'منتج رقمي'),
    ]
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    product_type = models.CharField(max_length=10, choices=PRODUCT_TYPES, default='physical')
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
    
    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('confirmed', 'تم التأكيد'),
        ('shipped', 'تم الشحن'),
        ('delivered', 'تم التوصيل'),
        ('cancelled', 'ملغي'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    notes = models.TextField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
    
    def __str__(self):
        return f"Order #{self.id} - {self.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
    
    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Notification

@receiver(post_save, sender=Product)
def notify_new_product(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title='منتج جديد في المتجر',
            description=f'تم إضافة {instance.name} - {instance.price} ر.س',
            notification_type='product'
        )
