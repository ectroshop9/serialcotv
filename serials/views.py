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

# Constants
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
CHARGILY_TEST_API = "https://pay.chargily.net/test/api/v2"
CHARGILY_LIVE_API = "https://pay.chargily.net/api/v2"


def clean_url(url: str) -> str:
    """تنظيف الرابط من أي أحرف غير مرغوب فيها"""
    if not url:
        return ''
    
    url = url.strip()
    url = url.strip("'\"")
    url = url.strip('[](){}')
    url = url.strip()
    url = url.replace(' ', '')
    url = url.strip('.,;:')
    
    if not url:
        logger.warning("Empty URL after cleaning")
        return ''
    
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"URL doesn't start with http/https: {url[:50]}...")
        return ''
    
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"Invalid URL structure: {url[:50]}...")
            return ''
    except Exception as e:
        logger.error(f"URL parsing failed: {e}")
        return ''
    
    return url


def extract_email_from_payload(data: Any, raw_body_str: str = "") -> Optional[str]:
    """البحث عن البريد الإلكتروني داخل البيانات المعالجة أو النص الخام"""
    email_keys = ['email', 'customer_email', 'client_email', 'payer_email', 'user_email']
    
    def _recursive_search(value: Any) -> Optional[str]:
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


def get_chargily_customer_email(customer_id: str, mode: str, api_secret_key: str) -> Optional[str]:
    """Fetch customer email from Chargily API"""
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
    """Parse metadata from various formats to dictionary"""
    if isinstance(metadata, dict):
        return metadata
    elif isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            logger.warning("Failed to parse metadata JSON")
    return {}


# ✅ دالة المعالجة في الخلفية مع إغلاق اتصال DB
# ملاحظة: إذا زاد حجم الطلبات (آلاف في الدقيقة)، يُفضل الترقية إلى Celery/RQ
def async_post_processing(
    client_email: str,
    client_name: str,
    package_id: int,
    serial_id: int,
    customer_instance_id: Optional[int],
    customer_id: Optional[str],
    sheet_url: str
):
    """
    معالجة ما بعد الدفع في Thread منفصل
    
    Production Notes:
    - يستخدم IDs فقط (Thread Safety)
    - يغلق اتصال DB في finally (Connection Leak Prevention)
    - مناسب للمشاريع المتوسطة (< 1000 طلب/دقيقة)
    - للترقية المستقبلية: استخدم Celery مع automatic retries
    """
    try:
        # جلب الكائنات من DB داخل الـ Thread
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
        
        # إرسال البريد الإلكتروني
        if client_email:
            try:
                import resend
                resend.api_key = settings.EMAIL_HOST_PASSWORD
                
                logger.info(f"📧 [Async] Sending email to {client_email}")
                
                if customer_instance:
                    email_html = f"<p>مرحباً {client_name}،</p><p>تم تفعيل اشتراكك بنجاح وربطه بحسابك!</p><p>الباقة: {package.name}<br>السيريال: {serial.serial_number}<br>البين: {serial.pin}<br>عدد التوكنز: {package.tokens_limit}</p><p>رابط: https://serialcotv.vercel.app/dashboard</p>"
                else:
                    email_html = f"<p>مرحباً {client_name}،</p><p>شكراً لاشتراكك!</p><p>الباقة: {package.name}<br>السيريال: {serial.serial_number}<br>البين: {serial.pin}<br>عدد التوكنز: {package.tokens_limit}</p><p>سجل من: https://serialcotv.vercel.app/register</p>"
                
                resend.Emails.send({
                    "from": "SerialCo TV <onboarding@resend.dev>",
                    "to": [client_email],
                    "subject": "تم تفعيل اشتراكك بنجاح 🎉",
                    "html": email_html,
                })
                logger.info(f"✅ [Async] Email sent via Resend API")
                
            except Exception as e:
                logger.error(f"❌ [Async] Email FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ [Async] Email FAILED: {e}")        
        # تحديث Google Sheet
        if sheet_url:
            try:
                logger.info(f"📊 [Async] Updating Google Sheet...")
                response = requests.post(
                    sheet_url,
                    json={
                        'client': client_name,
                        'client_email': client_email or 'No Email',
                        'email': client_email or 'No Email',
                        'package': package.name,
                        'serial': str(serial.serial_number),
                        'pin': str(serial.pin),
                        'tokens': package.tokens_limit,
                        'customer_id': customer_id or 'Not Linked',
                    },
                    timeout=10,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'SerialCoTV/1.0'
                    }
                )
                
                if response.status_code == 200:
                    logger.info("✅ [Async] Google Sheet updated")
                else:
                    logger.warning(f"⚠️ [Async] Google Sheet status {response.status_code}")
                    
            except Exception as sheet_err:
                logger.error(f"❌ [Async] Google Sheet failed: {sheet_err}")
                
    except Exception as e:
        logger.error(f"💥 [Async] Post-processing failed: {e}", exc_info=True)
        
    finally:
        # إغلاق اتصال DB لمنع تسريب الاتصالات
        try:
            connection.close()
            logger.debug("🔌 [Async] Database connection closed")
        except Exception as close_err:
            logger.error(f"❌ [Async] Failed to close database connection: {close_err}")


