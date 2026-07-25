from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.utils import timezone
from .models import TVBrand, TVModel, Firmware, Schematic, DownloadToken
from accounts.models import Customer


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
        data = firmwares.values('id', 'model__brand__name', 'model__model_number', 'version', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'firmwares': list(data)})


class FirmwareDetailAPI(APIView):
    def get(self, request, pk):
        firmware = get_object_or_404(Firmware, pk=pk, is_active=True)
        
        # تحديد الرابط الحقيقي
        if firmware.file:
            real_url = request.build_absolute_uri(firmware.file.url)
        elif firmware.file_url:
            real_url = firmware.file_url
        elif firmware.cloud_url:
            real_url = firmware.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        file_name = f"{firmware.model.model_number}_v{firmware.version}.bin"
        
        # إنشاء توكن تحميل مؤقت (15 دقيقة)
        download_token = DownloadToken.generate(real_url, file_name)
        
        return Response({
            'success': True,
            'firmware': {
                'id': firmware.id,
                'model': f"{firmware.model.brand.name} - {firmware.model.model_number}",
                'version': firmware.version,
                'download_url': f"/api/download/{download_token.token}/",
                'description': firmware.description,
                'downloads_count': firmware.downloads_count,
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
        data = schematics.values('id', 'model__brand__name', 'model__model_number', 'schematic_type', 'title', 'description', 'downloads_count', 'created_at')
        return Response({'success': True, 'schematics': list(data)})


class SchematicDetailAPI(APIView):
    def get(self, request, pk):
        schematic = get_object_or_404(Schematic, pk=pk, is_active=True)
        
        if schematic.file:
            real_url = request.build_absolute_uri(schematic.file.url)
        elif schematic.file_url:
            real_url = schematic.file_url
        elif schematic.cloud_url:
            real_url = schematic.cloud_url
        else:
            return Response({'success': False, 'message': 'لا يوجد ملف'}, status=404)
        
        file_name = f"{schematic.model.model_number}_{schematic.title}.pdf"
        download_token = DownloadToken.generate(real_url, file_name)
        
        return Response({
            'success': True,
            'schematic': {
                'id': schematic.id,
                'model': f"{schematic.model.brand.name} - {schematic.model.model_number}",
                'type': schematic.get_schematic_type_display(),
                'title': schematic.title,
                'download_url': f"/api/download/{download_token.token}/",
                'description': schematic.description,
                'downloads_count': schematic.downloads_count,
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