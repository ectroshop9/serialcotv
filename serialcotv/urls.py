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
    </body>
    </html>
    """)

@csrf_exempt
def jwt_login(request):
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

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    
    # Token القديم
    path('api/auth-token/', auth_views.obtain_auth_token, name='api-token-auth'),
    
    # JWT التوافق
    path('api/jwt/login/', jwt_login, name='jwt-login'),
    
    # ⭐⭐ مسارات API الجديدة ⭐⭐
    path('api/accounts/', include('accounts.urls')),
    
    # ⭐⭐ Health Check ⭐⭐
    path('api/health/', lambda r: JsonResponse({
        'status': 'healthy',
        'service': 'serialco-api',
        'timestamp': datetime.now().isoformat()
    }), name='api-health'),
]
