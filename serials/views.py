import hashlib
import hmac
import json
import logging
import re
from typing import Optional, Dict, Any

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
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

logger = logging.getLogger(__name__)

# Constants
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
CHARGILY_TEST_API = "https://pay.chargily.net/test/api/v2"
CHARGILY_LIVE_API = "https://pay.chargily.net/api/v2"


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
            serial_key = SerialKey.objects.get(
                serial_number=serial_number, 
                pin=pin
            )
            
            tokens_remaining = serial_key.tokens_remaining
            is_used_up = serial_key.is_used_up

            response_data = {
                'success': not is_used_up,
                'message': 'السيريال منتهي' if is_used_up else 'السيريال صالح',
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name if serial_key.package else '',
                    'tokens_remaining': tokens_remaining if not is_used_up else 0,
                    'status': 'منتهي' if is_used_up else 'شغال'
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال أو البين غير صحيح'
            }, status=status.HTTP_404_NOT_FOUND)


class ActivateSerialAPI(APIView):
    """تفعيل السيريال للعميل"""
    
    def post(self, request):
        serial_number = request.data.get('serial_number') or request.data.get('serial')
        pin = request.data.get('pin')
        customer_id = request.data.get('customer_id')

        # Validate required fields
        if not all([serial_number, pin, customer_id]):
            return Response({
                'success': False,
                'message': 'بيانات التفعيل غير مكتملة (serial_number, pin, customer_id)'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Lock the serial key for update
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number,
                    pin=pin,
                    customer__isnull=True  # Only unactivated serials
                )

                customer = get_object_or_404(Customer, id=customer_id, is_active=True)

                # Activate the serial
                serial_key.customer = customer
                serial_key.used_at = timezone.now()
                serial_key.save()

                # Update customer token balance atomically
                Customer.objects.filter(pk=customer.pk).update(
                    token_balance=F('token_balance') + serial_key.tokens_remaining
                )

            return Response({
                'success': True,
                'message': 'تم تفعيل السيريال بنجاح',
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name if serial_key.package else '',
                    'tokens_remaining': serial_key.tokens_remaining,
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

                tokens_before = serial_key.tokens_remaining

                if serial_key.use_tokens(1):
                    tokens_after = serial_key.tokens_remaining

                    # Log the usage
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
            serial_key = SerialKey.objects.get(
                serial_number=serial_number, 
                pin=pin
            )
            usages = SerialUsage.objects.filter(
                serial_key=serial_key
            ).order_by('-created_at')
            
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


def extract_email_from_payload(data: Any, raw_body_str: str = "") -> Optional[str]:
    """
    البحث عن البريد الإلكتروني داخل البيانات المعالجة أو النص الخام
    
    Args:
        data: Parsed JSON data or any nested structure
        raw_body_str: Raw request body as string
    
    Returns:
        Extracted email string or empty string
    """
    email_keys = ['email', 'customer_email', 'client_email', 'payer_email', 'user_email']
    
    def _recursive_search(value: Any) -> Optional[str]:
        if not value:
            return None
            
        if isinstance(value, dict):
            # Check known email keys first
            for key in email_keys:
                if key in value:
                    val = value[key]
                    if isinstance(val, str) and '@' in val:
                        return val.strip()
            
            # Recursively search all values
            for v in value.values():
                result = _recursive_search(v)
                if result:
                    return result
                    
        elif isinstance(value, (list, tuple)):
            for item in value:
                result = _recursive_search(item)
                if result:
                    return result
                    
        elif isinstance(value, str):
            match = EMAIL_REGEX.search(value)
            if match:
                return match.group(0)
                
        return None

    # Try to find email in parsed data
    email = _recursive_search(data)
    if email:
        return email

    # Fallback to raw body string
    if raw_body_str:
        match = EMAIL_REGEX.search(raw_body_str)
        if match:
            return match.group(0)

    return ""


def get_chargily_customer_email(customer_id: str, mode: str, api_secret_key: str) -> Optional[str]:
    """
    Fetch customer email from Chargily API
    
    Args:
        customer_id: Chargily customer ID
        mode: 'test' or 'live'
        api_secret_key: Chargily API secret key
    
    Returns:
        Customer email or None
    """
    try:
        api_base = CHARGILY_TEST_API if mode == 'test' else CHARGILY_LIVE_API
        headers = {
            "Authorization": f"Bearer {api_secret_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            f"{api_base}/customers/{customer_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            customer_data = response.json()
            return customer_data.get('email')
            
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Chargily customer: {e}")
    
    return None


def parse_metadata(metadata: Any) -> Dict:
    """
    Parse metadata from various formats to dictionary
    
    Args:
        metadata: Raw metadata (dict, JSON string, or other)
    
    Returns:
        Parsed metadata dictionary
    """
    if isinstance(metadata, dict):
        return metadata
    elif isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning("Failed to parse metadata JSON")
    return {}


@csrf_exempt
def chargily_webhook(request):
    """استقبال Webhook من Chargily بعد الدفع الناجح"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # 1. Verify webhook signature
    webhook_secret = getattr(settings, 'CHARGILY_APP_SECRET', '') or \
                     getattr(settings, 'CHARGILY_SECRET_KEY', '')
    api_secret_key = getattr(settings, 'CHARGILY_SECRET_KEY', '') or webhook_secret

    if not webhook_secret:
        logger.error("Chargily webhook secret not configured")
        return JsonResponse({'error': 'Server configuration error'}, status=500)

    # Verify HMAC signature
    secret_bytes = webhook_secret.encode('utf-8') if isinstance(webhook_secret, str) else webhook_secret
    signature = request.headers.get('signature', '') or \
                request.headers.get('Chargily-Signature', '')

    computed_signature = hmac.new(
        secret_bytes, 
        request.body, 
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        logger.warning("Invalid webhook signature received")
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    # 2. Parse request body
    raw_body_text = request.body.decode('utf-8', errors='ignore')
    try:
        payload = json.loads(raw_body_text)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # 3. Only process successful payments
    if payload.get('type') != 'checkout.paid':
        return JsonResponse({'status': 'ignored'}, status=200)

    checkout_data = payload.get('data', {})
    checkout_id = checkout_data.get('id')

    # 4. Idempotency check
    if checkout_id and hasattr(SerialKey, 'payment_id'):
        if SerialKey.objects.filter(payment_id=checkout_id).exists():
            logger.info(f"Duplicate webhook ignored: {checkout_id}")
            return JsonResponse({'status': 'already_processed'}, status=200)

    # 5. Extract email
    client_email = extract_email_from_payload(checkout_data, raw_body_text)

    # 6. Fetch email from Chargily API if needed
    chargily_customer_id = checkout_data.get('customer_id')
    if not client_email and chargily_customer_id:
        mode = checkout_data.get('account', {}).get('mode', 'test')
        client_email = get_chargily_customer_email(
            chargily_customer_id, 
            mode, 
            api_secret_key
        ) or ''

    # 7. Parse metadata
    metadata = parse_metadata(checkout_data.get('metadata', {}))
    client_name = metadata.get('name', '') or \
                  metadata.get('client_name', '') or \
                  'عميل SerialCo'

    # 8. Find or get package
    package_id = metadata.get('package_id')
    package_name = metadata.get('package_name')
    package = None

    if package_id:
        package = SerialPackage.objects.filter(id=package_id).first()
    if not package and package_name:
        package = SerialPackage.objects.filter(name=package_name).first()
    if not package:
        package = SerialPackage.objects.filter(is_active=True).first()

    if not package:
        logger.error("No active package found for serial creation")
        return JsonResponse({'error': 'Package not found'}, status=404)

    # 9. Find existing customer
    customer_id = metadata.get('user_id') or metadata.get('customer_id')
    customer_instance = None
    
    if customer_id:
        try:
            customer_instance = Customer.objects.get(
                id=customer_id, 
                is_active=True
            )
            if not client_email and getattr(customer_instance, 'email', None):
                client_email = customer_instance.email
        except Customer.DoesNotExist:
            logger.warning(f"Customer {customer_id} not found")

    # 10. Create serial key
    try:
        with transaction.atomic():
            create_kwargs = {
                'package': package,
                'customer': customer_instance,
                'used_at': timezone.now() if customer_instance else None,
                'is_active': True
            }
            
            if hasattr(SerialKey, 'payment_id') and checkout_id:
                create_kwargs['payment_id'] = checkout_id

            serial = SerialKey.objects.create(**create_kwargs)

            # Add tokens to customer balance
            if customer_instance:
                Customer.objects.filter(pk=customer_instance.pk).update(
                    token_balance=F('token_balance') + package.tokens_limit
                )
                logger.info(
                    f"Added {package.tokens_limit} tokens to customer {customer_id}"
                )

    except Exception as e:
        logger.error(f"Failed to create serial: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to create serial'}, status=500)

    # 11. Send email notification
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
                from_email=getattr(
                    settings, 
                    'DEFAULT_FROM_EMAIL', 
                    'noreply@serialcotv.com'
                ),
                recipient_list=[client_email],
                fail_silently=True,
            )
            logger.info(f"Confirmation email sent to {client_email}")
        except Exception as e:
            logger.error(f"Failed to send email to {client_email}: {e}")

    # 12. Update Google Sheet
    sheet_url = getattr(settings, 'GOOGLE_SHEET_URL', '')
    if sheet_url:
        try:
            requests.post(
                sheet_url,
                json={
                    'client': client_name,
                    'client_email': client_email,
                    'email': client_email,
                    'package': package.name,
                    'serial': str(serial.serial_number),
                    'pin': str(serial.pin),
                    'tokens': package.tokens_limit,
                },
                timeout=5
            )
        except requests.RequestException as e:
            logger.error(f"Failed to update Google Sheet: {e}")

    return JsonResponse({
        'success': True,
        'serial': serial.serial_number,
        'pin': serial.pin
    }, status=200)
