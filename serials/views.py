import hmac
import hashlib
import json
import requests

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SerialKey, SerialPackage, SerialUsage
from accounts.models import Customer

GOOGLE_SHEET_URL = 'https://script.google.com/macros/s/AKfycbzk9pPtYkLKeh0mFiBxG-jj_6vfCK9rIaPxPZwBuzWnVW2JUhItEDuXI_pE0qCrqN5u-g/exec'


class CheckSerialAPI(APIView):
    """1. فحص السيريال والبين"""
    
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
    """2. تفعيل السيريال للعميل"""
    
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
    """3. استخدام التوكن للتحميل"""
    
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

@csrf_exempt
def chargily_webhook(request):
    """4. استقبال Webhook من Chargily بعد الدفع الناجح"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # 1. التحقق من التوقيع (Signature)
    signature = request.headers.get('signature') or request.headers.get('Chargily-Signature', '')
    secret = getattr(settings, 'CHARGILY_APP_SECRET', '').encode('utf-8')
    
    computed_signature = hmac.new(
        secret,
        request.body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, signature or ''):
        print("❌ فشل التحقق من توقيع Chargily (Signature Mismatch)")
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    # 2. استخراج البيانات
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    event_type = payload.get('type', '')
    
    if event_type != 'checkout.paid':
        return JsonResponse({'status': 'ignored'}, status=200)
    
    checkout_data = payload.get('data', {})
    metadata = checkout_data.get('metadata', {}) or {}

    customer_id = metadata.get('user_id')
    package_name = metadata.get('package_name', '')
    package_id = metadata.get('package_id')

    # 3. جلب الباقة أولاً
    try:
        if package_id:
            package = SerialPackage.objects.get(id=package_id)
        elif package_name:
            package = SerialPackage.objects.get(name=package_name)
        else:
            package = SerialPackage.objects.first()
            if not package:
                print("❌ لا توجد أي باقات أنشئت في قاعدة البيانات!")
                return JsonResponse({'error': 'No packages available'}, status=400)
    except SerialPackage.DoesNotExist:
        print("❌ الباقة المطلوبة غير موجودة")
        return JsonResponse({'error': 'Package not found'}, status=404)

    # 4. إنشاء السيريال فوراً في قاعدة البيانات (مرحلة أولى مضمونة)
    try:
        serial = SerialKey.objects.create(package=package)
        print(f"✅ تم إنشاء السيريال بنجاح في قاعدة البيانات: {serial.serial_number}")
    except Exception as create_err:
        print(f"❌ خطأ أثناء إنشاء السيريال: {create_err}")
        return JsonResponse({'error': 'Failed to create serial'}, status=500)

    # 5. جلب بيانات البريد والاسم
    client_email = (
        checkout_data.get('customer_email') or 
        checkout_data.get('client_email') or 
        metadata.get('email') or 
        metadata.get('client_email') or 
        (checkout_data.get('customer') or {}).get('email') or 
        ''
    )
    
    client_name = (
        checkout_data.get('customer_name') or 
        checkout_data.get('client') or 
        metadata.get('name') or 
        'عميل Chargily'
    )

    # محاولة تجربة جلب البريد من API إن كان فارغاً
    chargily_customer_id = checkout_data.get('customer_id')
    if not client_email and chargily_customer_id:
        try:
            is_live = checkout_data.get('livemode', False)
            base_url = "https://pay.chargily.net/api/v2" if is_live else "https://pay.chargily.net/test/api/v2"
            api_secret = getattr(settings, 'CHARGILY_APP_SECRET', '')

            headers = {
                'Authorization': f'Bearer {api_secret}',
                'Content-Type': 'application/json'
            }
            
            res = requests.get(f"{base_url}/customers/{chargily_customer_id}", headers=headers, timeout=3)
            if res.status_code == 200:
                cust_data = res.json()
                client_email = cust_data.get('email', '') or cust_data.get('customer_email', '')
                if cust_data.get('name'):
                    client_name = cust_data.get('name')
                print(f"✅ تم جلب الإيميل من Chargily API: {client_email}")
        except Exception as fetch_err:
            print(f"⚠️ تجاوز جلب API للعميل بسبب: {fetch_err}")

    # 6. ربط السيريال بحساب العميل الداخلي إن وجد
    if customer_id:
        try:
            customer = Customer.objects.get(id=customer_id, is_active=True)
            serial.customer = customer
            serial.used_at = timezone.now()
            serial.save()
            
            customer.token_balance += package.tokens_limit
            customer.save()
        except Customer.DoesNotExist:
            pass

    # 7. إرسال الإيميل (معزول)
    if client_email:
        try:
            send_mail(
                'SerialCo TV - تم تفعيل اشتراكك',
                f'شكراً لاشتراكك!\n\n'
                f'الباقة: {package.name}\n'
                f'السيريال: {serial.serial_number}\n'
                f'البين: {serial.pin}\n\n'
                f'رابط التحميل: https://serialcotv.vercel.app/dashboard',
                settings.DEFAULT_FROM_EMAIL,
                [client_email],
                fail_silently=True,
            )
            print(f"📧 تم إرسال البريد إلى: {client_email}")
        except Exception as mail_err:
            print(f"❌ خطأ في إرسال البريد: {mail_err}")
    else:
        print("⚠️ لم يرسل الإيميل لأن خانة البريد فارغة.")

    # 8. تسجيل البيانات في Google Sheet (معزول)
    try:
        requests.post(GOOGLE_SHEET_URL, json={
            'client': client_name,
            'client_email': client_email,
            'email': client_email,
            'package': package.name,
            'serial': serial.serial_number,
            'pin': serial.pin,
            'tokens': package.tokens_limit,
        }, timeout=3)
    except Exception as sheet_err:
        print(f"❌ خطأ Google Sheet: {sheet_err}")

    return JsonResponse({
        'success': True,
        'serial': serial.serial_number,
        'pin': serial.pin
    }, status=200)