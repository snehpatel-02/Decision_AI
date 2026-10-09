from rest_framework import serializers

from .models import Product, Recommendation, Transaction


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "sku", "name", "category", "unit_cost", "current_stock",
                  "reorder_lead_time_days"]  # persona deliberately not exposed


class TransactionSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "sku", "date", "quantity", "type"]


class RecommendationSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Recommendation
        fields = ["id", "sku", "name", "as_of", "created_at", "stock_on_hand",
                  "daily_demand", "reorder_point", "should_reorder",
                  "recommended_qty", "urgency", "confidence", "reason",
                  "outcome_actual_demand", "outcome_stockout",
                  "outcome_checked_at"]
