from django.contrib import admin
from .models import SimklSyncState, WatchedItem


@admin.register(WatchedItem)
class WatchedItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'display_label', 'episode_title', 'watched_at', 'year', 'source')
    list_filter = ('media_type', 'source')
    search_fields = ('title', 'episode_title')
    date_hierarchy = 'watched_at'


@admin.register(SimklSyncState)
class SimklSyncStateAdmin(admin.ModelAdmin):
    list_display = ('last_activity_at', 'last_synced_at')
    readonly_fields = ('last_synced_at',)
