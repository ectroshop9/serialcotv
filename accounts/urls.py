from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.CustomerLoginAPI.as_view(), name='api_login'),
    path('register/', views.RegisterAPI.as_view(), name='api_register'),
    path('profile/', views.UserProfileAPI.as_view(), name='api_profile'),
    path('account-status/', views.AccountStatusAPI.as_view(), name='api_account_status'),
    path('update-profile/', views.UpdateProfileAPI.as_view(), name='api_update_profile'),
    path('validate-token/', views.ValidateTokenAPI.as_view(), name='api_validate_token'),
    path('notifications/', views.NotificationListAPI.as_view(), name='api_notifications'),
    path('notifications/<int:notification_id>/read/', views.MarkNotificationReadAPI.as_view(), name='api_mark_notification_read'),
]
