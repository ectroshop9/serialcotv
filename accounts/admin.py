from django.contrib import admin
from .models import Source, Customer, Transaction

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'is_active')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'is_active', 'last_login')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'transaction_type', 'amount', 'created_at')
