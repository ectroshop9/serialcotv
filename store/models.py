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


class Wilaya(models.Model):
    wilaya_id = models.IntegerField(unique=True)
    name_ar = models.CharField(max_length=50)
    name_fr = models.CharField(max_length=50)
    has_stopdesk = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Wilaya"
        verbose_name_plural = "Wilayas"
        ordering = ['wilaya_id']
    
    def __str__(self):
        return f"{self.wilaya_id} - {self.name_ar}"


class ShippingFee(models.Model):
    SERVICE_TYPES = [
        ('livraison', 'توصيل'),
        ('recouvrement', 'تحصيل'),
        ('retour', 'إرجاع'),
    ]
    
    wilaya = models.ForeignKey(Wilaya, on_delete=models.CASCADE)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)
    tarif_domicile = models.DecimalField(max_digits=10, decimal_places=2)
    tarif_stopdesk = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Shipping Fee"
        verbose_name_plural = "Shipping Fees"
        unique_together = ['wilaya', 'service_type']
    
    def __str__(self):
        return f"{self.wilaya.name_ar} - {self.service_type}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('confirmed', 'تم التأكيد'),
        ('shipped', 'تم الشحن'),
        ('delivered', 'تم التوصيل'),
        ('cancelled', 'ملغي'),
    ]
    
    SHIPPING_TYPE = [
        ('domicile', 'توصيل منزلي'),
        ('stopdesk', 'مكتب التوقف'),
    ]
    
    PAYMENT_METHOD = [
        ('cod', 'الدفع عند الاستلام'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    wilaya = models.ForeignKey(Wilaya, on_delete=models.SET_NULL, null=True)
    address = models.TextField()
    notes = models.TextField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_type = models.CharField(max_length=10, choices=SHIPPING_TYPE, default='domicile')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD, default='cod')
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


class EcotrackShipment(models.Model):
    SHIPMENT_STATUS = [
        ('created', 'تم الإنشاء'),
        ('pickup', 'قيد الاستلام'),
        ('in_transit', 'في الطريق'),
        ('delivered', 'تم التوصيل'),
        ('returned', 'مرتجع'),
        ('cancelled', 'ملغي'),
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='ecotrack_shipment')
    ecotrack_id = models.CharField(max_length=50, null=True, blank=True)
    tracking_number = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=SHIPMENT_STATUS, default='created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ecotrack Shipment"
        verbose_name_plural = "Ecotrack Shipments"
    
    def __str__(self):
        return f"Shipment #{self.ecotrack_id} - Order #{self.order.id}"


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

# Signal لإرسال الطلب تلقائياً إلى ECOTRACK
@receiver(post_save, sender=Order)
def send_order_to_ecotrack(sender, instance, created, **kwargs):
    if created and instance.payment_method == 'cod':
        from .services.ecotrack_service import EcotrackService
        result = EcotrackService.create_order(instance)
        
        if result.get('success'):
            instance.status = 'confirmed'
            instance.save(update_fields=['status'])