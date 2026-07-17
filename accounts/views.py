from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import jwt
from datetime import datetime, timedelta
from django.conf import settings
from .models import Customer, Transaction, Source

class CustomerJWTAuthentication:
    pass

class JWTAuthMixin:
    authentication_classes = []
    permission_classes = [IsAuthenticated]
    
    def get_customer(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                return Customer.objects.get(user=request.user, is_active=True)
            except Customer.DoesNotExist:
                pass
        return None

class RegisterAPI(APIView):
    def post(self, request):
        name = request.data.get('name')
        phone = request.data.get('phone')
        
        if not name or not phone:
            return Response({
                'success': False,
                'message': 'الاسم ورقم الهاتف مطلوبان'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if Customer.objects.filter(phone=phone).exists():
            return Response({
                'success': False,
                'message': 'رقم الهاتف مسجل مسبقاً'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        customer = Customer.objects.create(
            name=name.strip(),
            phone=phone
        )
        
        jwt_token = customer.generate_jwt_token()
        
        return Response({
            'success': True,
            'message': 'تم إنشاء الحساب بنجاح',
            'access_token': jwt_token,
            'token_type': 'bearer',
            'expires_in': 2592000,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
            }
        })

class CustomerLoginAPI(APIView):
    def post(self, request):
        phone = request.data.get('phone')
        
        if not phone:
            return Response({
                'success': False,
                'message': 'يرجى إدخال رقم الهاتف'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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

class UserProfileAPI(APIView, JWTAuthMixin):
    def get(self, request):
        customer = self.get_customer(request)
        
        if not customer:
            return Response({
                'success': False,
                'message': 'المصادقة مطلوبة'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'is_active': customer.is_active,
                'created_at': customer.created_at,
                'last_login': customer.last_login,
            }
        })

class AccountStatusAPI(APIView, JWTAuthMixin):
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
            'name': customer.name
        })

class ValidateTokenAPI(APIView):
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
            customer = Customer.objects.get(id=customer_id, is_active=True)
            
            return Response({
                'success': True,
                'valid': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name
                }
            })
        except:
            return Response({
                'success': False,
                'valid': False,
                'message': 'توكن غير صالح'
            }, status=401)

class UpdateProfileAPI(APIView, JWTAuthMixin):
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
        
        customer.name = name.strip()
        customer.save()
        
        return Response({
            'success': True,
            'message': 'تم تحديث الاسم بنجاح',
            'new_name': customer.name
        })
