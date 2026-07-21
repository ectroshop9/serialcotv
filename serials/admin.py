from django.contrib import admin
from .models import SerialPackage, SerialKey, SerialUsage

@admin.action(description="توليد سيريالات بالجملة")
def bulk_generate_serials(modeladmin, request, queryset):
    for package in queryset:
        count = 10
        for _ in range(count):
            SerialKey.objects.create(
                package=package,
                tokens_total=package.tokens_limit,
                tokens_used=0,
                tokens_remaining=package.tokens_limit,
            )
    modeladmin.message_user(request, f"تم توليد {count} سيريال بنجاح")

@admin.register(SerialPackage)
class SerialPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'tokens_limit', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    actions = [bulk_generate_serials]

@admin.register(SerialKey)
class SerialKeyAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'package', 'tokens_remaining', 'tokens_used', 'is_active', 'is_used_up', 'customer')
    list_filter = ('is_active', 'is_used_up', 'package')
    search_fields = ('serial_number', 'customer__name')
    readonly_fields = ('serial_number', 'pin', 'tokens_total', 'tokens_used', 'tokens_remaining')

@admin.register(SerialUsage)
class SerialUsageAdmin(admin.ModelAdmin):
    list_display = ('serial_key', 'customer', 'file_name', 'file_type', 'tokens_before', 'tokens_after', 'created_at')
    list_filter = ('file_type', 'created_at')
    search_fields = ('serial_key__serial_number', 'customer__name', 'file_name')
    readonly_fields = ('tokens_before', 'tokens_after')