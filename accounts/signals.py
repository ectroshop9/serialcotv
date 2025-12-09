# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Customer, Wallet, Transaction, JWTAuditLog

@receiver(post_save, sender=Customer)
def create_customer_wallet(sender, instance, created, **kwargs):
    """إنشاء محفظة تلقائياً عند إنشاء عميل"""
    if created and not hasattr(instance, 'wallet'):
        wallet = Wallet.objects.create(customer=instance)
        wallet.balance = 150
        wallet.total_deposited = 150
        wallet.save()
        
        Transaction.objects.create(
            customer=instance,
            transaction_type='bonus',
            amount=150,
            description='مكافأة التسجيل',
            source=instance.source
        )
        
        if instance.referrer:
            instance.referrer.add_referral(instance)

@receiver(post_save, sender=Customer)
def log_jwt_creation(sender, instance, created, **kwargs):
    """تسجيل إنشاء JWT عند إنشاء عميل جديد"""
    if created:
        JWTAuditLog.objects.create(
            customer=instance,
            action='TOKEN_GENERATED',
            token_fingerprint='initial_creation',
            description='إنشاء حساب جديد وتوليد JWT'
        )

@receiver(post_save, sender=User)
def link_customer_to_user(sender, instance, created, **kwargs):
    """ربط المستخدم مع العميل إذا كان username يتطابق مع serial"""
    if created:
        try:
            customer = Customer.objects.get(serial=instance.username)
            customer.user = instance
            customer.save()
        except Customer.DoesNotExist:
            pass
