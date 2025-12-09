from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.core.cache import cache
import jwt
from datetime import datetime, timedelta
from django.conf import settings
from .models import Customer, Wallet, Transaction, Source, BotRegistration
from django.shortcuts import get_object_or_404

# ==================== JWT Authentication ====================
class CustomerJWTAuthentication(BaseAuthentication):
    """مصادقة JWT مخصصة للعملاء"""
    
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
        
        token = auth_header[7:]
        
        try:
            # فك تشفير التوكن
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # التحقق من نوع التوكن
            if payload.get('type') != 'customer':
                return None
            
            # جلب العميل
            customer_id = payload.get('customer_id')
            if not customer_id:
                return None
            
            customer = Customer.objects.get(id=customer_id, is_active=True)
            
            # إرفاق التوكن مع الطلب
            request.jwt_token = token
            request.jwt_payload = payload
            
            return (customer.user if customer.user else None, token)
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Customer.DoesNotExist):
            return None

# ==================== Mixin للمصادقة المدمجة ====================
class JWTAuthMixin:
    """Mixin لإضافة مصادقة JWT للـ API Views"""
    
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_customer(self, request):
        """الحصول على العميل من المستخدم المصادق"""
        if hasattr(request, 'user') and request.user.is_authenticated:
            # البحث عن العميل المرتبط بالمستخدم
            try:
                return Customer.objects.get(user=request.user, is_active=True)
            except Customer.DoesNotExist:
                pass
        return None