# ==================== API Views ====================

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

        if not all([serial_number, pin, customer_id]):
            return Response({
                'success': False,
                'message': 'بيانات التفعيل غير مكتملة (serial_number, pin, customer_id)'
            }, status=status.HTTP_400_BAD_REQUEST)

        # التحقق من العميل خارج نطاق atomic
        try:
            customer = Customer.objects.get(id=customer_id, is_active=True)
        except Customer.DoesNotExist:
            return Response({
                'success': False,
                'message': 'الحساب غير موجود أو غير مفعل'
            }, status=status.HTTP_404_NOT_FOUND)

        response_data = None
        
        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number,
                    pin=pin,
                    customer__isnull=True
                )

                serial_key.customer = customer
                serial_key.used_at = timezone.now()
                serial_key.save()

                Customer.objects.filter(pk=customer.pk).update(
                    token_balance=Coalesce(F('token_balance'), 0) + serial_key.tokens_remaining
                )

                response_data = {
                    'success': True,
                    'message': 'تم تفعيل السيريال بنجاح',
                    'serial': {
                        'number': serial_key.serial_number,
                        'package': serial_key.package.name if serial_key.package else '',
                        'tokens_remaining': serial_key.tokens_remaining,
                    }
                }

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو مفعل مسبقاً'
            }, status=status.HTTP_404_NOT_FOUND)

        # إرجاع الرد خارج نطاق atomic
        return Response(response_data, status=status.HTTP_200_OK)


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

        tokens_after = None
        
        try:
            with transaction.atomic():
                serial_key = SerialKey.objects.select_for_update().get(
                    serial_number=serial_number,
                    pin=pin,
                    is_active=True
                )

                # ✅ تحسين: فحص الرصيد قبل البدء في التعديل
                if serial_key.tokens_remaining < 1:
                    return Response({
                        'success': False,
                        'message': 'رصيد التوكن غير كافي'
                    }, status=status.HTTP_400_BAD_REQUEST)

                tokens_before = serial_key.tokens_remaining
                
                # استخدام use_tokens بعد التأكد من كفاية الرصيد
                serial_key.use_tokens(1)
                tokens_after = serial_key.tokens_remaining

                SerialUsage.objects.create(
                    serial_key=serial_key,
                    customer=serial_key.customer,
                    file_name=f"File_ID_{file_id}",
                    tokens_before=tokens_before,
                    tokens_after=tokens_after
                )

        except SerialKey.DoesNotExist:
            return Response({
                'success': False,
                'message': 'السيريال غير صحيح أو غير مفعل'
            }, status=status.HTTP_404_NOT_FOUND)

        # إرجاع الرد خارج نطاق atomic
        return Response({
            'success': True,
            'message': 'تم الخصم بنجاح وجاري التحميل',
            'tokens_remaining': tokens_after
        }, status=status.HTTP_200_OK)


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


# ==================== Webhook Handler ====================

