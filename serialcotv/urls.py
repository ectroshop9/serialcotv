from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse, JsonResponse
from datetime import datetime
from django.contrib.auth.models import User

def home(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>SerialCo TV API</title></head>
    <body>
        <h1>🚀 SerialCo TV API</h1>
        <p>نظام السيريالات</p>
        <p>📞 الدعم: @serialco_support</p>
    </body>
    </html>
    """)

def reset_admin(request):
    if User.objects.filter(username='admin').exists():
        user = User.objects.get(username='admin')
        user.set_password('Admin123456')
        user.is_active = True
        user.save()
        return HttpResponse('✅ Password reset to Admin123456')
    return HttpResponse('⚠️ User not found')

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('reset-admin/', reset_admin, name='reset-admin'),
    path('api/accounts/', include('accounts.urls')),
    path('api/content/', include('content.urls')),
    path('api/serials/', include('serials.urls')),
    path('api/health/', lambda r: JsonResponse({'status': 'healthy'}), name='api-health'),
]
    # ⭐ Health Check
    path('api/health/', lambda r: JsonResponse({
        'status': 'healthy',
        'service': 'serialco-api',
        'timestamp': datetime.now().isoformat()
    }), name='api-health'),
]
