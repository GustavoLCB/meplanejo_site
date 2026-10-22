from django.contrib import admin
from django.urls import path

from MEPLANEJO.views import (contato, home, produto_cdb, produto_cri_cra, produto_debentures, produto_etf, produto_tesouro,
                             produto_fii, produto_fundos, produto_lci_lca, produto_previdencia, simulador,
                             simulador_metas)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('investimentos/cdb/', produto_cdb, name='produto_cdb'),
    path('investimentos/lci-lca/', produto_lci_lca, name='produto_lci_lca'),
    path('investimentos/cri-cra/', produto_cri_cra, name='produto_cri_cra'),
    path('investimentos/debentures/', produto_debentures, name='produto_debentures'),
    path('investimentos/fundos/', produto_fundos, name='produto_fundos'),
    path('investimentos/fundos-imobiliarios/', produto_fii, name='produto_fii'),
    path('investimentos/previdencia/', produto_previdencia, name='produto_previdencia'),
    path('investimentos/etf/', produto_etf, name='produto_etf'),
    path('investimentos/tesouro-direto/', produto_tesouro, name='produto_tesouro'),
    path('contato/', contato, name='contato'),
    path('simulador/', simulador, name='simulador'),
    path('metas/', simulador_metas, name='simulador_metas'),
]
