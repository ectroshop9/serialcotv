from django.db import models
import random
import string
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User  # ⭐ استيراد User العادي
import jwt  # ⭐ إضافة PyJWT
from datetime import datetime, timedelta
from django.conf import settings

# ⭐⭐ أولا: تأكد أن لا يوجد Custom User هنا ⭐⭐
# ⭐ لا تضيف: from django.contrib.auth.models import AbstractUser
# ⭐ لا تضيف: class User(AbstractUser)

class Source(models.Model):
    """نموذج لتخزين مصادر التسجيل (البوتات)"""
    
    SOURCE_PREFIXES = {
        'T': 'تليجرام',
        'S': 'المتجر',
        'M': 'مسنجر',
        'W': 'واتساب',
        'A': 'إداري',
        'U': 'غير معروف'
    }
    
    name = models.CharField(max_length=50, verbose_name="اسم المصدر")
    prefix = models.CharField(
        max_length=1, 
        unique=True,
        verbose_name="الحرف المميز",
        choices=[(k, v) for k, v in SOURCE_PREFIXES.items()]
    )
    description = models.TextField(blank=True, verbose_name="وصف المصدر")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    bot_username = models.CharField(max_length=50, blank=True, verbose_name="يوزر البوت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = "مصدر تسجيل"
        verbose_name_plural = "مصادر التسجيل"
        ordering = ['prefix']
    
    def __str__(self):
        return f"{self.get_prefix_display()} - {self.name}"
    
    @property
    def full_prefix(self):
        return f"{self.prefix}SC"


class CustomerManager(models.Manager):
    def create_customer(self, name, phone, source_prefix='U', referrer=None, **extra_fields):
        """
        إنشاء عميل جديد مع تتبع المصدر
        
        Args:
            name: اسم العميل
            phone: رقم الهاتف
            source_prefix: حرف المصدر (T, S, M, W, A, U)
            referrer: عميل محول (إذا كان التسجيل عن طريق الإحالة)
            **extra_fields: حقول إضافية
        """
        # الحصول على المصدر
        try:
            source = Source.objects.get(prefix=source_prefix)
        except Source.DoesNotExist:
            source, _ = Source.objects.get_or_create(
                prefix='U',
                defaults={'name': 'غير معروف', 'description': 'مصدر غير معروف'}
            )
        
        # توليد سيريال فريد مع حرف المصدر
        base_serial = f"{source_prefix}SC" + ''.join(random.choices(string.digits, k=14))
        
        # التأكد من عدم تكرار السيريال
        while Customer.objects.filter(serial=base_serial).exists():
            base_serial = f"{source_prefix}SC" + ''.join(random.choices(string.digits, k=14))
        
        # توليد بين
        pin = ''.join(random.choices(string.digits, k=4))
        
        # حساب مكافأة الإحالة إذا وجدت
        referral_bonus = 0
        referral_description = ''
        
        if referrer:
            referral_bonus = 50  # مكافأة للمُحال
            referrer_bonus = 30  # مكافأة للمُحيل
            
            # إضافة مكافأة للمُحيل
            try:
                referrer.wallet.charge(
                    amount=referrer_bonus,
                    description=f'مكافأة إحالة للعميل {name}'
                )
                referral_description = f'إحالة من {referrer.name}'
            except:
                pass
        
        # ⭐ إنشاء User مرتبط
        user = User.objects.create_user(
            username=base_serial,  # السيريال كـ username
            email=f'{phone}@serialco.tv',
            password=pin  # البين كـ password
        )
        
        # إنشاء العميل
        customer = self.model(
            name=name,
            phone=phone,
            serial=base_serial,
            pin=pin,
            source=source,
            referrer=referrer,
            is_active=True,
            is_trial_active=True,
            trial_expires=timezone.now() + timezone.timedelta(hours=48),
            last_login=timezone.now(),
            user=user,  # ⭐ ربط مع User
            **extra_fields
        )
        customer.save(using=self._db)
        
        # إنشاء محفظة مع مكافأة الإحالة إذا وجدت
        wallet, created = Wallet.objects.get_or_create(customer=customer)
        if created:
            wallet.balance = 150 + referral_bonus
            wallet.total_deposited = 150 + referral_bonus
            wallet.save()
            
            # تسجيل مكافأة التسجيل
            Transaction.objects.create(
                customer=customer,
                transaction_type='bonus',
                amount=150,
                description='مكافأة التسجيل',
                source=source
            )
            
            # تسجيل مكافأة الإحالة إذا وجدت
            if referral_bonus > 0:
                Transaction.objects.create(
                    customer=customer,
                    transaction_type='bonus',
                    amount=referral_bonus,
                    description=f'مكافأة إحالة {referral_description}',
                    source=source
                )
        
        return customer


class Customer(models.Model):
    """نموذج العميل مع تتبع المصدر"""
    
    # المعلومات الأساسية
    name = models.CharField(max_length=100, verbose_name="الاسم الكامل")
    phone = models.CharField(max_length=15, unique=True, verbose_name="رقم الهاتف")
    
    # بيانات الدخول
    serial = models.CharField(max_length=18, unique=True, verbose_name="السيريال")
    pin = models.CharField(max_length=4, verbose_name="البين")
    
    # ⭐ ربط مع Django User للنظام الجديد
    user = models.OneToOneField(
        User,  # ⭐ User العادي من Django
        on_delete=models.CASCADE,
        related_name='customer_profile',
        null=True,
        blank=True,
        verbose_name="حساب النظام"
    )
    
    # تتبع المصدر والإحالة
    source = models.ForeignKey(
        Source,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers',
        verbose_name="مصدر التسجيل"
    )
    
    referrer = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals',
        verbose_name="المُحيل"
    )
    
    referred_by_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="كود الإحالة المستخدم"
    )
    
    # حالة الحساب
    is_active = models.BooleanField(default=True, verbose_name="الحساب نشط")
    is_trial_active = models.BooleanField(default=True, verbose_name="التجربة نشطة")
    trial_expires = models.DateTimeField(null=True, blank=True, verbose_name="انتهاء التجربة")
    
    # إحصائيات
    total_referrals = models.IntegerField(default=0, verbose_name="عدد الإحالات")
    referral_earnings = models.IntegerField(default=0, verbose_name="أرباح الإحالات")
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    last_login = models.DateTimeField(null=True, blank=True, verbose_name="آخر دخول")
    
    objects = CustomerManager()
    
    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source']),
            models.Index(fields=['referrer']),
            models.Index(fields=['serial']),
            models.Index(fields=['phone']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.phone}) - {self.serial}"
    
    @property
    def balance(self):
        """الحصول على رصيد المحفظة"""
        try:
            return self.wallet.balance
        except Wallet.DoesNotExist:
            return 0
    
    @property
    def referral_code(self):
        """كود الإحالة الخاص بالعميل"""
        return f"REF{self.id:06d}"
    
    def get_referral_url(self, bot_username=None):
        """الحصول على رابط الإحالة"""
        if bot_username:
            return f"https://t.me/{bot_username}?start=ref{self.id}"
        return self.referral_code
    
    def add_referral(self, new_customer):
        """إضافة إحالة جديدة"""
        self.total_referrals += 1
        self.save()
        
        # تحديث أرباح الإحالة في المحفظة
        try:
            self.wallet.charge(
                amount=30,
                description=f'مكافأة إحالة للعميل {new_customer.name}'
            )
            self.referral_earnings += 30
            self.save()
        except:
            pass
    
    def generate_jwt_token(self):
        """
        ⭐ توليد JWT token للعميل
        """
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
        """
        ⭐ استخراج العميل من JWT token
        """
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=['HS256']
            )
            
            customer_id = payload.get('customer_id')
            if customer_id:
                return cls.objects.get(id=customer_id, is_active=True)
                
            serial = payload.get('serial')
            if serial:
                return cls.objects.get(serial=serial, is_active=True)
                
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, cls.DoesNotExist):
            return None
    
    def update_user_info(self):
        """تحديث معلومات المستخدم المرتبط"""
        if self.user:
            if self.user.username != self.serial:
                self.user.username = self.serial
            
            if not self.user.email or '@serialco.tv' in self.user.email:
                self.user.email = f'{self.phone}@serialco.tv'
            
            self.user.save()
    
    def save(self, *args, **kwargs):
        if self.pk:
            old = Customer.objects.get(pk=self.pk)
            if old.serial != self.serial or old.phone != self.phone:
                self.update_user_info()
        
        if not self.user:
            user = User.objects.create_user(
                username=self.serial,
                email=f'{self.phone}@serialco.tv',
                password=self.pin
            )
            self.user = user
        
        super().save(*args, **kwargs)


