from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def home(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>SerialCo TV API</title></head>
    <body>
        <h1>SerialCo TV API</h1>
        <p>Serial System</p>
    </body>
    </html>
    """)

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/content/', include('content.urls')),
    path('api/serials/', include('serials.urls')),
]
