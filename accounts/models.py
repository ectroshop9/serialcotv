from django.db import models
from django.contrib.auth.models import User
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
    phone = models.CharField(max_length=15, unique=True)
    token_balance = models.IntegerField(default=0)
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    total_referrals = models.IntegerField(default=0)
    referral_earnings = models.IntegerField(default=0)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
    
    def __str__(self):
        return f"{self.name} ({self.token_balance} tokens)"
    
    def generate_jwt_token(self):
        payload = {
            'customer_id': self.id,
            'exp': datetime.utcnow() + timedelta(days=30),
            'type': 'customer'
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
    
    def spend_tokens(self, amount):
        if self.token_balance >= amount:
            self.token_balance -= amount
            self.save()
            return True
        return False
    
    def add_tokens(self, amount):
        self.token_balance += amount
        self.save()

class Transaction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20)
    amount = models.IntegerField()
    description = models.TextField()
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
    
    def __str__(self):
        return f"{self.customer.name}"

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('firmware', 'سوفتوير جديد'),
        ('schematic', 'مخطط جديد'),
        ('product', 'منتج جديد'),
        ('update', 'تحديث نظام'),
        ('info', 'معلومة'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title