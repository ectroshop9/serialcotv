from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from .models import TVBrand, TVModel, Firmware, Schematic, DownloadToken
from serials.models import SerialKey


class BrandListAPI(APIView):
    def get(self, request):
        brands = TVBrand.objects.filter(is_active=True).values('id', 'name', 'logo')
        return Response({'success': True, 'brands': list(brands)})


class ModelListAPI(APIView):
    def get(self, request):
        brand_id = request.query_params.get('brand_id')
        search = request.query_params.get('search', '')
        models = TVModel.objects.filter(is_active=True)
        if brand_id:
            models = models.filter(brand_id=brand_id)
        if search:
            models = models.filter(
                Q(model_number__icontains=search) |
                Q(chassis__icontains=search) |
                Q(brand__name__icontains=search)
            )
        data = models.select_related('brand').values('id', 'brand__name', 'model_number', 'chassis', 'screen_size', 'year', 'image')
        return Response({'success': True, 'models': list(data)})


class FirmwareListAPI(APIView):
    def get(self, request):
        model_id = request.query_params.get('model_id')
        brand_id = request.query_params.get('brand_id')
        search = request.query_params.get('search', '')
        firmwares = Firmware.objects.filter(is_active=True).select_related('model__brand')
        if model_id:
            firmwares = firmwares.filter(model_id=model_id)
        if brand_id:
            firmwares = firmwares.filter(model__brand_id=brand_id)
        if search:
            firmwares = firmwares.filter(
                Q(model__model_number__icontains=search) |
                Q(model__brand__name__icontains=search) |
                Q(version__icontains=search)
            )
        data = firmwares.values('id', 'model__brand__name', 'model__model_number', 'version', 'token_cost', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'firmwares': list(data)})


class FirmwareDetailAPI(APIView):
    def get(self, request, pk):
        firmware = get_object_or_404(Firmware, pk=pk, is_active=True)
        
        # التحقق من السيريال
        serial_number = request.query_params.get('serial_number')
        pin = request.query_params.get('pin')
        
        if not serial_number or not pin:
            return Response({'success': False, 'message': 'يرجى إدخال السيريال والبين'}, status=400)
        
        try:
            serial_key = SerialKey.objects.get(serial_number=serial_number, pin=pin, is_active=True)
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'السيريال غير صحيح'}, status=404)
        
        if serial_key.tokens_remaining < firmware.token_cost:
            return Response({'success': False, 'message': 'رصيد التوكن غير كافي'}, status=400)
        
        # خصم التوكن
        serial_key.use_tokens(firmware.token_cost)
        firmware.downloads_count += 1
        firmware.save()
        
        # تحديد الرابط الحقيقي
        if firmware.file:
            real_url = request.build_absolute_uri(firmware.file.url)
        elif firmware.file_url:
            real_url = firmware.file_url
        elif firmware.cloud_url:
            real_url = firmware.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        # إنشاء توكن تحميل مؤقت
        file_name = f"{firmware.model.model_number}_v{firmware.version}.bin"
        download_token = DownloadToken.generate(real_url, file_name, serial_key.customer)
        
        return Response({
            'success': True,
            'tokens_remaining': serial_key.tokens_remaining,
            'download_url': f"/api/download/{download_token.token}/",
            'firmware': {
                'id': firmware.id,
                'model': f"{firmware.model.brand.name} - {firmware.model.model_number}",
                'version': firmware.version,
            }
        })


class SchematicListAPI(APIView):
    def get(self, request):
        model_id = request.query_params.get('model_id')
        schematic_type = request.query_params.get('type', '')
        search = request.query_params.get('search', '')
        schematics = Schematic.objects.filter(is_active=True).select_related('model__brand')
        if model_id:
            schematics = schematics.filter(model_id=model_id)
        if schematic_type:
            schematics = schematics.filter(schematic_type=schematic_type)
        if search:
            schematics = schematics.filter(
                Q(title__icontains=search) |
                Q(model__model_number__icontains=search) |
                Q(model__brand__name__icontains=search)
            )
        data = schematics.values('id', 'model__brand__name', 'model__model_number', 'schematic_type', 'title', 'token_cost', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'schematics': list(data)})


class SchematicDetailAPI(APIView):
    def get(self, request, pk):
        schematic = get_object_or_404(Schematic, pk=pk, is_active=True)
        
        # التحقق من السيريال
        serial_number = request.query_params.get('serial_number')
        pin = request.query_params.get('pin')
        
        if not serial_number or not pin:
            return Response({'success': False, 'message': 'يرجى إدخال السيريال والبين'}, status=400)
        
        try:
            serial_key = SerialKey.objects.get(serial_number=serial_number, pin=pin, is_active=True)
        except SerialKey.DoesNotExist:
            return Response({'success': False, 'message': 'السيريال غير صحيح'}, status=404)
        
        if serial_key.tokens_remaining < schematic.token_cost:
            return Response({'success': False, 'message': 'رصيد التوكن غير كافي'}, status=400)
        
        # خصم التوكن
        serial_key.use_tokens(schematic.token_cost)
        schematic.downloads_count += 1
        schematic.save()
        
        # تحديد الرابط الحقيقي
        if schematic.file:
            real_url = request.build_absolute_uri(schematic.file.url)
        elif schematic.file_url:
            real_url = schematic.file_url
        elif schematic.cloud_url:
            real_url = schematic.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        # إنشاء توكن تحميل مؤقت
        file_name = f"{schematic.model.model_number}_{schematic.title}.pdf"
        download_token = DownloadToken.generate(real_url, file_name, serial_key.customer)
        
        return Response({
            'success': True,
            'tokens_remaining': serial_key.tokens_remaining,
            'download_url': f"/api/download/{download_token.token}/",
            'schematic': {
                'id': schematic.id,
                'model': f"{schematic.model.brand.name} - {schematic.model.model_number}",
                'title': schematic.title,
            }
        })


class DownloadFileAPI(APIView):
    def get(self, request, token):
        download_token = get_object_or_404(DownloadToken, token=token)
        
        if not download_token.is_valid():
            return HttpResponse("الرابط منتهي أو تم استخدامه", status=410)
        
        # تعليم التوكن كمستخدم
        download_token.used = True
        download_token.save()
        
        # إعادة توجيه للرابط الحقيقي
        return HttpResponseRedirect(download_token.file_url)