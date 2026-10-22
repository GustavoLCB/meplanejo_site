from django.contrib import admin
from .models import CardInvestimento


@admin.register(CardInvestimento)
class CardInvestimentoAdmin(admin.ModelAdmin):
    list_display = ('ordem', 'titulo', 'tipo_investimento', 'icone')
    list_display_links = ('titulo',)
    list_editable = ('ordem',)
    search_fields = ('titulo',)
