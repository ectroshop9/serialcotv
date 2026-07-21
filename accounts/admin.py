from django.contrib import admin
from .models import Source, Customer, Transaction, Notification

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'is_active')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'token_balance', 'is_active', 'last_login')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'transaction_type', 'amount', 'created_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'notification_type', 'customer', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'description')