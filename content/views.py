from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import TVBrand, TVModel, Firmware, Schematic

class BrandListAPI(APIView):
    def get(self, request):
        brands = TVBrand.objects.filter(is_active=True).values('id', 'name', 'logo')
        return Response({
            'success': True,
            'brands': list(brands)
        })


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
        
        data = models.select_related('brand').values(
            'id', 'brand__name', 'model_number', 'chassis', 'screen_size', 'year', 'image'
        )
        
        return Response({
            'success': True,
            'models': list(data)
        })


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
        
        data = firmwares.values(
            'id', 'model__brand__name', 'model__model_number',
            'version', 'file', 'file_url', 'cloud_url', 'description', 'downloads_count', 'created_at'
        )
        
        return Response({
            'success': True,
            'firmwares': list(data)
        })


class FirmwareDetailAPI(APIView):
    def get(self, request, pk):
        firmware = get_object_or_404(Firmware, pk=pk, is_active=True)
        
        firmware.downloads_count += 1
        firmware.save()
        
        file_link = None
        if firmware.file:
            file_link = request.build_absolute_uri(firmware.file.url)
        elif firmware.file_url:
            file_link = firmware.file_url
        elif firmware.cloud_url:
            file_link = firmware.cloud_url
        
        return Response({
            'success': True,
            'firmware': {
                'id': firmware.id,
                'model': f"{firmware.model.brand.name} - {firmware.model.model_number}",
                'version': firmware.version,
                'file': file_link,
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
        
        data = schematics.values(
            'id', 'model__brand__name', 'model__model_number',
            'schematic_type', 'title', 'file', 'file_url', 'cloud_url', 'description', 'downloads_count', 'created_at'
        )
        
        return Response({
            'success': True,
            'schematics': list(data)
        })


class SchematicDetailAPI(APIView):
    def get(self, request, pk):
        schematic = get_object_or_404(Schematic, pk=pk, is_active=True)
        
        schematic.downloads_count += 1
        schematic.save()
        
        file_link = None
        if schematic.file:
            file_link = request.build_absolute_uri(schematic.file.url)
        elif schematic.file_url:
            file_link = schematic.file_url
        elif schematic.cloud_url:
            file_link = schematic.cloud_url
        
        return Response({
            'success': True,
            'schematic': {
                'id': schematic.id,
                'model': f"{schematic.model.brand.name} - {schematic.model.model_number}",
                'type': schematic.get_schematic_type_display(),
                'title': schematic.title,
                'file': file_link,
                'description': schematic.description,
                'downloads_count': schematic.downloads_count,
            }
        })