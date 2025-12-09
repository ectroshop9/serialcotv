from django.db import models
import random
import string
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User  # ⭐ Django User العادي
import jwt
from datetime import datetime, timedelta
from django.conf import settings

class Source(models.Model):
    SOURCE_PREFIXES = {
        'T': 'تليجرام', 'S': 'المتجر', 'M': 'مسنجر',
        'W': 'واتساب', 'A': 'إداري', 'U': 'غير معروف'
    }
    
    name = models.CharField(max_length=50)
    prefix = models.CharField(max_length=1, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    bot_username = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "مصدر تسجيل"
        verbose_name_plural = "مصادر التسجيل"
    
    def __str__(self):
        return f"{self.get_prefix_display()} - {self.name}"

class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    serial = models.CharField(max_length=18, unique=True)
    pin = models.CharField(max_length=4)
    
    # ⭐ ربط مع Django User العادي
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
        null=True,
        blank=True
    )
    
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    referrer = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    referred_by_code = models.CharField(max_length=20, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_trial_active = models.BooleanField(default=True)
    trial_expires = models.DateTimeField(null=True, blank=True)
    
    total_referrals = models.IntegerField(default=0)
    referral_earnings = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
    
    def __str__(self):
        return f"{self.name} ({self.phone})"
    
    def generate_jwt_token(self):
        """توليد JWT token"""
        payload = {
            'customer_id': self.id,
            'serial': self.serial,
            'phone': self.phone,
            'user_id': self.user.id if self.user else None,
            'exp': datetime.utcnow() + timedelta(days=30),
            'iat': datetime.utcnow(),
            'type': 'customer'
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
    
    @classmethod
    def get_customer_from_token(cls, token):
        """استخراج العميل من JWT token"""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
            customer_id = payload.get('customer_id')
            if customer_id:
                return cls.objects.get(id=customer_id, is_active=True)
        except:
            return None

class Wallet(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='wallet')
    balance = models.IntegerField(default=0)
    total_deposited = models.IntegerField(default=0)
    total_spent = models.IntegerField(default=0)
    referral_earnings = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.customer.name} - {self.balance}"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('bonus', 'مكافأة تسجيل'),
        ('purchase', 'شراء ملف'),
        ('charge', 'شحن رصيد'),
        ('referral', 'مكافأة إحالة'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.IntegerField()
    description = models.TextField()
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.customer.name} - {self.amount}"

# ⭐ الإشارات الأساسية
@receiver(post_save, sender=Customer)
def create_customer_wallet(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.create(customer=instance, balance=150, total_deposited=150)
        Transaction.objects.create(
            customer=instance,
            transaction_type='bonus',
            amount=150,
            description='مكافأة التسجيل',
            source=instance.source
        )
