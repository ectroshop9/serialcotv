from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse, JsonResponse
from datetime import datetime

def home(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>SerialCo TV API</title></head>
    <body>
        <h1>🚀 SerialCo TV API</h1>
        <p>نظام السيريالات - SQLite</p>
        <p>📞 الدعم: @serialco_support</p>
    </body>
    </html>
    """)

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    
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