from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Category, Product, Order, OrderItem

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

class CreateOrderAPI(APIView):
    def post(self, request):
        full_name = request.data.get('full_name')
        phone = request.data.get('phone')
        address = request.data.get('address')
        notes = request.data.get('notes', '')
        items = request.data.get('items', [])
        
        if not all([full_name, phone, address, items]):
            return Response({'success': False, 'message': 'جميع الحقول مطلوبة'}, status=400)
        
        total = 0
        order = Order.objects.create(
            full_name=full_name,
            phone=phone,
            address=address,
            notes=notes,
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
        
        return Response({
            'success': True,
            'message': 'تم استلام طلبك، سيتم التواصل معك قريباً',
            'order_id': order.id
        })
