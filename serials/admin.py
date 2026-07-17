from django.contrib import admin
from .models import SerialPackage, SerialKey, SerialUsage

@admin.register(SerialPackage)
class SerialPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'downloads_limit', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(SerialKey)
class SerialKeyAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'package', 'downloads_remaining', 'downloads_used', 'is_active', 'is_used_up', 'customer')
    list_filter = ('is_active', 'is_used_up', 'package')
    search_fields = ('serial_number', 'customer__name')
    readonly_fields = ('serial_number', 'pin', 'downloads_total', 'downloads_used', 'downloads_remaining')

@admin.register(SerialUsage)
class SerialUsageAdmin(admin.ModelAdmin):
    list_display = ('serial_key', 'customer', 'file_name', 'file_type', 'downloads_before', 'downloads_after', 'created_at')
    list_filter = ('file_type', 'created_at')
    search_fields = ('serial_key__serial_number', 'customer__name', 'file_name')
    readonly_fields = ('downloads_before', 'downloads_after')
