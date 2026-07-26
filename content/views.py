from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from .models import TVBrand, Firmware, Schematic, DownloadToken
from serials.models import SerialKey


class BrandListAPI(APIView):
    def get(self, request):
        brands = TVBrand.objects.filter(is_active=True).values('id', 'name', 'logo')
        return Response({'success': True, 'brands': list(brands)})


class FirmwareListAPI(APIView):
    def get(self, request):
        brand_id = request.query_params.get('brand_id')
        search = request.query_params.get('search', '')
        firmwares = Firmware.objects.filter(is_active=True).select_related('brand')
        if brand_id:
            firmwares = firmwares.filter(brand_id=brand_id)
        if search:
            firmwares = firmwares.filter(
                Q(model_number__icontains=search) |
                Q(brand__name__icontains=search) |
                Q(version__icontains=search)
            )
        data = firmwares.values('id', 'brand__name', 'model_number', 'version', 'token_cost', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'firmwares': list(data)})


class FirmwareDetailAPI(APIView):
    def get(self, request, pk):
        firmware = get_object_or_404(Firmware, pk=pk, is_active=True)
        
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
        
        serial_key.use_tokens(firmware.token_cost)
        firmware.downloads_count += 1
        firmware.save()
        
        if firmware.file:
            real_url = request.build_absolute_uri(firmware.file.url)
        elif firmware.file_url:
            real_url = firmware.file_url
        elif firmware.cloud_url:
            real_url = firmware.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        file_name = f"{firmware.brand.name}_{firmware.model_number}_v{firmware.version}.bin"
        download_token = DownloadToken.generate(real_url, file_name, serial_key.customer)
        
        return Response({
            'success': True,
            'tokens_remaining': serial_key.tokens_remaining,
            'download_url': f"/api/download/{download_token.token}/",
            'firmware': {
                'id': firmware.id,
                'brand': firmware.brand.name,
                'model_number': firmware.model_number,
                'version': firmware.version,
            }
        })


class SchematicListAPI(APIView):
    def get(self, request):
        brand_id = request.query_params.get('brand_id')
        schematic_type = request.query_params.get('type', '')
        search = request.query_params.get('search', '')
        schematics = Schematic.objects.filter(is_active=True).select_related('brand')
        if brand_id:
            schematics = schematics.filter(brand_id=brand_id)
        if schematic_type:
            schematics = schematics.filter(schematic_type=schematic_type)
        if search:
            schematics = schematics.filter(
                Q(title__icontains=search) |
                Q(model_number__icontains=search) |
                Q(brand__name__icontains=search)
            )
        data = schematics.values('id', 'brand__name', 'model_number', 'schematic_type', 'title', 'token_cost', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'schematics': list(data)})


class SchematicDetailAPI(APIView):
    def get(self, request, pk):
        schematic = get_object_or_404(Schematic, pk=pk, is_active=True)
        
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
        
        serial_key.use_tokens(schematic.token_cost)
        schematic.downloads_count += 1
        schematic.save()
        
        if schematic.file:
            real_url = request.build_absolute_uri(schematic.file.url)
        elif schematic.file_url:
            real_url = schematic.file_url
        elif schematic.cloud_url:
            real_url = schematic.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        file_name = f"{schematic.brand.name}_{schematic.model_number}_{schematic.title}.pdf"
        download_token = DownloadToken.generate(real_url, file_name, serial_key.customer)
        
        return Response({
            'success': True,
            'tokens_remaining': serial_key.tokens_remaining,
            'download_url': f"/api/download/{download_token.token}/",
            'schematic': {
                'id': schematic.id,
                'brand': schematic.brand.name,
                'model_number': schematic.model_number,
                'title': schematic.title,
            }
        })


class DownloadFileAPI(APIView):
    def get(self, request, token):
        download_token = get_object_or_404(DownloadToken, token=token)
        
        if not download_token.is_valid():
            return HttpResponse("الرابط منتهي أو تم استخدامه", status=410)
        
        download_token.used = True
        download_token.save()
        
        return HttpResponseRedirect(download_token.file_url)