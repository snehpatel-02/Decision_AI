from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("transactions", views.TransactionViewSet, basename="transaction")
router.register("recommendations", views.RecommendationViewSet,
                basename="recommendation")

urlpatterns = [
    path("", include(router.urls)),
    path("tools/current_stock/", views.get_current_stock),
    path("tools/sales_data/", views.get_sales_data),
]
