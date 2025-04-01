from django.contrib import admin
from .models import FeedSource, News, FilterWord

@admin.register(FeedSource)
class FeedSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'active', 'last_fetch', 'deep_search')
    list_filter = ('active', 'deep_search')
    search_fields = ('name', 'url')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_date', 'created_at', 'is_deleted', 'is_filtered', 'is_redundant', 'filtered_by', 'similarity_score')
    list_filter = ('source', 'published_date', 'is_deleted', 'is_filtered', 'is_redundant', 'filtered_by')
    search_fields = ('title', 'description')
    date_hierarchy = 'published_date'
    readonly_fields = ('embedding', 'similar_to', 'similarity_score', 'is_redundant', 'filtered_by')
    actions = ['mark_as_deleted_by_user', 'restore_news']

    def mark_as_deleted_by_user(self, request, queryset):
        queryset.update(is_deleted=True, is_filtered=False)  # Aseguramos que no esté marcada como filtrada
    mark_as_deleted_by_user.short_description = "Marcar como eliminadas por usuario"

    def restore_news(self, request, queryset):
        queryset.update(is_deleted=False, is_filtered=False)  # Restauramos quitando ambas marcas
    restore_news.short_description = "Restaurar noticias"

@admin.register(FilterWord)
class FilterWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'active', 'title_only', 'created_at')
    list_filter = ('active', 'title_only')
    search_fields = ('word',)
