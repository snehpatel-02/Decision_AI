from django.contrib import admin

from .models import Product, Recommendation, Transaction

admin.site.register(Product)
admin.site.register(Transaction)
admin.site.register(Recommendation)
