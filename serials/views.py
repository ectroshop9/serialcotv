import hashlib
import hmac
import json
import requests

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Customer
from .models import SerialKey, SerialPackage, SerialUsage
from .serializers import (
    SerialDownloadSerializer,
    SerialPackageSerializer,
    SerialUsageSerializer,
    SerialVerifySerializer,
)

GOOGLE_SHEET_URL = getattr(
    settings,
    'GOOGLE_SHEET_URL',
    'https://script.google.com/macros/s/AKfycbzk9pPtYkLKeh0mFiBxG-jj_6vfCK9rIaPxPZwBuzWnVW2JUhItEDuXI_pE0qCrqN5u-g/exec'
)


class PackageListAPI(APIView):
    """عرض قائمة الباقات المتاحة"""

    def get(self, request):
        packages = SerialPackage.objects.filter(is_active=True)
        serializer = SerialPackageSerializer(packages, many=True)
        return Response({
            'success': True,
            'packages': serializer.data
        }, status=status.HTTP_200_OK)


class CheckSerialAPI(APIView):
    """التحقق من السيريال والبين"""

    def post(self, request):
        serializer = SerialVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'بيانات مدخلة غير صحيحة',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serial_number = serializer.validated_data['serial_number']
        pin = serializer.validated_data['pin']

        try:
            serial_key = SerialKey.objects.get(serial_number=serial_number, pin=pin)

            tokens_remaining = getattr(serial_key, 'tokens_remaining', 0)
            is_used_up = getattr(serial_key, 'is_used_up', tokens_remaining <= 0)

            if is_used_up:
                return Response({
                    'success': False,
                    'message': 'السيريال منتهي',
                    'serial': {
                        'number': serial_key.serial_number,
                        'package': serial_key.package.name if serial_key.package else '',
                        'tokens_remaining': 0,
                        'status': 'منتهي'
                    }
                }, status=status.HTTP_200_OK)

            return Response({
                'success': True,
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name if serial_key.package else '',
                    'tokens_remaining': tokens_remaining,
                    'status': 'شغال'
                }
            }, status=status.HTTP_200_OK)

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال أو البين غير صحيح'
            }, status=status.HTTP_404_NOT_FOUND)


class ActivateSerialAPI(APIView):
    """تفعيل السيريال للعميل (المطلوبة في urls.py)"""

    def post(self, request):
        serial_number = request.data.get('serial_number') or request.data.get('serial')
        pin = request.data.get('pin')
        customer_id = request.data.get('customer_id')

        if not serial_number or not pin or not customer_id:
            return Response({
                'success': False,
                'message': 'بيانات التفعيل غير مكتملة (serial_number, pin, customer_id)'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number,
                    pin=pin,
                    customer__isnull=True
                )

                customer = get_object_or_404(Customer, id=customer_id, is_active=True)

                serial_key.customer = customer
                serial_key.used_at = timezone.now()
                serial_key.save()

                if hasattr(customer, 'token_balance') and hasattr(serial_key, 'tokens_remaining'):
                    customer.token_balance += serial_key.tokens_remaining
                    customer.save()

            return Response({
                'success': True,
                'message': 'تم تفعيل السيريال بنجاح',
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name if serial_key.package else '',
                    'tokens_remaining': getattr(serial_key, 'tokens_remaining', 0),
                }
            }, status=status.HTTP_200_OK)

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو مفعل مسبقاً'
            }, status=status.HTTP_404_NOT_FOUND)


