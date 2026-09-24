from django.urls import path

from . import views

urlpatterns = [
    path("books/<int:pk>", views.BookDetail.as_view(), name="book-detail"),
    path("search-sql", views.sql_search, name="search-sql"),
]
