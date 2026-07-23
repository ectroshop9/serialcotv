import jwt
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import authentication
from rest_framework.authentication import BaseAuthentication
from .models import Customer


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
            
            # إذا العميل مرتبط بحساب Django User نستخدمه، وإلا نستخدم العميل نفسه
            user = customer.user if customer.user else User.objects.get_or_create(
                username=f"customer_{customer.id}",
                defaults={'is_active': True}
            )[0]
            
            # تحديث آخر دخول
            from django.utils import timezone
            customer.last_login = timezone.now()
            customer.save(update_fields=['last_login'])
            
            # إرفاق التوكن مع الطلب
            request.jwt_token = token
            request.jwt_payload = payload
            request.customer = customer
            
            # إرجاع المستخدم والتوكن
            return (user, token)
            
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Customer.DoesNotExist:
            return None
    
    def authenticate_header(self, request):
        return 'Bearer realm="api"'
