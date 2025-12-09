# accounts/authentication.py
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from django.contrib.auth.models import User
from .models import Customer

class CustomerJWTAuthentication(BaseAuthentication):
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
            if customer_id:
                customer = Customer.objects.get(id=customer_id, is_active=True)
                if customer.user:
                    return (customer.user, token)
            
            return None
                
        except Exception:
            return None
