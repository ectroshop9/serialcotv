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

def create_admin(request):
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@serialco.tv', 'Admin123456')
        return HttpResponse('✅ Admin created')
    return HttpResponse('⚠️ Admin already exists')

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('create-admin/', create_admin, name='create-admin'),
    
    # ⭐ مسارات API
    path('api/accounts/', include('accounts.urls')),
    path('api/content/', include('content.urls')),
    path('api/serials/', include('serials.urls')),

    # ⭐ Health Check
    path('api/health/', lambda r: JsonResponse({
        'status': 'healthy',
        'service': 'serialco-api',
        'timestamp': datetime.now().isoformat()
    }), name='api-health'),
]
