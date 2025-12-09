from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum
from .models import Source, Customer, Wallet, Transaction, BotRegistration, JWTAuditLog

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('prefix_display', 'name', 'customer_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'prefix')
    search_fields = ('name', 'prefix', 'bot_username')
    readonly_fields = ('created_at',)

    def prefix_display(self, obj):
        color_map = {
            'T': '#0088cc',  # أزرق تليجرام
            'S': '#28a745',  # أخضر المتجر
            'M': '#0068d5',  # أزرق مسنجر
            'W': '#25D366',  # أخضر واتساب
            'A': '#dc3545',  # أحمر إداري
            'U': '#6c757d',  # رمادي
        }
        color = color_map.get(obj.prefix, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-weight: bold;">{}</span>',
            color,
            obj.get_prefix_display()
        )
    prefix_display.short_description = 'المصدر'

    def customer_count(self, obj):
        count = obj.customers.count()
        return format_html(
            '<span style="font-weight: bold;">{}</span> عميل',
            count
        )
    customer_count.short_description = 'عدد العملاء'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'serial_display', 'source_display',
                    'balance_display', 'is_active', 'created_at')
    search_fields = ('name', 'phone', 'serial')
    list_filter = ('is_active', 'source', 'created_at')
    readonly_fields = ('serial', 'pin', 'created_at', 'total_referrals', 'referral_earnings')
    ordering = ('-created_at',)

    def serial_display(self, obj):
        color_map = {
            'T': '#0088cc', 'S': '#28a745', 'M': '#0068d5',
            'W': '#25D366', 'A': '#dc3545', 'U': '#6c757d'
        }
        prefix = obj.serial[0] if obj.serial else 'U'
        color = color_map.get(prefix, '#6c757d')
        return format_html(
            '<code style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px;">{}</code>',
            color,
            obj.serial
        )
    serial_display.short_description = 'السيريال'
    serial_display.admin_order_field = 'serial'

    def source_display(self, obj):
        if obj.source:
            return format_html(
                '<span style="font-weight: bold; color: #{};">{}</span>',
                '0088cc' if obj.source.prefix == 'T' else
                '28a745' if obj.source.prefix == 'S' else
                '0068d5' if obj.source.prefix == 'M' else
                '25D366' if obj.source.prefix == 'W' else
                'dc3545' if obj.source.prefix == 'A' else '6c757d',
                obj.source.get_prefix_display()
            )
        return '-'
    source_display.short_description = 'المصدر'

    def balance_display(self, obj):
        try:
            wallet = Wallet.objects.get(customer=obj)
            color = 'green' if wallet.balance > 0 else 'orange' if wallet.balance == 0 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{} ⭐</span>',
                color,
                wallet.balance
            )
        except Wallet.DoesNotExist:
            return format_html('<span style="color: gray;">0 ⭐</span>')
    balance_display.short_description = 'الرصيد'
    balance_display.admin_order_field = 'wallet__balance'

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'balance', 'total_deposited', 'updated_at')
    search_fields = ('customer__name', 'customer__phone', 'customer__serial')
    list_filter = ('updated_at',)
    readonly_fields = ('created_at', 'updated_at')

    def customer_link(self, obj):
        url = reverse('admin:accounts_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'العميل'
    customer_link.admin_order_field = 'customer__name'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'transaction_type_display',
                    'amount_display', 'source_display', 'description_short', 'created_at')
    list_filter = ('transaction_type', 'source', 'created_at')
    search_fields = ('customer__name', 'customer__phone', 'customer__serial', 'description')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

    def customer_link(self, obj):
        url = reverse('admin:accounts_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'العميل'
    customer_link.admin_order_field = 'customer__name'

    def transaction_type_display(self, obj):
        return obj.get_transaction_type_display()
    transaction_type_display.short_description = 'نوع العملية'

    def amount_display(self, obj):
        color = 'green' if obj.amount > 0 else 'red' if obj.amount < 0 else 'gray'
        sign = '+' if obj.amount > 0 else '' if obj.amount == 0 else '-'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{} ⭐</span>',
            color,
            sign,
            abs(obj.amount)
        )
    amount_display.short_description = 'المبلغ'
    amount_display.admin_order_field = 'amount'

    def source_display(self, obj):
        if obj.source:
            return format_html(
                '<span style="color: #{};">{}</span>',
                '0088cc' if obj.source.prefix == 'T' else
                '28a745' if obj.source.prefix == 'S' else
                '0068d5' if obj.source.prefix == 'M' else
                '25D366' if obj.source.prefix == 'W' else
                'dc3545' if obj.source.prefix == 'A' else '6c757d',
                obj.source.get_prefix_display()
            )
        return '-'
    source_display.short_description = 'المصدر'

    def description_short(self, obj):
        if len(obj.description) > 50:
            return obj.description[:50] + '...'
        return obj.description
    description_short.short_description = 'الوصف'

@admin.register(BotRegistration)
class BotRegistrationAdmin(admin.ModelAdmin):
    list_display = ('source', 'customer_link', 'telegram_username', 'created_at')
    list_filter = ('source', 'created_at')
    search_fields = ('customer__name', 'telegram_username')
    readonly_fields = ('created_at',)

    def customer_link(self, obj):
        url = reverse('admin:accounts_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'العميل'

@admin.register(JWTAuditLog)
class JWTAuditLogAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'action', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('customer__name', 'customer__serial', 'action')
    readonly_fields = ('created_at',)

    def customer_link(self, obj):
        url = reverse('admin:accounts_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'العميل'

# تخصيص عنوان لوحة الإدارة
admin.site.site_header = "📊 إدارة نظام العملاء بالمصادر"
admin.site.site_title = "نظام المصادر"
admin.site.index_title = "لوحة التحكم - إحصائيات المصادر"
