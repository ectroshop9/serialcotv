from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken import views as auth_views
import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from datetime import datetime, timedelta

def home(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>SerialCo TV API</title></head>
    <body>
        <h1>🚀 SerialCo TV API - Render</h1>
        <p>JWT نظام محدث - PostgreSQL</p>
        <p>📞 الدعم: @serialco_support</p>
        <p>📊 Health: <a href="/api/health/">/api/health/</a></p>
        <p>🔧 Test: <a href="/api/test/">/api/test/</a></p>
    </body>
    </html>
    """)

@csrf_exempt
def jwt_login(request):
    """JWT login endpoint للتوافق"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(username=username, password=password)
        
        if user:
            payload = {
                'user_id': user.id,
                'username': user.username,
                'exp': datetime.utcnow() + timedelta(hours=24),
                'iat': datetime.utcnow()
            }
            
            token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
            
            return JsonResponse({
                'access_token': token,
                'token_type': 'bearer',
                'expires_in': 86400,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            })
        
        return JsonResponse({'error': 'بيانات الدخول غير صحيحة'}, status=401)
    
    return JsonResponse({'error': 'يجب استخدام POST'}, status=400)

@csrf_exempt
def validate_jwt(request):
    """التحقق من JWT token"""
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'valid': False, 'error': 'لا يوجد توكن'}, status=400)
    
    token = auth_header[7:]
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return JsonResponse({
            'valid': True,
            'user_id': payload['user_id'],
            'username': payload['username']
        })
    except jwt.ExpiredSignatureError:
        return JsonResponse({'valid': False, 'error': 'انتهت صلاحية التوكن'}, status=401)
    except:
        return JsonResponse({'valid': False, 'error': 'توكن غير صالح'}, status=401)

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    
    # Token القديم (للتوافق)
    path('api/auth-token/', auth_views.obtain_auth_token, name='api-token-auth'),
    
    # JWT التوافق
    path('api/jwt/login/', jwt_login, name='jwt-login'),
    path('api/jwt/validate/', validate_jwt, name='jwt-validate'),
    
    # ⭐⭐ مسارات API الجديدة ⭐⭐
    path('api/accounts/', include('accounts.urls')),  # ⭐ API العملاء الجديد
    
    # ⭐⭐ Health Check للـ Render ⭐⭐
    path('api/health/', lambda r: JsonResponse({
        'status': 'healthy',
        'service': 'serialco-api',
        'database': 'postgresql',
        'jwt': True,
        'timestamp': datetime.now().isoformat()
    }), name='api-health'),
    
    # ⭐⭐ Test Page ⭐⭐
    path('api/test/', lambda r: JsonResponse({
        'api': 'SerialCo TV API',
        'version': '2.0',
        'database': 'PostgreSQL',
        'environment': 'production' if not settings.DEBUG else 'development',
        'endpoints': {
            'accounts': {
                'login': '/api/accounts/login/',
                'register': '/api/accounts/register/',
                'profile': '/api/accounts/profile/',
                'wallet': '/api/accounts/wallet/'
            },
            'system': {
                'admin': '/admin/',
                'health': '/api/health/',
                'jwt_login': '/api/jwt/login/'
            }
        }
    }), name='api-test'),
    
    # ⭐⭐ Admin Customization ⭐⭐
    path('admin/accounts/', include('accounts.admin_urls', namespace='accounts_admin')),
]
