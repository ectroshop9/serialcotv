
from django.db import models
import random
import string
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "مصدر تسجيل"
        verbose_name_plural = "مصادر التسجيل"
    
    def __str__(self):
        return f"{self.name} ({self.prefix})"

class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    serial = models.CharField(max_length=18, unique=True)
    pin = models.CharField(max_length=4)
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
        null=True,
        blank=True
    )
    
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
    
    def __str__(self):
        return f"{self.name} ({self.phone})"

class Wallet(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)
    balance = models.IntegerField(default=0)
    total_deposited = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.customer.name} - {self.balance}"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('bonus', 'مكافأة تسجيل'),
        ('purchase', 'شراء ملف'),
        ('charge', 'شحن رصيد'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.IntegerField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.customer.name} - {self.amount}"