class UseTokenAPI(APIView):
    """خصم التوكن عند التحميل"""

    def post(self, request):
        serializer = SerialDownloadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'بيانات التحميل غير مكتملة',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serial_number = serializer.validated_data['serial_number']
        pin = serializer.validated_data['pin']
        file_id = serializer.validated_data['file_id']

        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number,
                    pin=pin,
                    is_active=True
                )

                tokens_before = getattr(serial_key, 'tokens_remaining', 0)

                if hasattr(serial_key, 'use_tokens') and serial_key.use_tokens(1):
                    tokens_after = getattr(serial_key, 'tokens_remaining', 0)

                    SerialUsage.objects.create(
                        serial_key=serial_key,
                        customer=serial_key.customer,
                        file_name=f"File_ID_{file_id}",
                        tokens_before=tokens_before,
                        tokens_after=tokens_after
                    )

                    return Response({
                        'success': True,
                        'message': 'تم الخصم بنجاح وجاري التحميل',
                        'tokens_remaining': tokens_after
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': False,
                        'message': 'رصيد التوكن غير كافي'
                    }, status=status.HTTP_400_BAD_REQUEST)

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو غير مفعل'
            }, status=status.HTTP_404_NOT_FOUND)


class SerialUsageHistoryAPI(APIView):
    """عرض سجل استخدامات السيريال"""

    def post(self, request):
        serializer = SerialVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'يرجى إدخال السيريال والبين',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serial_number = serializer.validated_data['serial_number']
        pin = serializer.validated_data['pin']

        try:
            serial_key = SerialKey.objects.get(serial_number=serial_number, pin=pin)
            usages = SerialUsage.objects.filter(serial_key=serial_key).order_by('-created_at')
            usage_serializer = SerialUsageSerializer(usages, many=True)

            return Response({
                'success': True,
                'history': usage_serializer.data
            }, status=status.HTTP_200_OK)

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'بيانات السيريال غير صحيحة'
            }, status=status.HTTP_404_NOT_FOUND)


# ==================== Chargily Webhook ====================

