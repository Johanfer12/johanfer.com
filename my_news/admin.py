from django.contrib import admin
from .models import FeedSource, News, FilterWord

@admin.register(FeedSource)
class FeedSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'active', 'last_fetch', 'deep_search')
    list_filter = ('active', 'deep_search')
    search_fields = ('name', 'url')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_date', 'created_at')
    list_filter = ('source', 'published_date')
    search_fields = ('title', 'description')
    date_hierarchy = 'published_date'

@admin.register(FilterWord)
class FilterWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('word',)
