from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    current_stock = models.IntegerField()
    reorder_lead_time_days = models.PositiveSmallIntegerField()
    # Generator metadata; kept for evaluation, never used as a model input.
    persona = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["sku"]

    def __str__(self):
        return f"{self.sku} {self.name}"


class Transaction(models.Model):
    SALE = "SALE"
    RESTOCK = "RESTOCK"
    TYPES = [(SALE, "Sale"), (RESTOCK, "Restock")]

    product = models.ForeignKey(Product, on_delete=models.CASCADE,
                                related_name="transactions")
    date = models.DateField(db_index=True)
    quantity = models.PositiveIntegerField()
    type = models.CharField(max_length=8, choices=TYPES)
    split = models.CharField(max_length=8, default="train")

    class Meta:
        ordering = ["date", "id"]
        indexes = [models.Index(fields=["product", "date"])]

    def __str__(self):
        return f"{self.date} {self.type} {self.quantity} {self.product.sku}"


class Recommendation(models.Model):
    """One engine call. `outcome_*` is filled later by the feedback loop."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE,
                                related_name="recommendations")
    as_of = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    stock_on_hand = models.IntegerField()
    daily_demand = models.FloatField()
    reorder_point = models.FloatField()
    should_reorder = models.BooleanField()
    recommended_qty = models.PositiveIntegerField()
    urgency = models.CharField(max_length=10)
    confidence = models.CharField(max_length=10)
    reason = models.TextField()

    # Feedback loop fields (null until the outcome is known)
    outcome_actual_demand = models.FloatField(null=True, blank=True)
    outcome_stockout = models.BooleanField(null=True, blank=True)
    outcome_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-as_of", "product__sku"]

    def __str__(self):
        return f"{self.product.sku} @ {self.as_of}: order {self.recommended_qty}"
