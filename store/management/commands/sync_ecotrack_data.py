import requests
from django.core.management.base import BaseCommand
from decouple import config
from store.models import Wilaya, ShippingFee

class Command(BaseCommand):
    help = 'مزامنة الولايات والأسعار من ECOTRACK API'
    
    ECOTRACK_URL = config('ECOTRACK_API_URL', default='https://platform.dhd-dz.com/api/v1/get/fees')
    API_TOKEN = config('ECOTRACK_API_TOKEN', default='')
    
    def handle(self, *args, **options):
        if not self.API_TOKEN:
            self.stdout.write(self.style.ERROR('❌ ECOTRACK_API_TOKEN غير موجود في ملف .env'))
            return
        
        self.stdout.write('جاري جلب البيانات من ECOTRACK...')
        
        headers = {
            'Authorization': f'Bearer {self.API_TOKEN}'
        }
        
        try:
            response = requests.get(self.ECOTRACK_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            self.process_fees(data.get('livraison', []), 'livraison')
            self.process_fees(data.get('recouvrement', []), 'recouvrement')
            self.process_fees(data.get('retours', []), 'retour')
            
            self.stdout.write(self.style.SUCCESS('✅ تمت المزامنة بنجاح!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ خطأ: {str(e)}'))
    
    def process_fees(self, fees_data, service_type):
        for item in fees_data:
            wilaya_id = item['wilaya_id']
            
            wilaya, created = Wilaya.objects.get_or_create(
                wilaya_id=wilaya_id,
                defaults={
                    'name_ar': f'ولاية {wilaya_id}',
                    'name_fr': f'Wilaya {wilaya_id}',
                    'has_stopdesk': int(item.get('tarif_stopdesk', 0)) > 0
                }
            )
            
            ShippingFee.objects.update_or_create(
                wilaya=wilaya,
                service_type=service_type,
                defaults={
                    'tarif_domicile': item['tarif'],
                    'tarif_stopdesk': item.get('tarif_stopdesk', 0)
                }
            )
