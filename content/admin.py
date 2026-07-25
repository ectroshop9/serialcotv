from django.contrib import admin
from .models import TVBrand, TVModel, Firmware, Schematic, DownloadToken  # ← أضف DownloadToken

@admin.register(TVBrand)
class TVBrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(TVModel)
class TVModelAdmin(admin.ModelAdmin):
    list_display = ('brand', 'model_number', 'chassis', 'screen_size', 'is_active')
    list_filter = ('brand', 'is_active')
    search_fields = ('model_number', 'chassis', 'brand__name')

@admin.register(Firmware)
class FirmwareAdmin(admin.ModelAdmin):
    list_display = ('model', 'version', 'token_cost', 'downloads_count', 'is_active')
    list_filter = ('is_active', 'model__brand')
    search_fields = ('model__model_number', 'model__brand__name', 'version')

@admin.register(Schematic)
class SchematicAdmin(admin.ModelAdmin):
    list_display = ('model', 'title', 'schematic_type', 'token_cost', 'downloads_count', 'is_active')
    list_filter = ('schematic_type', 'is_active', 'model__brand')
    search_fields = ('title', 'model__model_number', 'model__brand__name')

@admin.register(DownloadToken)
class DownloadTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'file_name', 'customer', 'used', 'created_at', 'expires_at')
    list_filter = ('used',)
    search_fields = ('token', 'file_name', 'customer__email')
    readonly_fields = ('token', 'created_at', 'expires_at')

admin.site.site_header = 'SerialCo TV Admin'
admin.site.site_title = 'SerialCo TV'
admin.site.index_title = 'Dashboard'