# ==================== مسارات API محدثة ====================
class RegisterAPI(APIView):
    """
    تسجيل عميل جديد مع توليد JWT مباشرة
    """
    
    def post(self, request):
        name = request.data.get('name')
        phone = request.data.get('phone')
        source_prefix = request.data.get('source', 'U')
        referrer_code = request.data.get('referrer_code')
        
        if not name or not phone:
            return Response({
                'success': False,
                'message': 'الاسم ورقم الهاتف مطلوبان'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من صحة رقم الهاتف
        if not phone.isdigit() or len(phone) < 10:
            return Response({
                'success': False,
                'message': 'رقم الهاتف غير صحيح'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من عدم تكرار رقم الهاتف
        if Customer.objects.filter(phone=phone).exists():
            return Response({
                'success': False,
                'message': 'رقم الهاتف مسجل مسبقاً'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من المحيل إذا وجد كود
        referrer = None
        if referrer_code:
            try:
                if referrer_code.startswith('REF'):
                    ref_id = int(referrer_code[3:])
                    referrer = Customer.objects.get(id=ref_id, is_active=True)
                elif referrer_code.startswith('ref'):
                    ref_id = int(referrer_code[3:])
                    referrer = Customer.objects.get(id=ref_id, is_active=True)
            except (ValueError, Customer.DoesNotExist):
                pass
        
        try:
            # التحقق من صحة حرف المصدر
            valid_sources = ['T', 'S', 'M', 'W', 'A', 'U']
            if source_prefix not in valid_sources:
                source_prefix = 'U'
            
            # إنشاء العميل
            customer = Customer.objects.create_customer(
                name=name.strip(),
                phone=phone,
                source_prefix=source_prefix,
                referrer=referrer,
                referred_by_code=referrer_code if referrer else ''
            )
            
            wallet = Wallet.objects.get(customer=customer)
            
            # تسجيل عملية البوت إذا كان هناك معلومات إضافية
            telegram_data = request.data.get('telegram_data')
            if telegram_data and source_prefix == 'T':
                BotRegistration.objects.create(
                    source=customer.source,
                    customer=customer,
                    telegram_user_id=telegram_data.get('id'),
                    telegram_username=telegram_data.get('username'),
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            
            # ⭐ توليد JWT token
            jwt_token = customer.generate_jwt_token()
            
            return Response({
                'success': True,
                'message': 'تم إنشاء الحساب بنجاح',
                'access_token': jwt_token,
                'token_type': 'bearer',
                'expires_in': 2592000,  # 30 يوم
                'serial': customer.serial,
                'pin': customer.pin,
                'referral_code': customer.referral_code,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'phone': customer.phone,
                    'balance': wallet.balance,
                    'source': customer.source.get_prefix_display() if customer.source else 'غير معروف',
                    'serial': customer.serial,
                    'is_trial_active': customer.is_trial_active,
                    'created_at': customer.created_at
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'خطأ في إنشاء الحساب: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CustomerLoginAPI(APIView):
    """
    تسجيل دخول العميل باستخدام السيريال والبين مع إرجاع JWT
    """
    
    def post(self, request):
        serial = request.data.get('serial')
        pin = request.data.get('pin')
        source = request.data.get('source', 'U')

        if not serial or not pin:
            return Response({
                'success': False,
                'message': 'يرجى إدخال السيريال والبين'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(serial=serial, is_active=True)
            
            # التحقق من البين
            if customer.pin != pin:
                return Response({
                    'success': False,
                    'message': 'البين غير صحيح'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            customer.last_login = timezone.now()
            customer.save()

            wallet, created = Wallet.objects.get_or_create(customer=customer)
            
            # تتبع مصدر الدخول
            if source != 'U':
                try:
                    login_source = Source.objects.get(prefix=source)
                    Transaction.objects.create(
                        customer=customer,
                        transaction_type='manual',
                        amount=0,
                        description=f'دخول عبر {login_source.get_prefix_display()}',
                        source=login_source
                    )
                except Source.DoesNotExist:
                    pass
            
            # ⭐ توليد JWT token
            jwt_token = customer.generate_jwt_token()

            return Response({
                'success': True,
                'access_token': jwt_token,
                'token_type': 'bearer',
                'expires_in': 2592000,  # 30 يوم
                'customer': {
                    'id': customer.id,
                    'serial': customer.serial,
                    'name': customer.name,
                    'phone': customer.phone,
                    'balance': wallet.balance,
                    'is_trial_active': customer.is_trial_active,
                    'trial_expires': customer.trial_expires,
                    'created_at': customer.created_at,
                    'last_login': customer.last_login,
                    'source_prefix': customer.serial[0] if customer.serial else 'U',
                    'source_name': customer.source.get_prefix_display() if customer.source else 'غير معروف'
                },
                'message': 'تم الدخول بنجاح'
            })
        except Customer.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو الحساب غير مفعل'
            }, status=status.HTTP_401_UNAUTHORIZED)


class UserProfileAPI(APIView, JWTAuthMixin):
    """
    الحصول على معلومات الملف الشخصي للعميل باستخدام JWT
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        wallet, created = Wallet.objects.get_or_create(customer=customer)
        
        # حساب الوقت المتبقي للتجربة
        trial_remaining = None
        if customer.is_trial_active and customer.trial_expires:
            now = timezone.now()
            if customer.trial_expires > now:
                remaining = customer.trial_expires - now
                hours = remaining.total_seconds() / 3600
                trial_remaining = {
                    'hours': round(hours, 1),
                    'days': round(hours / 24, 1)
                }
            else:
                customer.is_trial_active = False
                customer.save()

        return Response({
            'success': True,
            'customer': {
                'id': customer.id,
                'serial': customer.serial,
                'name': customer.name,
                'phone': customer.phone,
                'balance': wallet.balance,
                'is_trial_active': customer.is_trial_active,
                'is_active': customer.is_active,
                'trial_expires': customer.trial_expires,
                'trial_remaining': trial_remaining,
                'created_at': customer.created_at,
                'last_login': customer.last_login,
                'source': customer.source.get_prefix_display() if customer.source else 'غير معروف',
                'referral_code': customer.referral_code,
                'total_referrals': customer.total_referrals,
                'referral_earnings': customer.referral_earnings
            }
        })


class WalletAPI(APIView, JWTAuthMixin):
    """
    الحصول على معلومات المحفظة والعمليات المالية باستخدام JWT
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 20))
        
        wallet, created = Wallet.objects.get_or_create(customer=customer)
        
        # حساب الإزاحة للباجينيش
        offset = (page - 1) * limit
        
        # الحصول على العمليات المالية
        transactions = Transaction.objects.filter(customer=customer)\
            .order_by('-created_at')[offset:offset + limit]
        
        # إحصائيات إضافية
        total_transactions = Transaction.objects.filter(customer=customer).count()
        total_pages = (total_transactions + limit - 1) // limit

        return Response({
            'success': True,
            'balance': wallet.balance,
            'total_deposited': wallet.total_deposited,
            'total_spent': wallet.total_spent,
            'referral_earnings': wallet.referral_earnings,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_transactions,
                'pages': total_pages
            },
            'transactions': [
                {
                    'id': t.id,
                    'type': t.transaction_type,
                    'type_display': t.get_transaction_type_display(),
                    'amount': t.amount,
                    'description': t.description,
                    'source': t.source.get_prefix_display() if t.source else 'غير معروف',
                    'date': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'timestamp': t.created_at.timestamp()
                }
                for t in transactions
            ]
        })


class RecoverSerialAPI(APIView):
    """
    استعادة السيريال المفقود باستخدام الهاتف والبين
    """
    
    def post(self, request):
        phone = request.data.get('phone')
        pin = request.data.get('pin')

        if not phone or not pin:
            return Response({
                'success': False,
                'message': 'الهاتف والبين مطلوبان'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(phone=phone, pin=pin, is_active=True)
            
            # توليد JWT مؤقت للاستخدام الفوري
            jwt_token = customer.generate_jwt_token()
            
            return Response({
                'success': True,
                'access_token': jwt_token,
                'token_type': 'bearer',
                'expires_in': 86400,  # 24 ساعة
                'serial': customer.serial,
                'name': customer.name,
                'status': 'active' if customer.is_active else 'inactive',
                'is_trial_active': customer.is_trial_active
            })
        except Customer.DoesNotExist:
            return Response({
                'success': False,
                'message': 'الهاتف أو البين غير صحيح'
            }, status=status.HTTP_404_NOT_FOUND)


class AccountStatusAPI(APIView, JWTAuthMixin):
    """
    التحقق من حالة الحساب باستخدام JWT
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)

        trial_end = customer.created_at + timezone.timedelta(hours=48)
        time_left = trial_end - timezone.now()
        hours_left = max(0, time_left.total_seconds() / 3600)
        days_left = hours_left / 24
        
        # تحديث حالة التجربة إذا انتهت
        if hours_left <= 0 and customer.is_trial_active:
            customer.is_trial_active = False
            customer.save()

        return Response({
            'success': True,
            'status': 'active' if customer.is_active else 'inactive',
            'is_trial_active': customer.is_trial_active,
            'created_at': customer.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'trial_ends_at': trial_end.strftime('%Y-%m-%d %H:%M:%S'),
            'hours_left': round(hours_left, 1),
            'days_left': round(days_left, 2),
            'is_expired': hours_left <= 0,
            'serial': customer.serial,
            'name': customer.name
        })


class ChangePINAPI(APIView, JWTAuthMixin):
    """
    تغيير بين الحساب باستخدام JWT
    """
    
    def post(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        old_pin = request.data.get('old_pin')
        new_pin = request.data.get('new_pin')

        if not old_pin or not new_pin:
            return Response({
                'success': False,
                'message': 'جميع الحقول مطلوبة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_pin) != 4 or not new_pin.isdigit():
            return Response({
                'success': False,
                'message': 'البين الجديد يجب أن يكون 4 أرقام'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من البين القديم
        if customer.pin != old_pin:
            return Response({
                'success': False,
                'message': 'البين القديم غير صحيح'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # تغيير البين
        customer.pin = new_pin
        customer.save()
        
        # تسجيل العملية
        Transaction.objects.create(
            customer=customer,
            transaction_type='manual',
            amount=0,
            description='تغيير بين الحساب'
        )

        return Response({
            'success': True,
            'message': 'تم تغيير البين بنجاح'
        })


class PurchaseAPI(APIView, JWTAuthMixin):
    """
    شراء خدمة أو منتج باستخدام JWT
    """
    
    def post(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        amount = int(request.data.get('amount', 0))
        product_name = request.data.get('product_name', 'منتج')
        description = request.data.get('description', '')
        
        if amount <= 0:
            return Response({
                'success': False,
                'message': 'المبلغ غير صحيح'
            }, status=status.HTTP_400_BAD_REQUEST)

        wallet = customer.wallet
        
        # التحقق من الرصيد
        if not wallet.can_afford(amount):
            return Response({
                'success': False,
                'message': 'رصيد غير كافي',
                'balance': wallet.balance,
                'required': amount
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # تنفيذ الشراء
        wallet.spend(
            amount=amount,
            description=f'{product_name} - {description}'
        )
        
        return Response({
            'success': True,
            'message': f'تم شراء {product_name} بنجاح',
            'new_balance': wallet.balance,
            'transaction': {
                'amount': -amount,
                'description': f'شراء {product_name}',
                'date': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        })


class ChargeWalletAPI(APIView):
    """
    شحن رصيد المحفظة (للاستخدام الداخلي أو بوابات الدفع)
    """
    
    def post(self, request):
        # التحقق من المفتاح السري للشحن
        secret_key = request.data.get('secret_key')
        if secret_key != settings.WALLET_CHARGE_SECRET:  # من settings
            return Response({
                'success': False,
                'message': 'غير مصرح'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        serial = request.data.get('serial')
        amount = int(request.data.get('amount', 0))
        description = request.data.get('description', 'شحن رصيد')
        
        if not serial or amount <= 0:
            return Response({
                'success': False,
                'message': 'بيانات غير صحيحة'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(serial=serial, is_active=True)
            wallet = customer.wallet
            
            # شحن الرصيد
            wallet.charge(
                amount=amount,
                description=description
            )
            
            return Response({
                'success': True,
                'message': 'تم شحن الرصيد بنجاح',
                'new_balance': wallet.balance,
                'customer': {
                    'name': customer.name,
                    'serial': customer.serial,
                    'phone': customer.phone
                }
            })
        except Customer.DoesNotExist:
            return Response({
                'success': False,
                'message': 'العميل غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)


class SourceStatsAPI(APIView, JWTAuthMixin):
    """
    إحصائيات المصادر (للمستخدمين المسؤولين)
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        # التحقق من صلاحيات المسؤول
        if not customer or not customer.user.is_staff:
            return Response({
                'success': False,
                'message': 'غير مصرح'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        period = request.query_params.get('period', 'today')
        
        # حساب الفترة الزمنية
        now = timezone.now()
        if period == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            start_date = now - timezone.timedelta(days=7)
        elif period == 'month':
            start_date = now - timezone.timedelta(days=30)
        else:  # all
            start_date = None
        
        sources = Source.objects.filter(is_active=True)
        
        stats = []
        for source in sources:
            customers_query = source.customers.all()
            if start_date:
                customers_query = customers_query.filter(created_at__gte=start_date)
            
            customers_count = customers_query.count()
            
            total_balance = 0
            if customers_count > 0:
                total_balance = Wallet.objects.filter(
                    customer__in=customers_query
                ).aggregate(total=Sum('balance'))['total'] or 0
            
            today_registrations = source.customers.filter(
                created_at__date=now.date()
            ).count()
            
            stats.append({
                'prefix': source.prefix,
                'name': source.name,
                'display_name': source.get_prefix_display(),
                'customers_count': customers_count,
                'total_balance': total_balance,
                'today_registrations': today_registrations,
                'bot_username': source.bot_username,
                'color': self.get_source_color(source.prefix)
            })
        
        total_query = Customer.objects.all()
        if start_date:
            total_query = total_query.filter(created_at__gte=start_date)
        
        total_customers = total_query.count()
        total_balance = Wallet.objects.filter(
            customer__in=total_query
        ).aggregate(total=Sum('balance'))['total'] or 0
        
        today_total = Customer.objects.filter(
            created_at__date=now.date()
        ).count()
        
        return Response({
            'success': True,
            'period': period,
            'stats': stats,
            'summary': {
                'total_customers': total_customers,
                'total_balance': total_balance,
                'today_registrations': today_total,
                'period_start': start_date.strftime('%Y-%m-%d') if start_date else 'all'
            }
        })
    
    def get_source_color(self, prefix):
        color_map = {
            'T': '#0088cc',
            'S': '#28a745',
            'M': '#0068d5',
            'W': '#25D366',
            'A': '#dc3545',
            'U': '#6c757d',
        }
        return color_map.get(prefix, '#6c757d')


class ReferralStatsAPI(APIView, JWTAuthMixin):
    """
    إحصائيات الإحالات باستخدام JWT
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # الحصول على الإحالات
        referrals = Customer.objects.filter(referrer=customer)\
            .select_related('wallet', 'source')\
            .order_by('-created_at')
        
        total_referrals = referrals.count()
        
        referral_list = []
        for ref in referrals[:50]:
            wallet_balance = ref.wallet.balance if hasattr(ref, 'wallet') else 0
            referral_list.append({
                'name': ref.name,
                'phone': ref.phone[:3] + '****' + ref.phone[-3:] if len(ref.phone) > 6 else ref.phone,
                'serial': ref.serial,
                'created_at': ref.created_at.strftime('%Y-%m-%d'),
                'source': ref.source.get_prefix_display() if ref.source else 'غير معروف',
                'balance': wallet_balance,
                'is_active': ref.is_active
            })
        
        return Response({
            'success': True,
            'stats': {
                'total_referrals': customer.total_referrals,
                'referral_earnings': customer.referral_earnings,
                'referral_code': customer.referral_code,
                'referral_url': f"https://t.me/your_bot?start=ref{customer.id}",
                'recent_referrals': referral_list
            }
        })


class CheckPhoneAPI(APIView):
    """
    التحقق من وجود رقم الهاتف في النظام (عام)
    """
    
    def get(self, request):
        phone = request.query_params.get('phone')
        
        if not phone:
            return Response({
                'success': False,
                'message': 'رقم الهاتف مطلوب'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        exists = Customer.objects.filter(phone=phone).exists()
        
        return Response({
            'success': True,
            'exists': exists,
            'message': 'رقم الهاتف مسجل مسبقاً' if exists else 'رقم الهاتف غير مسجل'
        })


class UpdateProfileAPI(APIView, JWTAuthMixin):
    """
    تحديث معلومات الملف الشخصي باستخدام JWT
    """
    
    def post(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        name = request.data.get('name')
        
        if not name:
            return Response({
                'success': False,
                'message': 'الاسم الجديد مطلوب'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # تحديث الاسم
        old_name = customer.name
        customer.name = name.strip()
        customer.save()
        
        # تسجيل العملية
        Transaction.objects.create(
            customer=customer,
            transaction_type='manual',
            amount=0,
            description=f'تحديث الاسم من "{old_name}" إلى "{name}"'
        )
        
        return Response({
            'success': True,
            'message': 'تم تحديث الاسم بنجاح',
            'new_name': customer.name
        })


class DashboardStatsAPI(APIView, JWTAuthMixin):
    """
    إحصائيات لوحة التحكم (للمسؤولين)
    """
    
    def get(self, request):
        customer = self.get_customer(request)
        
        # التحقق من صلاحيات المسؤول
        if not customer or not customer.user.is_staff:
            return Response({
                'success': False,
                'message': 'غير مصرح'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timezone.timedelta(days=7)
        month_start = now - timezone.timedelta(days=30)
        
        total_customers = Customer.objects.count()
        active_customers = Customer.objects.filter(is_active=True).count()
        trial_customers = Customer.objects.filter(is_trial_active=True).count()
        
        daily_signups = Customer.objects.filter(created_at__gte=today_start).count()
        weekly_signups = Customer.objects.filter(created_at__gte=week_start).count()
        monthly_signups = Customer.objects.filter(created_at__gte=month_start).count()
        
        wallets_stats = Wallet.objects.aggregate(
            total_balance=Sum('balance'),
            total_deposited=Sum('total_deposited'),
            total_spent=Sum('total_spent')
        )
        
        top_sources = Customer.objects.values('source__prefix', 'source__name')\
            .annotate(count=Count('id'))\
            .order_by('-count')[:5]
        
        return Response({
            'success': True,
            'stats': {
                'customers': {
                    'total': total_customers,
                    'active': active_customers,
                    'trial': trial_customers,
                    'daily_signups': daily_signups,
                    'weekly_signups': weekly_signups,
                    'monthly_signups': monthly_signups
                },
                'wallets': {
                    'total_balance': wallets_stats['total_balance'] or 0,
                    'total_deposited': wallets_stats['total_deposited'] or 0,
                    'total_spent': wallets_stats['total_spent'] or 0
                },
                'top_sources': [
                    {
                        'prefix': item['source__prefix'],
                        'name': item['source__name'],
                        'count': item['count']
                    }
                    for item in top_sources
                ]
            },
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')
        })


class ValidateTokenAPI(APIView):
    """
    التحقق من صحة JWT token
    """
    
    def post(self, request):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return Response({
                'success': False,
                'valid': False,
                'message': 'توكن غير صالح'
            }, status=401)
        
        token = auth_header[7:]
        
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            customer_id = payload.get('customer_id')
            if not customer_id:
                return Response({
                    'success': False,
                    'valid': False,
                    'message': 'توكن غير صالح'
                })
            
            customer = Customer.objects.get(id=customer_id, is_active=True)
            
            return Response({
                'success': True,
                'valid': True,
                'customer': {
                    'id': customer.id,
                    'serial': customer.serial,
                    'name': customer.name
                },
                'expires_at': datetime.fromtimestamp(payload['exp']).isoformat() if 'exp' in payload else None
            })
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Customer.DoesNotExist):
            return Response({
                'success': False,
                'valid': False,
                'message': 'توكن منتهي أو غير صالح'
            }, status=401)


class RefreshTokenAPI(APIView):
    """
    تجديد JWT token
    """
    
    def post(self, request):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return Response({
                'success': False,
                'message': 'توكن غير صالح'
            }, status=401)
        
        token = auth_header[7:]
        
        try:
            # فك التوكن القديم (دون التحقق من الانتهاء)
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM],
                options={'verify_exp': False}  # قبول التوكن المنتهي
            )
            
            customer_id = payload.get('customer_id')
            if not customer_id:
                return Response({
                    'success': False,
                    'message': 'توكن غير صالح'
                }, status=401)
            
            customer = Customer.objects.get(id=customer_id, is_active=True)
            
            # توليد توكن جديد
            new_token = customer.generate_jwt_token()
            
            return Response({
                'success': True,
                'access_token': new_token,
                'token_type': 'bearer',
                'expires_in': 2592000
            })
            
        except (jwt.InvalidTokenError, Customer.DoesNotExist):
            return Response({
                'success': False,
                'message': 'توكن غير صالح'
            }, status=401)


class HealthCheckAPI(APIView):
    """فحص صحة التطبيق"""
    
    def get(self, request):
        from django.db import connection
        from django.core.cache import cache
        
        # فحص قاعدة البيانات
        db_ok = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
        except:
            db_ok = False
        
        # فحص الـ cache (Redis)
        cache_ok = False
        try:
            cache.set('health_check', 'ok', 5)
            cache_ok = cache.get('health_check') == 'ok'
        except:
            cache_ok = False
        
        # فحص الموديلات
        models_ok = False
        try:
            Customer.objects.count()
            Source.objects.count()
            models_ok = True
        except:
            models_ok = False
        
        status = 'healthy' if all([db_ok, models_ok]) else 'unhealthy'
        
        return Response({
            'status': status,
            'timestamp': timezone.now().isoformat(),
            'checks': {
                'database': 'ok' if db_ok else 'error',
                'models': 'ok' if models_ok else 'error',
                'cache': 'ok' if cache_ok else 'error',
            },
            'service': 'serialco-accounts-api',
            'version': '2.0',
            'environment': 'production' if not settings.DEBUG else 'development'
        })
