import hashlib
import hmac
import json
import requests

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
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


# ==================== Chargily Webhook ====================

@csrf_exempt
def chargily_webhook(request):
    """استقبال Webhook من Chargily + إنشاء السيريال أوتوماتيكياً + إرسال الإيميل + تحديث Google Sheet"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    signature = request.headers.get('signature') or request.headers.get('Chargily-Signature') or request.headers.get('x-signature')
    secret = getattr(settings, 'CHARGILY_APP_SECRET', '')

    if secret:
        computed_signature = hmac.new(
            secret.encode('utf-8'),
            request.body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_signature, signature or ''):
            print("❌ Chargily Signature Mismatch")
            return JsonResponse({'error': 'Invalid signature'}, status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    event_type = payload.get('type')
    if event_type != 'checkout.paid':
        return JsonResponse({'status': 'ignored'}, status=200)

    checkout_data = payload.get('data', {})
    checkout_id = checkout_data.get('id')
    metadata = checkout_data.get('metadata') or {}

    customer_id = metadata.get('user_id') or metadata.get('customer_id')
    package_id = metadata.get('package_id')
    package_name = metadata.get('package_name')

    package = None
    if package_id:
        package = SerialPackage.objects.filter(id=package_id).first()
    if not package and package_name:
        package = SerialPackage.objects.filter(name=package_name).first()
    if not package:
        package = SerialPackage.objects.first()

    if not package:
        print("❌ لم يتم العثور على أي باقة")
        return JsonResponse({'error': 'No package found'}, status=400)

    try:
        with transaction.atomic():
            serial = SerialKey()
            serial.package = package

            if hasattr(package, 'tokens_limit'):
                serial.tokens_total = package.tokens_limit
                serial.tokens_remaining = package.tokens_limit

            if customer_id:
                try:
                    customer = Customer.objects.select_for_update().get(id=customer_id, is_active=True)
                    serial.customer = customer
                    serial.used_at = timezone.now()

                    if hasattr(customer, 'token_balance') and hasattr(package, 'tokens_limit'):
                        customer.token_balance += package.tokens_limit
                        customer.save()
                except Customer.DoesNotExist:
                    pass

            serial.save()
            print(f"✅ تم إنشاء السيريال أوتوماتيكياً: {serial.serial_number}")

    except Exception as create_err:
        print(f"❌ خطأ أثناء إنشاء السيريال: {create_err}")
        return JsonResponse({'error': str(create_err)}, status=500)

    client_email = (
        checkout_data.get('customer_email') or
        metadata.get('email') or
        metadata.get('client_email') or
        (checkout_data.get('customer') or {}).get('email') or
        ''
    )

    client_name = (
        checkout_data.get('customer_name') or
        metadata.get('name') or
        'عميل Chargily'
    )

    if client_email:
        try:
            send_mail(
                subject='SerialCo TV - تم تفعيل اشتراكك وتوليد السيريال',
                message=(
                    f"مرحباً {client_name}،\n\n"
                    f"شكراً لاشتراكك! تفاصيل السيريال الخاص بك:\n"
                    f"الباقة: {package.name}\n"
                    f"السيريال: {serial.serial_number}\n"
                    f"البين: {serial.pin}\n\n"
                    f"رابط اللوحة: https://serialcotv.vercel.app/dashboard"
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@serialcotv.com'),
                recipient_list=[client_email],
                fail_silently=True
            )
            print(f"📧 تم إرسال البريد إلى: {client_email}")
        except Exception as mail_err:
            print(f"❌ خطأ الإيميل: {mail_err}")

    if GOOGLE_SHEET_URL:
        try:
            requests.post(GOOGLE_SHEET_URL, json={
                'checkout_id': checkout_id,
                'client': client_name,
                'client_email': client_email,
                'email': client_email,
                'package': package.name,
                'serial': str(serial.serial_number),
                'pin': str(serial.pin),
                'tokens': getattr(package, 'tokens_limit', 0),
            }, timeout=5)
            print("📊 تم تحديث Google Sheet بنجاح")
        except Exception as sheet_err:
            print(f"❌ خطأ Google Sheet: {sheet_err}")

    return JsonResponse({
        'success': True,
        'serial': str(serial.serial_number),
        'pin': str(serial.pin)
    }, status=200)
