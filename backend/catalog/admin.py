from django.contrib import admin

from .models import Book, Quote


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "price", "rating", "availability", "updated_at")
    list_filter = ("category", "rating")
    search_fields = ("title",)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("author", "text", "updated_at")
    search_fields = ("author", "text")
