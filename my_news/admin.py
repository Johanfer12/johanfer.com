from django.contrib import admin
from django import forms
from django.utils import timezone
from .models import FeedSource, News, FilterWord, AIFilterInstruction, AIModelSetting, IngestionStatus

class FeedSourceAdminForm(forms.ModelForm):
    class Meta:
        model = FeedSource
        fields = '__all__'
        widgets = {
            'similarity_threshold': forms.NumberInput(attrs={'step': '0.01'})
        }

@admin.register(FeedSource)
class FeedSourceAdmin(admin.ModelAdmin):
    form = FeedSourceAdminForm
    list_display = ('name', 'url', 'active', 'last_fetch', 'deep_search', 'translate_titles', 'similarity_threshold')
    list_filter = ('active', 'deep_search', 'translate_titles')
    search_fields = ('name', 'url')
    list_editable = ('active', 'deep_search', 'translate_titles')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_date', 'created_at', 'is_deleted', 'deleted_at', 'is_filtered', 'is_ai_filtered', 'is_redundant', 'filtered_by', 'similarity_score', 'ai_filter_reason')
    list_filter = ('source', 'published_date', 'is_deleted', 'is_filtered', 'is_ai_filtered', 'is_redundant', 'filtered_by')
    search_fields = ('title', 'title_es', 'description')
    date_hierarchy = 'published_date'
    readonly_fields = ('similar_to', 'similar_ref', 'similarity_score', 'is_redundant', 'filtered_by', 'ai_filter_reason', 'is_ai_filtered')
    actions = ['mark_as_deleted_by_user', 'restore_news']

    def mark_as_deleted_by_user(self, request, queryset):
        queryset.update(is_deleted=True, deleted_at=timezone.now(), is_filtered=False)  # Aseguramos que no esté marcada como filtrada
    mark_as_deleted_by_user.short_description = "Marcar como eliminadas por usuario"

    def restore_news(self, request, queryset):
        # Restauramos quitando todas las marcas de filtro/eliminación
        queryset.update(is_deleted=False, deleted_at=None, is_filtered=False, is_ai_filtered=False, is_redundant=False)
    restore_news.short_description = "Restaurar noticias"

@admin.register(FilterWord)
class FilterWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'active', 'title_only', 'created_at')
    list_filter = ('active', 'title_only')
    search_fields = ('word',)

@admin.register(AIFilterInstruction)
class AIFilterInstructionAdmin(admin.ModelAdmin):
    list_display = ('instruction', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('instruction',)
    list_editable = ('active',)

@admin.register(AIModelSetting)
class AIModelSettingAdmin(admin.ModelAdmin):
    list_display = ('provider', 'model_name', 'fallback_provider', 'updated_at')
    fields = (
        'provider', 'model_name', 'fallback_provider',
        'thinking_level', 'reasoning_effort', 'max_completion_tokens',
    )

    def has_add_permission(self, request):
        return not AIModelSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return True


@admin.register(IngestionStatus)
class IngestionStatusAdmin(admin.ModelAdmin):
    """Solo lectura: lo escribe el cron al terminar cada pasada."""

    list_display = ('state', 'reason', 'new_count', 'updated_at')
    readonly_fields = ('state', 'reason', 'detail', 'new_count', 'retry_at', 'updated_at')

    def has_add_permission(self, request):
        return False
