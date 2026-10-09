from datetime import date, timedelta

from django.db.models import Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from . import services
from .models import Product, Recommendation, Transaction
from .serializers import (ProductSerializer, RecommendationSerializer,
                          TransactionSerializer)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = "sku"


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        qs = Transaction.objects.select_related("product")
        p = self.request.query_params
        if p.get("sku"):
            qs = qs.filter(product__sku=p["sku"])
        if p.get("type"):
            qs = qs.filter(type=p["type"].upper())
        if p.get("start"):
            qs = qs.filter(date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(date__lte=p["end"])
        return qs


class RecommendationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    serializer_class = RecommendationSerializer

    def get_queryset(self):
        qs = Recommendation.objects.select_related("product")
        p = self.request.query_params
        if p.get("urgency"):
            qs = qs.filter(urgency=p["urgency"])
        if p.get("sku"):
            qs = qs.filter(product__sku=p["sku"])
        return qs

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """POST {"as_of": "YYYY-MM-DD"} (defaults to the latest data date)."""
        as_of = request.data.get("as_of") or services.latest_date()
        saved = services.generate_recommendations(as_of)
        return Response(RecommendationSerializer(saved, many=True).data,
                        status=201)


# --- Tool endpoints: the AI assistant calls these, never the DB directly ---

@api_view(["GET"])
def get_current_stock(request):
    sku = request.query_params.get("sku")
    qs = Product.objects.filter(sku=sku) if sku else Product.objects.all()
    return Response([{"sku": p.sku, "name": p.name,
                      "current_stock": p.current_stock} for p in qs])


@api_view(["GET"])
def get_sales_data(request):
    """Units sold per SKU over the last `days` days of data (default 7)."""
    days = int(request.query_params.get("days", 7))
    end = services.latest_date() or date.today()
    start = end - timedelta(days=days - 1)
    qs = Transaction.objects.filter(type="SALE", date__gte=start, date__lte=end)
    if request.query_params.get("sku"):
        qs = qs.filter(product__sku=request.query_params["sku"])
    rows = (qs.values("product__sku").annotate(units=Sum("quantity"))
            .order_by("product__sku"))
    return Response({"start": start, "end": end,
                     "sales": [{"sku": r["product__sku"], "units": r["units"]}
                               for r in rows]})
