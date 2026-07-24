from django.db import models
from django.contrib.auth.models import User
from django.db.models.functions import Coalesce
import jwt
from datetime import datetime, timedelta
from django.conf import settings


class Source(models.Model):
    name = models.CharField(max_length=50)
    prefix = models.CharField(max_length=1, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Source"
        verbose_name_plural = "Sources"
    
    def __str__(self):
        return f"{self.name}"


class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        verbose_name="البريد الإلكتروني"
    )
    phone = models.CharField(max_length=15, unique=True)
    
    # ✅ تحسين: إضافة default=0 وعدم السماح بـ NULL
    token_balance = models.PositiveIntegerField(
        default=0,
        null=False,
        blank=False,
        verbose_name="رصيد التوكنز"
    )
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='customer'
    )
    source = models.ForeignKey(
        Source, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.token_balance} tokens)"
    
    def generate_jwt_token(self):
        """توليد JWT Token للعميل"""
        payload = {
            'customer_id': self.id,
            'email': self.email,
            'name': self.name,
            'exp': datetime.utcnow() + timedelta(days=30),
            'type': 'customer'
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
    
    def spend_tokens(self, amount):
        """
        خصم التوكنز بشكل آمن مع التحقق من الرصيد
        
        Returns:
            bool: True إذا تم الخصم بنجاح
        """
        if self.token_balance >= amount:
            # ✅ استخدام update مع F expression للتحديث الآمن
            Customer.objects.filter(pk=self.pk).update(
                token_balance=Coalesce(models.F('token_balance'), 0) - amount
            )
            self.refresh_from_db()
            return True
        return False
    
    def add_tokens(self, amount):
        """
        إضافة التوكنز بشكل آمن (مانع للـ race conditions)
        
        ✅ استخدام update بدلاً من save() للتحديث الآمن
        """
        Customer.objects.filter(pk=self.pk).update(
            token_balance=Coalesce(models.F('token_balance'), 0) + amount
        )
        self.refresh_from_db()
    
    @classmethod
    def get_or_create_by_email(cls, email, defaults=None):
        """
        البحث عن عميل بالإيميل أو إنشائه إذا لم يكن موجوداً
        
        مفيد لربط السيريال تلقائياً
        """
        if not email:
            return None
            
        customer = cls.objects.filter(email__iexact=email, is_active=True).first()
        
        if not customer and defaults:
            customer = cls.objects.create(
                email=email,
                **defaults
            )
            
        return customer


class Transaction(models.Model):
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20)
    amount = models.IntegerField()
    description = models.TextField()
    source = models.ForeignKey(
        Source, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.transaction_type} ({self.amount})"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('firmware', 'سوفتوير جديد'),
        ('schematic', 'مخطط جديد'),
        ('product', 'منتج جديد'),
        ('update', 'تحديث نظام'),
        ('info', 'معلومة'),
    ]
    
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='notifications'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    notification_type = models.CharField(
        max_length=20, 
        choices=NOTIFICATION_TYPES, 
        default='info'
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
