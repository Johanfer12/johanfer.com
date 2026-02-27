from django.contrib import admin
from .models import Book, DeletedBook, VisitLog

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'my_rating', 'date_read')
    search_fields = ('title', 'author')


@admin.register(DeletedBook)
class DeletedBookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'deleted_at')
    search_fields = ('title', 'author')


@admin.register(VisitLog)
class VisitLogAdmin(admin.ModelAdmin):
    list_display = ('visited_at', 'ip_address', 'visitor_id', 'country_code', 'country', 'path')
    search_fields = ('ip_address', 'visitor_id', 'country_code', 'country', 'path', 'user_agent')
    list_filter = ('country_code', 'country', 'visited_at')
