from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q
import jwt
import re
from datetime import datetime, timedelta
from django.conf import settings
from .models import Customer, Transaction, Source, Notification


class CustomerJWTAuthentication:
    """توثيق العميل باستخدام JWT Token"""
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return None
        
        token = auth_header[7:]
        
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            customer_id = payload.get('customer_id')
            token_type = payload.get('type')
            
            if token_type != 'customer':
                return None
            
            customer = Customer.objects.get(id=customer_id, is_active=True)
            return (customer, token)
        except:
            return None


class JWTAuthMixin:
    """مزيج لإضافة توثيق JWT للـ Views"""
    authentication_classes = []
    permission_classes = [IsAuthenticated]
    
    def get_customer(self, request):
        auth = CustomerJWTAuthentication()
        result = auth.authenticate(request)
        if result:
            return result[0]
        return None


class RegisterAPI(APIView):
    """تسجيل حساب جديد"""
    def post(self, request):
        name = request.data.get('name', '').strip()
        phone = request.data.get('phone', '').strip()
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        
        # التحقق من الاسم
        if not name:
            return Response({
                'success': False,
                'message': 'الاسم مطلوب'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # يجب توفير الهاتف أو الإيميل
        if not phone and not email:
            return Response({
                'success': False,
                'message': 'رقم الهاتف أو البريد الإلكتروني مطلوب'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من صيغة الإيميل
        if email:
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                return Response({
                    'success': False,
                    'message': 'صيغة البريد الإلكتروني غير صحيحة'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if Customer.objects.filter(email=email).exists():
                return Response({
                    'success': False,
                    'message': 'البريد الإلكتروني مسجل مسبقاً'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من رقم الهاتف
        if phone:
            if Customer.objects.filter(phone=phone).exists():
                return Response({
                    'success': False,
                    'message': 'رقم الهاتف مسجل مسبقاً'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # التحقق من كلمة المرور
        if password:
            if len(password) < 6:
                return Response({
                    'success': False,
                    'message': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # إنشاء العميل
        customer_data = {
            'name': name,
            'phone': phone if phone else '',
        }
        
        if email:
            customer_data['email'] = email
        
        if password:
            customer_data['password_hash'] = make_password(password)
        
        try:
            customer = Customer.objects.create(**customer_data)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'حدث خطأ أثناء إنشاء الحساب: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        jwt_token = customer.generate_jwt_token()
        
        response_data = {
            'success': True,
            'message': 'تم إنشاء الحساب بنجاح',
            'access_token': jwt_token,
            'token_type': 'bearer',
            'expires_in': 2592000,  # 30 يوم
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
            }
        }
        
        if customer.email:
            response_data['customer']['email'] = customer.email
        
        return Response(response_data, status=status.HTTP_201_CREATED)


class CustomerLoginAPI(APIView):
    """تسجيل الدخول - يدعم الإيميل+باسورد أو رقم الهاتف فقط"""
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        phone = request.data.get('phone', '').strip()
        
        # تسجيل الدخول بالإيميل والباسورد
        if email and password:
            try:
                customer = Customer.objects.get(email=email, is_active=True)
                
                if not customer.password_hash:
                    return Response({
                        'success': False,
                        'message': 'هذا الحساب لا يملك كلمة مرور. استخدم رقم الهاتف لتسجيل الدخول'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                if check_password(password, customer.password_hash):
                    customer.last_login = timezone.now()
                    customer.save()
                    
                    jwt_token = customer.generate_jwt_token()
                    
                    return Response({
                        'success': True,
                        'access_token': jwt_token,
                        'token_type': 'bearer',
                        'expires_in': 2592000,
                        'customer': {
                            'id': customer.id,
                            'name': customer.name,
                            'phone': customer.phone,
                            'email': customer.email,
                        },
                        'message': 'تم الدخول بنجاح'
                    })
                else:
                    return Response({
                        'success': False,
                        'message': 'كلمة المرور غير صحيحة'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                    
            except Customer.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'البريد الإلكتروني غير مسجل'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        # تسجيل الدخول برقم الهاتف فقط (للعملاء القدامى أو المسجلين بدون إيميل)
        if phone:
            try:
                customer = Customer.objects.get(phone=phone, is_active=True)
                customer.last_login = timezone.now()
                customer.save()
                
                jwt_token = customer.generate_jwt_token()
                
                return Response({
                    'success': True,
                    'access_token': jwt_token,
                    'token_type': 'bearer',
                    'expires_in': 2592000,
                    'customer': {
                        'id': customer.id,
                        'name': customer.name,
                        'phone': customer.phone,
                    },
                    'message': 'تم الدخول بنجاح'
                })
            except Customer.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'رقم الهاتف غير مسجل'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({
            'success': False,
            'message': 'يرجى إدخال البريد الإلكتروني وكلمة المرور أو رقم الهاتف'
        }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileAPI(APIView, JWTAuthMixin):
    """عرض الملف الشخصي"""
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        profile_data = {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'token_balance': customer.token_balance,
            'is_active': customer.is_active,
            'created_at': customer.created_at.strftime('%Y-%m-%d %H:%M'),
            'last_login': customer.last_login.strftime('%Y-%m-%d %H:%M') if customer.last_login else None,
        }
        
        if customer.email:
            profile_data['email'] = customer.email
        
        return Response({
            'success': True,
            'customer': profile_data
        })


class AccountStatusAPI(APIView, JWTAuthMixin):
    """التحقق من حالة الحساب"""
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({
            'success': True,
            'status': 'active' if customer.is_active else 'inactive',
            'name': customer.name,
            'token_balance': customer.token_balance,
        })


class ValidateTokenAPI(APIView):
    """التحقق من صحة التوكن"""
    def post(self, request):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return Response({
                'success': False,
                'valid': False,
                'message': 'توكن غير صالح - صيغة خاطئة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        token = auth_header[7:]
        
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            customer_id = payload.get('customer_id')
            token_type = payload.get('type')
            
            if token_type != 'customer':
                return Response({
                    'success': False,
                    'valid': False,
                    'message': 'نوع التوكن غير صالح'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            customer = Customer.objects.get(id=customer_id, is_active=True)
            
            return Response({
                'success': True,
                'valid': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                }
            })
        except jwt.ExpiredSignatureError:
            return Response({
                'success': False,
                'valid': False,
                'message': 'انتهت صلاحية التوكن'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({
                'success': False,
                'valid': False,
                'message': 'توكن غير صالح'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Customer.DoesNotExist:
            return Response({
                'success': False,
                'valid': False,
                'message': 'العميل غير موجود'
            }, status=status.HTTP_401_UNAUTHORIZED)


class UpdateProfileAPI(APIView, JWTAuthMixin):
    """تحديث الملف الشخصي"""
    def post(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        name = request.data.get('name', '').strip()
        email = request.data.get('email', '').strip().lower()
        phone = request.data.get('phone', '').strip()
        password = request.data.get('password', '')
        
        updated = False
        
        if name:
            customer.name = name
            updated = True
        
        if email and email != customer.email:
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                return Response({
                    'success': False,
                    'message': 'صيغة البريد الإلكتروني غير صحيحة'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if Customer.objects.filter(email=email).exclude(id=customer.id).exists():
                return Response({
                    'success': False,
                    'message': 'البريد الإلكتروني مستخدم من قبل'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            customer.email = email
            updated = True
        
        if phone and phone != customer.phone:
            if Customer.objects.filter(phone=phone).exclude(id=customer.id).exists():
                return Response({
                    'success': False,
                    'message': 'رقم الهاتف مستخدم من قبل'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            customer.phone = phone
            updated = True
        
        if password:
            if len(password) < 6:
                return Response({
                    'success': False,
                    'message': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            customer.password_hash = make_password(password)
            updated = True
        
        if not updated:
            return Response({
                'success': False,
                'message': 'لم يتم توفير أي بيانات للتحديث'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        customer.save()
        
        return Response({
            'success': True,
            'message': 'تم تحديث البيانات بنجاح',
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'email': customer.email if customer.email else None,
            }
        })


class NotificationListAPI(APIView, JWTAuthMixin):
    """قائمة الإشعارات"""
    def get(self, request):
        customer = self.get_customer(request)
        if not customer:
            return Response({
                'success': False, 
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # إشعارات العميل الخاصة + الإشعارات العامة
        notifications = Notification.objects.filter(
            Q(customer=customer) | Q(customer__isnull=True)
        ).order_by('-created_at')[:20]
        
        return Response({
            'success': True,
            'notifications': [
                {
                    'id': n.id,
                    'title': n.title,
                    'description': n.description,
                    'type': n.notification_type,
                    'is_read': n.is_read,
                    'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
                }
                for n in notifications
            ],
            'unread_count': notifications.filter(is_read=False).count(),
        })


class MarkNotificationReadAPI(APIView, JWTAuthMixin):
    """تحديث حالة الإشعار كمقروء"""
    def post(self, request, notification_id):
        customer = self.get_customer(request)
        if not customer:
            return Response({
                'success': False, 
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            notification = Notification.objects.get(
                id=notification_id,
                customer=customer
            )
            notification.is_read = True
            notification.save()
            
            return Response({
                'success': True,
                'message': 'تم تحديث حالة الإشعار'
            })
        except Notification.DoesNotExist:
            return Response({
                'success': False,
                'message': 'الإشعار غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
