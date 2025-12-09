from django.db import models
from django.contrib.auth.models import User
import jwt
from datetime import datetime, timedelta
from django.conf import settings

# ⭐⭐ تعريف Source أولاً ⭐⭐
class Source(models.Model):
    name = models.CharField(max_length=50)
    prefix = models.CharField(max_length=1, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "مصدر"
    
    def __str__(self):
        return f"{self.name}"

# ⭐⭐ تعريف Customer ثانياً ⭐⭐
class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    serial = models.CharField(max_length=18, unique=True)
    pin = models.CharField(max_length=4)
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    total_referrals = models.IntegerField(default=0)
    referral_earnings = models.IntegerField(default=0)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "عميل"
    
    def __str__(self):
        return f"{self.name}"
    
    def generate_jwt_token(self):
        payload = {
            'customer_id': self.id,
            'serial': self.serial,
            'exp': datetime.utcnow() + timedelta(days=30),
            'type': 'customer'
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')

# ⭐⭐ باقي الموديلات بعد Customer ⭐⭐
class Wallet(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)
    balance = models.IntegerField(default=0)
    total_deposited = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.customer.name}"

class Transaction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20)
    amount = models.IntegerField()
    description = models.TextField()
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.customer.name}"

class BotRegistration(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.source.name}"

class JWTAuditLog(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.customer.serial}"
