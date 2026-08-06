from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Category, Product, Order, OrderItem, Wilaya, ShippingFee


class CategoryListAPI(APIView):
    def get(self, request):
        categories = Category.objects.filter(is_active=True).values('id', 'name')
        return Response({'success': True, 'categories': list(categories)})


class ProductListAPI(APIView):
    def get(self, request):
        category_id = request.query_params.get('category')
        product_type = request.query_params.get('type')
        
        products = Product.objects.filter(is_active=True)
        if category_id:
            products = products.filter(category_id=category_id)
        if product_type:
            products = products.filter(product_type=product_type)
        
        data = products.values('id', 'name', 'price', 'product_type', 'image', 'category__name')
        return Response({'success': True, 'products': list(data)})


class ProductDetailAPI(APIView):
    def get(self, request, pk):
        try:
            product = Product.objects.get(pk=pk, is_active=True)
            return Response({
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'description': product.description,
                    'price': str(product.price),
                    'product_type': product.product_type,
                    'image': product.image.url if product.image else None,
                    'stock': product.stock,
                    'category': product.category.name if product.category else None,
                }
            })
        except Product.DoesNotExist:
            return Response({'success': False, 'message': 'المنتج غير موجود'}, status=404)


class WilayaListAPI(APIView):
    def get(self, request):
        wilayas = Wilaya.objects.filter(is_active=True).values('wilaya_id', 'name_ar', 'has_stopdesk')
        return Response({'success': True, 'wilayas': list(wilayas)})


class ShippingFeeAPI(APIView):
    def get(self, request):
        wilaya_id = request.query_params.get('wilaya_id')
        
        if not wilaya_id:
            return Response({'success': False, 'message': 'wilaya_id مطلوب'}, status=400)
        
        try:
            fee = ShippingFee.objects.get(
                wilaya__wilaya_id=wilaya_id,
                service_type='livraison'
            )
            return Response({
                'success': True,
                'fees': {
                    'domicile': str(fee.tarif_domicile),
                    'stopdesk': str(fee.tarif_stopdesk),
                }
            })
        except ShippingFee.DoesNotExist:
            return Response({'success': False, 'message': 'الولاية غير متوفرة'}, status=404)


class CreateOrderAPI(APIView):
    def post(self, request):
        full_name = request.data.get('full_name')
        phone = request.data.get('phone')
        wilaya_id = request.data.get('wilaya_id')
        address = request.data.get('address')
        shipping_type = request.data.get('shipping_type', 'domicile')
        notes = request.data.get('notes', '')
        items = request.data.get('items', [])
        
        if not all([full_name, phone, address, items]):
            return Response({'success': False, 'message': 'جميع الحقول مطلوبة'}, status=400)
        
        # التحقق من نوع المنتجات
        has_physical = False
        wilaya = None
        shipping_cost = 0
        
        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'], is_active=True)
                if product.product_type == 'physical':
                    has_physical = True
                    break
            except Product.DoesNotExist:
                continue
        
        # إذا فيه منتجات مادية، نحتاج ولاية
        if has_physical:
            if not wilaya_id:
                return Response({'success': False, 'message': 'الولاية مطلوبة للمنتجات المادية'}, status=400)
            
            try:
                wilaya = Wilaya.objects.get(wilaya_id=wilaya_id, is_active=True)
                fee = ShippingFee.objects.get(wilaya=wilaya, service_type='livraison')
                shipping_cost = fee.tarif_stopdesk if shipping_type == 'stopdesk' else fee.tarif_domicile
            except Wilaya.DoesNotExist:
                return Response({'success': False, 'message': 'الولاية غير موجودة'}, status=400)
            except ShippingFee.DoesNotExist:
                return Response({'success': False, 'message': 'الشحن غير متوفر لهذه الولاية'}, status=400)
        
        # إنشاء الطلب
        total = 0
        order = Order.objects.create(
            customer=request.user if request.user.is_authenticated else None,
            full_name=full_name,
            phone=phone,
            wilaya=wilaya,
            address=address,
            notes=notes,
            shipping_cost=shipping_cost,
            shipping_type=shipping_type if has_physical else 'domicile',
            total_price=0
        )
        
        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'], is_active=True)
                qty = int(item.get('quantity', 1))
                price = product.price * qty
                total += price
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price=price
                )
            except Product.DoesNotExist:
                continue
        
        order.total_price = total
        order.save()
        
        response_data = {
            'success': True,
            'message': 'تم استلام طلبك، سيتم التواصل معك قريباً',
            'order_id': order.id
        }
        
        # إضافة tracking إذا تم الإرسال لـ ECOTRACK
        if has_physical and hasattr(order, 'ecotrack_shipment'):
            response_data['tracking_number'] = order.ecotrack_shipment.tracking_number
        
        return Response(response_data)


class TrackOrderAPI(APIView):
    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            
            if hasattr(order, 'ecotrack_shipment'):
                shipment = order.ecotrack_shipment
                return Response({
                    'success': True,
                    'order': {
                        'id': order.id,
                        'status': order.status,
                        'tracking_number': shipment.tracking_number,
                        'shipment_status': shipment.status
                    }
                })
            
            return Response({
                'success': True,
                'order': {
                    'id': order.id,
                    'status': order.status,
                    'tracking_number': None
                }
            })
            
        except Order.DoesNotExist:
            return Response({'success': False, 'message': 'الطلب غير موجود'}, status=404)