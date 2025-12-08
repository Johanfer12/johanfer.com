from django.contrib import admin
from django import forms
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import FeedSource, News, FilterWord, AIFilterInstruction, GroqGlobalSetting

# --- Resource para FeedSource ---
class FeedSourceResource(resources.ModelResource):
    class Meta:
        model = FeedSource
        import_id_fields = ('url',)
        skip_unchanged = True
        report_skipped = False
        # Campos a incluir (excluyendo id y campos auto-gestionados)
        fields = ('name', 'url', 'active', 'deep_search', 'similarity_threshold')
        # Campos a excluir explícitamente
        exclude = ('id', 'last_fetch',)

# --- Resource para FilterWord ---
class FilterWordResource(resources.ModelResource):
    class Meta:
        model = FilterWord
        import_id_fields = ('word',)
        skip_unchanged = True
        report_skipped = False
        # Campos a incluir (excluyendo id y campos auto-gestionados)
        fields = ('word', 'active', 'title_only')
        # Campos a excluir explícitamente
        exclude = ('id', 'created_at',)

# --- Resource para AIFilterInstruction ---
class AIFilterInstructionResource(resources.ModelResource):
    class Meta:
        model = AIFilterInstruction
        import_id_fields = ('instruction',)
        skip_unchanged = True
        report_skipped = False
        # Campos a incluir
        fields = ('instruction', 'active')
        # Campos a excluir
        exclude = ('id', 'created_at')

class FeedSourceAdminForm(forms.ModelForm):
    class Meta:
        model = FeedSource
        fields = '__all__'
        widgets = {
            'similarity_threshold': forms.NumberInput(attrs={'step': '0.01'})
        }

@admin.register(FeedSource)
class FeedSourceAdmin(ImportExportModelAdmin):
    resource_class = FeedSourceResource  # Asociar el resource personalizado
    form = FeedSourceAdminForm
    list_display = ('name', 'url', 'active', 'last_fetch', 'deep_search', 'similarity_threshold')
    list_filter = ('active', 'deep_search')
    search_fields = ('name', 'url')
    list_editable = ('active', 'deep_search')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_date', 'created_at', 'is_deleted', 'is_filtered', 'is_ai_filtered', 'is_redundant', 'filtered_by', 'similarity_score', 'ai_filter_reason')
    list_filter = ('source', 'published_date', 'is_deleted', 'is_filtered', 'is_ai_filtered', 'is_redundant', 'filtered_by')
    search_fields = ('title', 'description')
    date_hierarchy = 'published_date'
    readonly_fields = ('embedding', 'similar_to', 'similarity_score', 'is_redundant', 'filtered_by', 'ai_filter_reason', 'is_ai_filtered')
    actions = ['mark_as_deleted_by_user', 'restore_news']

    def mark_as_deleted_by_user(self, request, queryset):
        queryset.update(is_deleted=True, is_filtered=False)  # Aseguramos que no esté marcada como filtrada
    mark_as_deleted_by_user.short_description = "Marcar como eliminadas por usuario"

    def restore_news(self, request, queryset):
        # Restauramos quitando todas las marcas de filtro/eliminación
        queryset.update(is_deleted=False, is_filtered=False, is_ai_filtered=False, is_redundant=False)
    restore_news.short_description = "Restaurar noticias"

@admin.register(FilterWord)
class FilterWordAdmin(ImportExportModelAdmin):
    resource_class = FilterWordResource  # Asociar el resource personalizado
    list_display = ('word', 'active', 'title_only', 'created_at')
    list_filter = ('active', 'title_only')
    search_fields = ('word',)

@admin.register(AIFilterInstruction)
class AIFilterInstructionAdmin(ImportExportModelAdmin):
    resource_class = AIFilterInstructionResource
    list_display = ('instruction', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('instruction',)
    list_editable = ('active',)

@admin.register(GroqGlobalSetting)
class GroqGlobalSettingAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'updated_at')

    def has_add_permission(self, request):
        return not GroqGlobalSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return True
