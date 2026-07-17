from django.urls import path
from . import views

urlpatterns = [
    # TV Brands
    path('brands/', views.BrandListAPI.as_view(), name='brands'),
    
    # TV Models
    path('models/', views.ModelListAPI.as_view(), name='models'),
    
    # Firmware
    path('firmware/', views.FirmwareListAPI.as_view(), name='firmware-list'),
    path('firmware/<int:pk>/', views.FirmwareDetailAPI.as_view(), name='firmware-detail'),
    
    # Schematics
    path('schematics/', views.SchematicListAPI.as_view(), name='schematics-list'),
    path('schematics/<int:pk>/', views.SchematicDetailAPI.as_view(), name='schematics-detail'),
]
