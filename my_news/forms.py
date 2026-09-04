from django import forms

from .models import AIFilterInstruction, FeedSource, FilterWord


class FeedSourceForm(forms.ModelForm):
    similarity_threshold = forms.FloatField(
        min_value=0,
        max_value=1,
        label="Umbral de similitud",
        help_text="Entre 0 y 1. Con 0,85 se detectan más duplicados; 0,92 es más estricto.",
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )

    class Meta:
        model = FeedSource
        fields = ("name", "url", "active", "deep_search", "similarity_threshold")
        labels = {
            "name": "Nombre",
            "url": "Dirección del feed RSS",
            "active": "Fuente activa",
            "deep_search": "Leer el artículo completo",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "url": forms.URLInput(attrs={"placeholder": "https://ejemplo.com/feed.xml"}),
        }

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        duplicate = FeedSource.objects.filter(url__iexact=url).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Ya existe una fuente con esta dirección.")
        return url


class FilterWordForm(forms.ModelForm):
    class Meta:
        model = FilterWord
        fields = ("word", "active", "title_only")
        labels = {
            "word": "Palabra o frase",
            "active": "Filtro activo",
            "title_only": "Buscar solo en el título",
        }
        widgets = {
            "word": forms.TextInput(
                attrs={"autocomplete": "off", "placeholder": "Ej. horóscopo"}
            ),
        }


class AIFilterInstructionForm(forms.ModelForm):
    class Meta:
        model = AIFilterInstruction
        fields = ("instruction", "active")
        labels = {
            "instruction": "Qué contenido debe filtrar la IA",
            "active": "Instrucción activa",
        }
        widgets = {
            "instruction": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Ej. Artículos de opinión política muy sesgados",
                }
            ),
        }
