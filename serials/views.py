import hashlib
import hmac
import json
import logging
import re
import threading
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction, IntegrityError, connection
from django.db.models import F
from django.db.models.functions import Coalesce
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

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
CHARGILY_TEST_API = "https://pay.chargily.net/test/api/v2"
CHARGILY_LIVE_API = "https://pay.chargily.net/api/v2"


def clean_url(url):
    if not url:
        return ''
    url = url.strip().strip("'\"").strip('[](){}').strip().replace(' ', '')
    if not url.startswith(('http://', 'https://')):
        return ''
    return url


def extract_email_from_payload(data, raw_body_str=""):
    email_keys = ['email', 'customer_email', 'client_email', 'payer_email', 'user_email']
    def _recursive_search(value):
        if not value:
            return None
        if isinstance(value, dict):
            for key in email_keys:
                if key in value:
                    val = value[key]
                    if isinstance(val, str) and '@' in val:
                        return val.strip()
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
    email = _recursive_search(data)
    if email:
        return email
    if raw_body_str:
        match = EMAIL_REGEX.search(raw_body_str)
        if match:
            return match.group(0)
    return None


def get_chargily_customer_email(customer_id, mode, api_secret_key):
    try:
        api_base = CHARGILY_TEST_API if mode == 'test' else CHARGILY_LIVE_API
        headers = {"Authorization": f"Bearer {api_secret_key}"}
        response = requests.get(f"{api_base}/customers/{customer_id}", headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json().get('email')
    except:
        pass
    return None


def parse_metadata(metadata):
    if isinstance(metadata, dict):
        return metadata
    elif isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except:
            pass
    return {}


def async_post_processing(client_email, client_name, package_id, serial_id, customer_instance_id, customer_id, sheet_url):
    try:
        from .models import SerialKey, SerialPackage
        from accounts.models import Customer
        
        package = SerialPackage.objects.get(id=package_id)
        serial = SerialKey.objects.get(id=serial_id)
        customer_instance = None
        if customer_instance_id:
            try:
                customer_instance = Customer.objects.get(id=customer_instance_id)
            except Customer.DoesNotExist:
                pass
        
        if client_email:
            try:
                logger.info(f"📧 [Async] Sending email to {client_email}")
                
                if customer_instance:
                    email_html = f"<p>مرحباً {client_name}،</p><p>تم تفعيل اشتراكك!</p><p>الباقة: {package.name}<br>السيريال: {serial.serial_number}<br>البين: {serial.pin}<br>التوكنز: {package.tokens_limit}</p>"
                else:
                    email_html = f"<p>مرحباً {client_name}،</p><p>شكراً لاشتراكك!</p><p>الباقة: {package.name}<br>السيريال: {serial.serial_number}<br>البين: {serial.pin}<br>التوكنز: {package.tokens_limit}</p>"
                
                # ✅ استخدام BREVO_API_KEY
                api_key = getattr(settings, 'BREVO_API_KEY', settings.EMAIL_HOST_PASSWORD)
                response = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                        "accept": "application/json"
                    },
                    json={
                        "sender": {"name": "SerialCo TV", "email": "ectroshop9@gmail.com"},
                        "to": [{"email": client_email}],
                        "subject": "تم تفعيل اشتراكك بنجاح 🎉",
                        "htmlContent": email_html,
                    },
                    timeout=10
                )
                logger.info(f"📧 [Async] Brevo API response: {response.status_code}")
                
            except Exception as e:
                logger.error(f"❌ [Async] Email FAILED: {e}")

        if sheet_url:
            try:
                requests.post(sheet_url, json={
                    'client': client_name,
                    'email': client_email or '',
                    'package': package.name,
                    'serial': str(serial.serial_number),
                    'pin': str(serial.pin),
                    'tokens': package.tokens_limit,
                }, timeout=10)
                logger.info("✅ [Async] Sheet updated")
            except Exception as e:
                logger.error(f"❌ [Async] Sheet error: {e}")
                
    except Exception as e:
        logger.error(f"💥 [Async] Error: {e}")
    finally:
        try:
            connection.close()
        except:
            pass


class PackageListAPI(APIView):
    def get(self, request):
        packages = SerialPackage.objects.filter(is_active=True)
        serializer = SerialPackageSerializer(packages, many=True)
        return Response({'success': True, 'packages': serializer.data})


class CheckSerialAPI(APIView):
    def post(self, request):
        serializer = SerialVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'message': 'بيانات غير صحيحة'}, status=400)
        try:
            serial_key = SerialKey.objects.get(
                serial_number=serializer.validated_data['serial_number'],
                pin=serializer.validated_data['pin']
            )
            return Response({
                'success': not serial_key.is_used_up,
                'serial': {
                    'number': serial_key.serial_number,
                    'package': serial_key.package.name,
                    'tokens_remaining': serial_key.tokens_remaining,
                    'status': 'شغال' if not serial_key.is_used_up else 'منتهي'
                }
            })
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'سيريال غير صحيح'}, status=404)


