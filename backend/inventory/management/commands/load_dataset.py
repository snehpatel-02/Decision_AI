import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Product, Transaction


class Command(BaseCommand):
    help = "Load products.csv and transactions.csv from DATASET_DIR (idempotent)."

    @transaction.atomic
    def handle(self, *args, **opts):
        d = settings.DATASET_DIR
        products = pd.read_csv(d / "products.csv")
        txns = pd.read_csv(d / "transactions.csv", parse_dates=["date"])

        Transaction.objects.all().delete()
        Product.objects.all().delete()

        by_sku = {}
        for r in products.itertuples():
            by_sku[r.sku] = Product.objects.create(
                sku=r.sku, name=r.name, category=r.category,
                unit_cost=r.unit_cost, current_stock=int(r.current_stock),
                reorder_lead_time_days=int(r.reorder_lead_time_days),
                persona=r.persona)

        Transaction.objects.bulk_create([
            Transaction(product=by_sku[t.sku], date=t.date.date(),
                        quantity=int(t.quantity), type=t.type, split=t.split)
            for t in txns.itertuples()], batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(by_sku)} products, {len(txns)} transactions"))
