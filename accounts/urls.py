# accounts/urls.py - المصحح
from django.urls import path
from . import views  # ⭐ تصحيح: views بدلاً من api_views

urlpatterns = [
    # ⭐ مسارات المصادقة
    path('login/', views.CustomerLoginAPI.as_view(), name='api_login'),
    path('register/', views.RegisterAPI.as_view(), name='api_register'),
    
    # ⭐ المسارات المحمية بـ JWT
    path('profile/', views.UserProfileAPI.as_view(), name='api_profile'),
    path('wallet/', views.WalletAPI.as_view(), name='api_wallet'),
    path('account-status/', views.AccountStatusAPI.as_view(), name='api_account_status'),
    
    # ⭐ المسارات الخاصة
    path('recover-serial/', views.RecoverSerialAPI.as_view(), name='api_recover_serial'),
    path('change-pin/', views.ChangePINAPI.as_view(), name='api_change_pin'),
    path('purchase/', views.PurchaseAPI.as_view(), name='api_purchase'),
    path('update-profile/', views.UpdateProfileAPI.as_view(), name='api_update_profile'),
    
    # ⭐ مسارات الإحالة
    path('referral-stats/', views.ReferralStatsAPI.as_view(), name='api_referral_stats'),
    path('check-phone/', views.CheckPhoneAPI.as_view(), name='api_check_phone'),
    
    # ⭐ مسارات الإدارة (للمسؤولين)
    path('source-stats/', views.SourceStatsAPI.as_view(), name='api_source_stats'),
    path('dashboard-stats/', views.DashboardStatsAPI.as_view(), name='api_dashboard_stats'),
    path('charge-wallet/', views.ChargeWalletAPI.as_view(), name='api_charge_wallet'),
    
    # ⭐ مسارات JWT الإضافية
    path('validate-token/', views.ValidateTokenAPI.as_view(), name='api_validate_token'),
    path('refresh-token/', views.RefreshTokenAPI.as_view(), name='api_refresh_token'),
    
    # ⭐ Health check للتطبيق
    path('health/', views.HealthCheckAPI.as_view(), name='api_health'),
]