class ActivateSerialAPI(APIView):
    def post(self, request):
        serial_number = request.data.get('serial_number') or request.data.get('serial')
        pin = request.data.get('pin')
        customer_id = request.data.get('customer_id')
        if not all([serial_number, pin, customer_id]):
            return Response({'success': False, 'message': 'بيانات ناقصة'}, status=400)
        try:
            customer = Customer.objects.get(id=customer_id, is_active=True)
        except Customer.DoesNotExist:
            return Response({'success': False, 'message': 'حساب غير موجود'}, status=404)
        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number, pin=pin, customer__isnull=True
                )
                serial_key.customer = customer
                serial_key.used_at = timezone.now()
                serial_key.save()
                Customer.objects.filter(pk=customer.pk).update(
                    token_balance=Coalesce(F('token_balance'), 0) + serial_key.tokens_remaining
                )
                return Response({
                    'success': True,
                    'message': 'تم التفعيل',
                    'serial': {'number': serial_key.serial_number, 'tokens_remaining': serial_key.tokens_remaining}
                })
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'سيريال غير صحيح'}, status=404)


class UseTokenAPI(APIView):
    def post(self, request):
        serializer = SerialDownloadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'message': 'بيانات غير صحيحة'}, status=400)
        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serializer.validated_data['serial_number'],
                    pin=serializer.validated_data['pin'],
                    is_active=True
                )
                if serial_key.tokens_remaining < 1:
                    return Response({'success': False, 'message': 'رصيد غير كافي'}, status=400)
                tokens_before = serial_key.tokens_remaining
                serial_key.use_tokens(1)
                tokens_after = serial_key.tokens_remaining
                SerialUsage.objects.create(
                    serial_key=serial_key, customer=serial_key.customer,
                    file_name=f"File_{serializer.validated_data['file_id']}",
                    tokens_before=tokens_before, tokens_after=tokens_after
                )
                return Response({'success': True, 'tokens_remaining': tokens_after})
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'سيريال غير صحيح'}, status=404)


class SerialUsageHistoryAPI(APIView):
    def post(self, request):
        serializer = SerialVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'message': 'بيانات غير صحيحة'}, status=400)
        try:
            serial_key = SerialKey.objects.get(
                serial_number=serializer.validated_data['serial_number'],
                pin=serializer.validated_data['pin']
            )
            usages = SerialUsage.objects.filter(serial_key=serial_key).order_by('-created_at')
            return Response({'success': True, 'history': SerialUsageSerializer(usages, many=True).data})
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'سيريال غير صحيح'}, status=404)


@csrf_exempt
def chargily_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    webhook_secret = getattr(settings, 'CHARGILY_APP_SECRET', '') or getattr(settings, 'CHARGILY_SECRET_KEY', '')
    api_secret_key = getattr(settings, 'CHARGILY_SECRET_KEY', '') or webhook_secret

    if not webhook_secret:
        return JsonResponse({'error': 'Config error'}, status=500)

    secret_bytes = webhook_secret.encode() if isinstance(webhook_secret, str) else webhook_secret
    signature = request.headers.get('signature', '') or request.headers.get('Chargily-Signature', '')
    computed = hmac.new(secret_bytes, request.body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    try:
        payload = json.loads(request.body)
    except:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if payload.get('type') != 'checkout.paid':
        return JsonResponse({'status': 'ignored'})

    checkout_data = payload.get('data', {})
    checkout_id = checkout_data.get('id')

    client_email = extract_email_from_payload(checkout_data, request.body.decode('utf-8', errors='ignore'))
    
    chargily_customer_id = checkout_data.get('customer_id')
    if not client_email and chargily_customer_id:
        mode = checkout_data.get('account', {}).get('mode', 'test')
        client_email = get_chargily_customer_email(chargily_customer_id, mode, api_secret_key)

    metadata = parse_metadata(checkout_data.get('metadata', {}))
    client_name = metadata.get('name', '') or 'عميل'

    package = None
    if metadata.get('package_id'):
        package = SerialPackage.objects.filter(id=metadata['package_id']).first()
    if not package and metadata.get('package_name'):
        package = SerialPackage.objects.filter(name=metadata['package_name']).first()
    if not package:
        package = SerialPackage.objects.filter(is_active=True).first()
    if not package:
        return JsonResponse({'error': 'No package'}, status=404)

    customer_instance = None
    customer_id = metadata.get('user_id') or metadata.get('customer_id')
    if customer_id:
        try:
            customer_instance = Customer.objects.get(id=customer_id, is_active=True)
        except:
            pass
    if not customer_instance and client_email:
        customer_instance = Customer.objects.filter(email__iexact=client_email, is_active=True).first()

    try:
        with transaction.atomic():
            create_kwargs = {'package': package, 'customer': customer_instance, 'is_active': True}
            if customer_instance:
                create_kwargs['used_at'] = timezone.now()
            if checkout_id and hasattr(SerialKey, 'payment_id'):
                create_kwargs['payment_id'] = checkout_id
            serial = SerialKey.objects.create(**create_kwargs)
            
            if customer_instance:
                Customer.objects.filter(pk=customer_instance.pk).update(
                    token_balance=Coalesce(F('token_balance'), 0) + package.tokens_limit
                )
    except IntegrityError:
        return JsonResponse({'status': 'already_processed'})
    except:
        return JsonResponse({'error': 'Failed'}, status=500)

    sheet_url = clean_url(getattr(settings, 'GOOGLE_SHEET_URL', ''))
    
    threading.Thread(
        target=async_post_processing,
        args=(client_email, client_name, package.id, serial.id,
              customer_instance.id if customer_instance else None,
              customer_id, sheet_url),
        daemon=True
    ).start()

    return JsonResponse({
        'success': True,
        'serial': serial.serial_number,
        'pin': serial.pin,
    })
