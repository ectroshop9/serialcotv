from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from .models import SerialKey, SerialPackage, SerialUsage
import json
import hmac
import hashlib
import requests

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
                        'tokens_total': serial_key.tokens_total,
                        'tokens_used': serial_key.tokens_used,
                        'tokens_remaining': 0,
                        'status': 'منتهي'
                    }
                })
            
            return Response({
                'success': True,
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name,
                    'tokens_total': serial_key.tokens_total,
                    'tokens_used': serial_key.tokens_used,
                    'tokens_remaining': serial_key.tokens_remaining,
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
            
            customer.token_balance += serial_key.tokens_remaining
            customer.save()
            
            return Response({
                'success': True,
                'message': 'تم تفعيل السيريال بنجاح',
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name,
                    'tokens_remaining': serial_key.tokens_remaining,
                }
            })
            
        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو مستخدم مسبقاً'
            }, status=status.HTTP_404_NOT_FOUND)


class UseTokenAPI(APIView):
    """استخدام التوكن للتحميل"""
    
    def post(self, request):
        serial_number = request.data.get('serial')
        pin = request.data.get('pin')
        file_name = request.data.get('file_name')
        file_type = request.data.get('file_type', 'firmware')
        token_amount = int(request.data.get('token_amount', 0))
        
        if not all([serial_number, pin, file_name, token_amount]):
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
            
            tokens_before = serial_key.tokens_remaining
            
            if serial_key.use_tokens(token_amount):
                SerialUsage.objects.create(
                    serial_key=serial_key,
                    customer=serial_key.customer,
                    file_name=file_name,
                    file_type=file_type,
                    tokens_before=tokens_before,
                    tokens_after=serial_key.tokens_remaining
                )
                
                return Response({
                    'success': True,
                    'message': 'تم بنجاح',
                    'tokens_remaining': serial_key.tokens_remaining
                })
            else:
                return Response({
                    'success': False,
                    'message': 'رصيد التوكن غير كافي'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو منتهي'
            }, status=status.HTTP_404_NOT_FOUND)


# ==================== Chargily Webhook ====================
GOOGLE_SHEET_URL = 'https://script.google.com/macros/s/AKfycby-7Tuosek9RRiEelC7gUWhzutVmspfswtK7xz45D-2/exec'

@csrf_exempt
def chargily_webhook(request):
    """استقبال Webhook من Chargily بعد الدفع الناجح"""
    if request.method == 'POST':
        payload = request.body
        signature = request.headers.get('X-Signature', '')
        
        secret = getattr(settings, 'CHARGILY_APP_SECRET', '')
        computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        
        if computed != signature:
            return JsonResponse({'error': 'Invalid signature'}, status=400)
        
        data = json.loads(payload)
        
        if data.get('status') == 'paid':
            package_name = data.get('comment', '')
            try:
                package = SerialPackage.objects.get(name=package_name)
                serial = SerialKey.objects.create(
                    package=package,
                    tokens_total=package.tokens_limit,
                    tokens_remaining=package.tokens_limit,
                )
                
                # إرسال السيريال بالإيميل
                if data.get('client_email'):
                    send_mail(
                        'SerialCo TV - تم تفعيل اشتراكك',
                        f'شكراً لاشتراكك!\n\n'
                        f'الباقة: {package.name}\n'
                        f'السيريال: {serial.serial_number}\n'
                        f'البين: {serial.pin}\n'
                        f'التوكن: {package.tokens_limit:,}\n\n'
                        f'رابط التحميل: https://serialco.tv/download',
                        settings.DEFAULT_FROM_EMAIL,
                        [data.get('client_email')],
                        fail_silently=True,
                    )
                
                # تسجيل في Google Sheet
                try:
                    requests.post(GOOGLE_SHEET_URL, json={
                        'client': data.get('client', ''),
                        'client_email': data.get('client_email', ''),
                        'package': package.name,
                        'serial': serial.serial_number,
                        'pin': serial.pin,
                        'tokens': package.tokens_limit,
                    })
                except:
                    pass
                
                return JsonResponse({
                    'success': True,
                    'serial': serial.serial_number,
                    'pin': serial.pin
                })
            except SerialPackage.DoesNotExist:
                return JsonResponse({'error': 'Package not found'}, status=404)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)