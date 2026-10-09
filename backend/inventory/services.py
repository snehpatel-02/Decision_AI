"""Bridge between the ORM and the pandas prediction engine."""
import pandas as pd

from engine import predict

from .models import Product, Recommendation, Transaction


def load_frames():
    products = pd.DataFrame(list(Product.objects.values(
        "sku", "name", "category", "unit_cost", "current_stock",
        "reorder_lead_time_days", "persona")))
    txns = pd.DataFrame(list(Transaction.objects.values(
        "product__sku", "date", "quantity", "type", "split")))
    txns = txns.rename(columns={"product__sku": "sku"})
    txns["date"] = pd.to_datetime(txns["date"])
    products["unit_cost"] = products["unit_cost"].astype(float)
    return products, txns


def generate_recommendations(as_of):
    """Run the engine for every product as of a date and persist the results."""
    products, txns = load_frames()
    by_sku = {p.sku: p for p in Product.objects.all()}
    saved = []
    for rec in predict.recommend_all(as_of, products, txns):
        saved.append(Recommendation.objects.create(
            product=by_sku[rec.sku], as_of=rec.as_of,
            stock_on_hand=rec.stock_on_hand, daily_demand=rec.daily_demand,
            reorder_point=rec.reorder_point, should_reorder=rec.should_reorder,
            recommended_qty=rec.recommended_qty, urgency=rec.urgency,
            confidence=rec.confidence, reason=rec.reason))
    return saved


def latest_date():
    last = Transaction.objects.order_by("-date").values_list("date", flat=True).first()
    return last
