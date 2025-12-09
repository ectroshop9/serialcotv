from django.contrib import admin
from .models import Source, Customer, Wallet, Transaction

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix', 'is_active')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'serial', 'is_active')

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('customer', 'balance')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'transaction_type', 'amount')

# ⭐ التسجيل البسيط للباقي
#admin.site.register(BotRegistration)
admin.site.register(JWTAuditLog)