@csrf_exempt
def chargily_webhook(request):
    """استقبال Webhook من Chargily بعد الدفع الناجح"""
    
    logger.info("=" * 50)
    logger.info("📥 Received Chargily Webhook")
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # 1. التحقق من التوقيع
    webhook_secret = getattr(settings, 'CHARGILY_APP_SECRET', '') or \
                     getattr(settings, 'CHARGILY_SECRET_KEY', '')
    api_secret_key = getattr(settings, 'CHARGILY_SECRET_KEY', '') or webhook_secret

    if not webhook_secret:
        logger.error("❌ Chargily webhook secret not configured")
        return JsonResponse({'error': 'Server configuration error'}, status=500)

    secret_bytes = webhook_secret.encode('utf-8') if isinstance(webhook_secret, str) else webhook_secret
    signature = request.headers.get('signature', '') or \
                request.headers.get('Chargily-Signature', '')

    computed_signature = hmac.new(
        secret_bytes, 
        request.body, 
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        logger.warning("❌ Invalid webhook signature")
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    logger.info("✅ Signature verified")

    # 2. تحليل البيانات
    raw_body_text = request.body.decode('utf-8', errors='ignore')
    
    try:
        payload = json.loads(raw_body_text)
    except json.JSONDecodeError:
        logger.error("❌ Invalid JSON")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # 3. التأكد من نوع الحدث
    if payload.get('type') != 'checkout.paid':
        logger.info(f"⏭️ Ignored event: {payload.get('type')}")
        return JsonResponse({'status': 'ignored'}, status=200)

    checkout_data = payload.get('data', {})
    checkout_id = checkout_data.get('id')
    logger.info(f"🆔 Checkout ID: {checkout_id}")

    # 4. استخراج البريد الإلكتروني
    client_email = extract_email_from_payload(checkout_data, raw_body_text)
    logger.info(f"📧 Email from payload: {client_email}")

    # 5. جلب البريد من Chargily API إذا لم يكن موجوداً
    chargily_customer_id = checkout_data.get('customer_id')
    if not client_email and chargily_customer_id:
        mode = checkout_data.get('account', {}).get('mode', 'test')
        client_email = get_chargily_customer_email(
            chargily_customer_id, 
            mode, 
            api_secret_key
        )
        logger.info(f"📧 Email from API: {client_email}")

    # 6. تحليل metadata
    metadata = parse_metadata(checkout_data.get('metadata', {}))
    client_name = metadata.get('name', '') or \
                  metadata.get('client_name', '') or \
                  'عميل SerialCo'
    logger.info(f"👤 Client: {client_name}")

    # 7. البحث عن الباقة
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
        logger.error("❌ No package found")
        return JsonResponse({'error': 'Package not found'}, status=404)

    logger.info(f"📦 Package: {package.name}")

    # 8. ربط العميل المسجل
    customer_id = metadata.get('user_id') or metadata.get('customer_id')
    customer_instance = None

    if customer_id:
        try:
            customer_instance = Customer.objects.get(id=customer_id, is_active=True)
            logger.info(f"👤 Found customer by ID: {customer_id}")
            if not client_email and getattr(customer_instance, 'email', None):
                client_email = customer_instance.email
        except Customer.DoesNotExist:
            logger.warning(f"⚠️ Customer ID {customer_id} not found")

    if not customer_instance and client_email:
        customer_instance = Customer.objects.filter(
            email__iexact=client_email,
            is_active=True
        ).first()
        
        if customer_instance:
            logger.info(f"👤 Found customer by email: {client_email}")
            customer_id = customer_instance.id
        else:
            logger.info(f"ℹ️ No customer found with email: {client_email}")

    # 9. إنشاء السيريال
    serial_id = None
    serial_number = None
    serial_pin = None
    package_id_value = package.id
    customer_instance_id = customer_instance.id if customer_instance else None
    
    try:
        with transaction.atomic():
            logger.info("🔑 Creating serial key...")
            
            create_kwargs = {
                'package': package,
                'customer': customer_instance,
                'is_active': True,
            }
            
            if customer_instance:
                create_kwargs['used_at'] = timezone.now()
            
            if checkout_id and hasattr(SerialKey, 'payment_id'):
                create_kwargs['payment_id'] = checkout_id

            serial = SerialKey.objects.create(**create_kwargs)
            
            serial_id = serial.id
            serial_number = serial.serial_number
            serial_pin = serial.pin
            
            logger.info(f"✅ Serial created!")
            logger.info(f"   Number: {serial_number}")
            logger.info(f"   PIN: {serial_pin}")
            logger.info(f"   Package: {package.name}")
            logger.info(f"   Tokens: {package.tokens_limit}")
            logger.info(f"   Customer: {customer_instance.email if customer_instance else 'None'}")

            if customer_instance:
                Customer.objects.filter(pk=customer_instance.pk).update(
                    token_balance=Coalesce(F('token_balance'), 0) + package.tokens_limit
                )
                logger.info(f"💰 Added {package.tokens_limit} tokens to customer")

    except IntegrityError:
        logger.info(f"🔄 Duplicate checkout_id detected via DB constraint: {checkout_id}")
        return JsonResponse({'status': 'already_processed'}, status=200)
        
    except Exception as create_err:
        logger.error(f"❌ Failed to create serial: {create_err}", exc_info=True)
        return JsonResponse({'error': 'Failed to create serial'}, status=500)

    # تشغيل المعالجة اللاحقة في Thread منفصل
    sheet_url = clean_url(getattr(settings, 'GOOGLE_SHEET_URL', ''))
    
    threading.Thread(
        target=async_post_processing,
        args=(
            client_email,
            client_name,
            package_id_value,
            serial_id,
            customer_instance_id,
            customer_id,
            sheet_url
        ),
        daemon=True
    ).start()
    
    logger.info("🚀 Post-processing started in background thread")
    logger.info("=" * 50)
    logger.info("🎉 Webhook completed successfully!")
    logger.info("=" * 50)
    
    return JsonResponse({
        'success': True,
        'serial': serial_number,
        'pin': serial_pin,
        'customer_linked': customer_instance is not None,
        'customer_email': client_email,
    }, status=200)