class Wallet(models.Model):
    """محفظة العميل"""
    
    customer = models.OneToOneField(
        Customer, 
        on_delete=models.CASCADE,
        related_name='wallet',
        verbose_name="العميل"
    )
    
    balance = models.IntegerField(default=0, verbose_name="الرصيد الحالي")
    total_deposited = models.IntegerField(default=0, verbose_name="الإجمالي المشحون")
    total_spent = models.IntegerField(default=0, verbose_name="الإجمالي المنفق")
    referral_earnings = models.IntegerField(default=0, verbose_name="أرباح الإحالات")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    class Meta:
        verbose_name = "محفظة"
        verbose_name_plural = "المحافظ"
    
    def __str__(self):
        return f"{self.customer.name} - {self.balance}⭐"
    
    def can_afford(self, amount):
        """هل يمكن تحمل المبلغ؟"""
        return self.balance >= amount
    
    def charge(self, amount, description='شحن رصيد'):
        """شحن المحفظة"""
        self.balance += amount
        self.total_deposited += amount
        self.save()
        
        Transaction.objects.create(
            customer=self.customer,
            transaction_type='charge',
            amount=amount,
            description=description,
            source=self.customer.source
        )
    
    def spend(self, amount, description='شراء منتج'):
        """إنفاق من المحفظة"""
        if not self.can_afford(amount):
            raise ValueError("رصيد غير كافي")
        
        self.balance -= amount
        self.total_spent += amount
        self.save()
        
        Transaction.objects.create(
            customer=self.customer,
            transaction_type='purchase',
            amount=-amount,
            description=description,
            source=self.customer.source
        )
    
    def get_jwt_authorization(self):
        """
        ⭐ الحصول على header Authorization للـ JWT
        """
        token = self.customer.generate_jwt_token()
        return f'Bearer {token}'


