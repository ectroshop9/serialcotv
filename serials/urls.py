from django.urls import path
from . import views

urlpatterns = [
    path('check/', views.CheckSerialAPI.as_view(), name='check-serial'),
    path('activate/', views.ActivateSerialAPI.as_view(), name='activate-serial'),
    path('use-download/', views.UseSerialDownloadAPI.as_view(), name='use-download'),
]
