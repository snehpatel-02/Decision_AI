from django.contrib import admin
from django.urls import include, path

from inventory.views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("api/", include("inventory.urls")),
]