class Transaction(models.Model):
    """سجل المعاملات المالية"""
    
    TRANSACTION_TYPES = [
        ('bonus', 'مكافأة تسجيل'),
        ('purchase', 'شراء ملف'),
        ('charge', 'شحن رصيد'),
        ('refund', 'استرجاع'),
        ('manual', 'تعديل يدوي'),
        ('referral', 'مكافأة إحالة'),
        ('trial', 'تجربة مجانية'),
    ]
    
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name="العميل"
    )
    
    transaction_type = models.CharField(
        max_length=20, 
        choices=TRANSACTION_TYPES,
        verbose_name="نوع العملية"
    )
    
    amount = models.IntegerField(verbose_name="المبلغ")
    description = models.TextField(verbose_name="الوصف")
    
    source = models.ForeignKey(
        Source,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="مصدر العملية"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ العملية")
    
    class Meta:
        verbose_name = "عملية مالية"
        verbose_name_plural = "العمليات المالية"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.get_transaction_type_display()} - {self.amount}⭐"
    
    def get_jwt_context(self):
        """
        ⭐ معلومات إضافية للاستخدام مع JWT
        """
        return {
            'transaction_id': self.id,
            'customer_serial': self.customer.serial,
            'type': self.transaction_type,
            'amount': self.amount,
            'timestamp': self.created_at.isoformat()
        }


class BotRegistration(models.Model):
    """سجل عمليات التسجيل عبر البوتات"""
    
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name='registrations',
        verbose_name="المصدر"
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='bot_registrations',
        verbose_name="العميل"
    )
    
    telegram_user_id = models.BigIntegerField(null=True, blank=True, verbose_name="معرف تليجرام")
    telegram_username = models.CharField(max_length=50, blank=True, verbose_name="يوزر تليجرام")
    
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    
    class Meta:
        verbose_name = "تسجيل عبر بوت"
        verbose_name_plural = "التسجيلات عبر البوتات"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.source.name} - {self.customer.name}"


class JWTAuditLog(models.Model):
    """
    ⭐ سجلات تدقيق JWT - لتتبع استخدام التوكنات
    """
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='jwt_logs',
        verbose_name="العميل"
    )
    
    action = models.CharField(max_length=50, verbose_name="الإجراء")
    token_fingerprint = models.CharField(max_length=64, verbose_name="بصمة التوكن")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت الإجراء")
    
    class Meta:
        verbose_name = "سجل تدقيق JWT"
        verbose_name_plural = "سجلات تدقيق JWT"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.serial} - {self.action}"


# إشارات تلقائية
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
    """
    ⭐ ربط المستخدم مع العميل إذا كان username يتطابق مع serial
    """
    if created:
        try:
            customer = Customer.objects.get(serial=instance.username)
            customer.user = instance
            customer.save()
        except Customer.DoesNotExist:
            pass


# دالة مساعدة
def get_customer_from_jwt_request(request):
    """
    ⭐ دالة مساعدة: استخراج العميل من طلب JWT
    """
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]
    return Customer.get_customer_from_token(token)
