from rest_framework import serializers
from .models import SerialKey, SerialPackage, SerialUsage


class SerialVerifySerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=32, required=True)
    pin = serializers.CharField(max_length=8, required=True)


class SerialDownloadSerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=32, required=True)
    pin = serializers.CharField(max_length=8, required=True)
    file_id = serializers.IntegerField(required=True, help_text="معرف الملف المراد تحميله")


class SerialPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SerialPackage
        fields = '__all__'


class SerialUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SerialUsage
        fields = '__all__'
