from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import SerialKey, SerialPackage, SerialUsage

class CheckSerialAPI(APIView):
    """فحص السيريال والبين"""
    
    def post(self, request):
        serial_number = request.data.get('serial')
        pin = request.data.get('pin')
        
        if not serial_number or not pin:
            return Response({
                'success': False,
                'message': 'يرجى إدخال السيريال والبين'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            serial_key = SerialKey.objects.get(
                serial_number=serial_number,
                pin=pin
            )
            
            if serial_key.is_used_up:
                return Response({
                    'success': False,
                    'message': 'السيريال منتهي',
                    'serial': {
                        'number': serial_key.serial_number,
                        'package': serial_key.package.name,
                        'downloads_total': serial_key.downloads_total,
                        'downloads_used': serial_key.downloads_used,
                        'downloads_remaining': 0,
                        'status': 'منتهي'
                    }
                })
            
            return Response({
                'success': True,
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name,
                    'downloads_total': serial_key.downloads_total,
                    'downloads_used': serial_key.downloads_used,
                    'downloads_remaining': serial_key.downloads_remaining,
                    'status': 'شغال' if serial_key.is_active else 'غير مفعل'
                }
            })
            
        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال أو البين غير صحيح'
            }, status=status.HTTP_404_NOT_FOUND)


class ActivateSerialAPI(APIView):
    """تفعيل السيريال للعميل"""
    
    def post(self, request):
        serial_number = request.data.get('serial')
        pin = request.data.get('pin')
        customer_id = request.data.get('customer_id')
        
        if not all([serial_number, pin, customer_id]):
            return Response({
                'success': False,
                'message': 'جميع الحقول مطلوبة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            serial_key = SerialKey.objects.get(
                serial_number=serial_number,
                pin=pin,
                customer__isnull=True
            )
            
            from accounts.models import Customer
            customer = get_object_or_404(Customer, id=customer_id, is_active=True)
            
            serial_key.customer = customer
            serial_key.used_at = timezone.now()
            serial_key.save()
            
            return Response({
                'success': True,
                'message': 'تم تفعيل السيريال بنجاح',
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name,
                    'downloads_remaining': serial_key.downloads_remaining,
                }
            })
            
        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو مستخدم مسبقاً'
            }, status=status.HTTP_404_NOT_FOUND)


class UseSerialDownloadAPI(APIView):
    """استخدام السيريال للتحميل"""
    
    def post(self, request):
        serial_number = request.data.get('serial')
        pin = request.data.get('pin')
        file_name = request.data.get('file_name')
        file_type = request.data.get('file_type', 'firmware')
        
        if not all([serial_number, pin, file_name]):
            return Response({
                'success': False,
                'message': 'جميع الحقول مطلوبة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            serial_key = SerialKey.objects.get(
                serial_number=serial_number,
                pin=pin,
                is_active=True
            )
            
            downloads_before = serial_key.downloads_remaining
            
            if serial_key.use_download():
                SerialUsage.objects.create(
                    serial_key=serial_key,
                    customer=serial_key.customer,
                    file_name=file_name,
                    file_type=file_type,
                    downloads_before=downloads_before,
                    downloads_after=serial_key.downloads_remaining
                )
                
                return Response({
                    'success': True,
                    'message': 'تم التحميل بنجاح',
                    'downloads_remaining': serial_key.downloads_remaining
                })
            else:
                return Response({
                    'success': False,
                    'message': 'رصيد التحميلات منتهي'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو منتهي'
            }, status=status.HTTP_404_NOT_FOUND)
