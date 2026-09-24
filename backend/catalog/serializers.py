from rest_framework import serializers

from .models import Book


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "price", "rating", "availability", "category", "description",
                  "url", "image_url", "updated_at"]


class BookListSerializer(serializers.ModelSerializer):
    """Smaller shape for result lists, same fields as the ES search results."""

    class Meta:
        model = Book
        fields = ["id", "title", "price", "rating", "availability", "category", "image_url"]
