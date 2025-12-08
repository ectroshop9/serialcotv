from django.http import JsonResponse

def health(request):
    return JsonResponse({
        "project": "serialcoTV",
        "status": "API is running successfully running",
        "database": "PostgreSQL ready"
    })