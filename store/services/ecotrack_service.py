import requests
from decouple import config
from store.models import EcotrackShipment

class EcotrackService:
    BASE_URL = config('ECOTRACK_API_URL', default='https://platform.dhd-dz.com/api/v1')
    API_TOKEN = config('ECOTRACK_API_TOKEN', default='')
    
    @classmethod
    def get_headers(cls):
        return {
            'Authorization': f'Bearer {cls.API_TOKEN}',
            'Content-Type': 'application/json'
        }
    
    @classmethod
    def create_order(cls, order):
        """إرسال طلب توصيل إلى ECOTRACK"""
        
        # تجهيز المنتجات كنص
        products_text = ", ".join([
            f"{item.product.name} x{item.quantity}" 
            for item in order.items.all()
        ])
        
        payload = {
            "reference": str(order.id),
            "client": order.full_name,
            "phone": order.phone,
            "adresse": order.address,
            "wilaya_id": order.wilaya.wilaya_id if order.wilaya else None,
            "montant": float(order.total_price + order.shipping_cost),
            "products": products_text,
            "notes": order.notes or ""
        }
        
        try:
            response = requests.post(
                f"{cls.BASE_URL}/add-order",
                json=payload,
                headers=cls.get_headers()
            )
            response.raise_for_status()
            
            data = response.json()
            
            # حفظ معلومات الشحنة
            shipment, created = EcotrackShipment.objects.get_or_create(
                order=order,
                defaults={
                    'ecotrack_id': data.get('id'),
                    'tracking_number': data.get('tracking'),
                    'status': 'created'
                }
            )
            
            if not created and not shipment.tracking_number:
                shipment.tracking_number = data.get('tracking')
                shipment.ecotrack_id = data.get('id')
                shipment.save()
            
            return {
                'success': True,
                'tracking': data.get('tracking'),
                'ecotrack_id': data.get('id')
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @classmethod
    def get_orders_status(cls, tracking=None, page=1):
        """جلب حالة الطلبات من ECOTRACK"""
        try:
            params = {'page': page}
            if tracking:
                params['tracking'] = tracking
            
            response = requests.get(
                f"{cls.BASE_URL}/get/orders",
                params=params,
                headers=cls.get_headers()
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {'error': str(e)}
    
    @classmethod
    def track_shipment(cls, tracking_number):
        """تتبع شحنة محددة"""
        return cls.get_orders_status(tracking=tracking_number)
