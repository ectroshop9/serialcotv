from rest_framework import serializers
from .models import SerialKey, SerialPackage, SerialUsage


class CheckSerialSerializer(serializers.Serializer):
    serial = serializers.CharField(max_length=32, required=False)
    serial_number = serializers.CharField(max_length=32, required=False)
    pin = serializers.CharField(max_length=8, required=True)

    def validate(self, data):
        if not data.get('serial') and not data.get('serial_number'):
            raise serializers.ValidationError("يرجى إدخال السيريال")
        return data


class SerialVerifySerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=32, required=True)
    pin = serializers.CharField(max_length=8, required=True)


class ActivateSerialSerializer(serializers.Serializer):
    serial = serializers.CharField(max_length=32, required=False)
    serial_number = serializers.CharField(max_length=32, required=False)
    pin = serializers.CharField(max_length=8, required=True)
    customer_id = serializers.IntegerField(required=True)

    def validate(self, data):
        if not data.get('serial') and not data.get('serial_number'):
            raise serializers.ValidationError("يرجى إدخال السيريال")
        return data


class UseTokenSerializer(serializers.Serializer):
    serial = serializers.CharField(max_length=32, required=False)
    serial_number = serializers.CharField(max_length=32, required=False)
    pin = serializers.CharField(max_length=8, required=True)
    file_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    file_type = serializers.CharField(max_length=50, required=False, default='firmware')
    token_amount = serializers.IntegerField(required=False, default=1)

    def validate(self, data):
        if not data.get('serial') and not data.get('serial_number'):
            raise serializers.ValidationError("يرجى إدخال السيريال")
        return data


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