@csrf_exempt
def chargily_webhook(request):
    """استقبال Webhook من Chargily بعد الدفع الناجح مع فحص توقيع مرن واستخراج آمن للبريد"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # 1. جلب المفتاح والتوقيع
    raw_secret = getattr(settings, 'CHARGILY_APP_SECRET', '')
    secret_bytes = raw_secret.encode('utf-8') if isinstance(raw_secret, str) else raw_secret
    
    signature = (
        request.headers.get('signature') or 
        request.headers.get('Chargily-Signature') or 
        request.headers.get('x-signature') or 
        ''
    )

    # 2. حساب التوقيع المتوقع
    computed_signature = hmac.new(
        secret_bytes,
        request.body,
        hashlib.sha256
    ).hexdigest()

    # 3. التحقق من التوقيع (مرن في DEBUG، صارم في Production)
    if not hmac.compare_digest(computed_signature, signature):
        if getattr(settings, 'DEBUG', False):
            print("⚠️ [DEBUG MODE]: تم تجاوز خطأ التوقيع للتجربة المحلية فقط.")
        else:
            print("❌ فشل التحقق من توقيع Chargily (Production)")
            return JsonResponse({'error': 'Invalid signature'}, status=400)

    # 4. استخراج بيانات الحمولة (Payload)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    event_type = payload.get('type', '')
    if event_type != 'checkout.paid':
        return JsonResponse({'status': 'ignored'}, status=200)

    checkout_data = payload.get('data', {}) or {}
    checkout_id = checkout_data.get('id')  # رقم العملية الفريد من Chargily

    # 🛑 أمان: فك تشفير metadata بأمان سواء كانت Dict أو String
    raw_metadata = checkout_data.get('metadata') or {}
    if isinstance(raw_metadata, str):
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = raw_metadata

    customer_id = metadata.get('user_id') or metadata.get('customer_id')
    package_name = metadata.get('package_name', '')
    package_id = metadata.get('package_id')

    # 5. جلب الباقة
    try:
        if package_id:
            package = SerialPackage.objects.get(id=package_id)
        elif package_name:
            package = SerialPackage.objects.get(name=package_name)
        else:
            package = SerialPackage.objects.first()
            if not package:
                print("❌ لا توجد أي باقات في قاعدة البيانات")
                return JsonResponse({'error': 'No packages available'}, status=400)
    except SerialPackage.DoesNotExist:
        print("❌ الباقة المطلوبة غير موجودة")
        return JsonResponse({'error': 'Package not found'}, status=404)

    # 6. البحث الشامل عن البريد الإلكتروني والاسم (حل المشكلة الرئيسي)
    customer_obj = checkout_data.get('customer') if isinstance(checkout_data.get('customer'), dict) else {}
    payer_obj = checkout_data.get('payer') if isinstance(checkout_data.get('payer'), dict) else {}

    client_email = (
        metadata.get('email') or 
        metadata.get('client_email') or 
        metadata.get('user_email') or 
        checkout_data.get('customer_email') or 
        checkout_data.get('payer_email') or 
        customer_obj.get('email') or 
        payer_obj.get('email') or 
        ''
    )

    client_name = (
        metadata.get('name') or 
        metadata.get('client_name') or 
        checkout_data.get('customer_name') or 
        customer_obj.get('name') or 
        payer_obj.get('name') or 
        'عميل SerialCo'
    )

    # 7. ربط الحساب الداخلي بالعميل + جلب البريد منه إن لم يجد في Chargily
    customer_instance = None
    if customer_id:
        try:
            customer_instance = Customer.objects.get(id=customer_id, is_active=True)
            if not client_email and getattr(customer_instance, 'email', None):
                client_email = customer_instance.email
        except Customer.DoesNotExist:
            pass

    # 🛑 تجربة محليّة: وضع إيميل تجريبي أثناء DEBUG إذا كان الإيميل فارغاً
    if not client_email and getattr(settings, 'DEBUG', False):
        client_email = getattr(settings, 'DEFAULT_TEST_EMAIL', 'test_user@gmail.com')
        print(f"⚠️ [DEBUG MODE]: تم تعيين إيميل افتراضي للتجربة: {client_email}")

    # 8. إنشاء السيريال
    try:
        serial = SerialKey.objects.create(
            package=package,
            customer=customer_instance,
            used_at=timezone.now() if customer_instance else None
        )

        if customer_instance:
            customer_instance.token_balance += package.tokens_limit
            customer_instance.save()

        print(f"✅ تم إنشاء السيريال بنجاح: {serial.serial_number}")
    except Exception as create_err:
        print(f"❌ خطأ أثناء إنشاء السيريال: {create_err}")
        return JsonResponse({'error': 'Failed to create serial'}, status=500)

    # 9. إرسال البريد الإلكتروني
    if client_email:
        try:
            send_mail(
                subject='SerialCo TV - تم تفعيل اشتراكك',
                message=(
                    f"مرحباً {client_name}،\n\n"
                    f"شكراً لاشتراكك!\n\n"
                    f"الباقة: {package.name}\n"
                    f"السيريال: {serial.serial_number}\n"
                    f"البين: {serial.pin}\n\n"
                    f"رابط Dashboard: https://serialcotv.vercel.app/dashboard"
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@serialcotv.com'),
                recipient_list=[client_email],
                fail_silently=False,
            )
            print(f"📧 تم إرسال البريد إلى: {client_email}")
        except Exception as mail_err:
            print(f"❌ خطأ في إرسال البريد (تأكد من إعدادات SMTP في settings.py): {mail_err}")
    else:
        print("⚠️ لم يتم إرسال إيميل لأن البريد الإلكتروني فارغ تماماً.")

    # 10. تحديث Google Sheet
    sheet_url = getattr(settings, 'GOOGLE_SHEET_URL', globals().get('GOOGLE_SHEET_URL', ''))
    if sheet_url:
        try:
            requests.post(sheet_url, json={
                'client': client_name,
                'client_email': client_email,
                'email': client_email,
                'package': package.name,
                'serial': str(serial.serial_number),
                'pin': str(serial.pin),
                'tokens': package.tokens_limit,
            }, timeout=4)
            print(f"📊 تم تحديث Google Sheet للإيميل: {client_email}")
        except Exception as sheet_err:
            print(f"❌ خطأ Google Sheet: {sheet_err}")

    return JsonResponse({
        'success': True,
        'serial': serial.serial_number,
        'pin': serial.pin
    }, status=200)
