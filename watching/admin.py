from django.contrib import admin
from .models import WatchedItem


@admin.register(WatchedItem)
class WatchedItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'display_label', 'episode_title', 'watched_at', 'year')
    list_filter = ('media_type',)
    search_fields = ('title', 'episode_title')
    date_hierarchy = 'watched_at'
