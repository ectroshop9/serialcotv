# accounts/authentication.py
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from django.contrib.auth.models import User
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
            
            # إرفاق التوكن مع الطلب
            request.jwt_token = token
            request.jwt_payload = payload
            
            # إرجاع المستخدم والتوكن
            return (customer.user if customer.user else None, token)
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Customer.DoesNotExist):
            return None
