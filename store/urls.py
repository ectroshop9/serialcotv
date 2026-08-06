from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.CategoryListAPI.as_view(), name='store-categories'),
    path('products/', views.ProductListAPI.as_view(), name='store-products'),
    path('products/<int:pk>/', views.ProductDetailAPI.as_view(), name='store-product-detail'),
    path('wilayas/', views.WilayaListAPI.as_view(), name='store-wilayas'),
    path('shipping-fee/', views.ShippingFeeAPI.as_view(), name='store-shipping-fee'),
    path('orders/', views.CreateOrderAPI.as_view(), name='store-create-order'),
    path('orders/<int:order_id>/track/', views.TrackOrderAPI.as_view(), name='store-track-order'),
]