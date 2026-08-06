from django.contrib import admin
from .models import Category, Product, Order, OrderItem, Wilaya, ShippingFee, EcotrackShipment

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

class EcotrackShipmentInline(admin.TabularInline):
    model = EcotrackShipment
    extra = 0
    can_delete = False
    fields = ('tracking_number', 'status', 'ecotrack_id')
    readonly_fields = ('tracking_number', 'status', 'ecotrack_id')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'product_type', 'stock', 'is_active')
    list_filter = ('product_type', 'is_active', 'category')
    search_fields = ('name',)

@admin.register(Wilaya)
class WilayaAdmin(admin.ModelAdmin):
    list_display = ('wilaya_id', 'name_ar', 'has_stopdesk', 'is_active')
    list_filter = ('has_stopdesk', 'is_active')
    search_fields = ('name_ar', 'wilaya_id')

@admin.register(ShippingFee)
class ShippingFeeAdmin(admin.ModelAdmin):
    list_display = ('wilaya', 'service_type', 'tarif_domicile', 'tarif_stopdesk')
    list_filter = ('service_type',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone', 'wilaya', 'shipping_type', 'total_price', 'shipping_cost', 'status', 'created_at')
    list_filter = ('status', 'shipping_type', 'wilaya')
    search_fields = ('full_name', 'phone', 'id')
    inlines = [OrderItemInline, EcotrackShipmentInline]
    readonly_fields = ('created_at',)