from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Liveness check for healthcheck.sh / monitoring: the Django process is up and answering."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health),
    path("api/", include("search.urls")),
    path("api/", include("catalog.urls")),
]
