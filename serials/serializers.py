from rest_framework import serializers
from .models import SerialKey, SerialUsage, SerialPackage

class SerialVerifySerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=32, required=True)
    pin = serializers.CharField(max_length=8, required=True)


class SerialDownloadSerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=32, required=True)
    pin = serializers.CharField(max_length=8, required=True)
    file_id = serializers.IntegerField(required=True, help_text="معرف الملف المراد تحميله")
