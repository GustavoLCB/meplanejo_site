from django.db import models
from django.urls import reverse


class CardInvestimento(models.Model):
    OPCOES_TIPO = [
        ('CDB', 'CDB'), ('LCI_LCA', 'LCI/LCA'), ('CRI_CRA', 'CRI/CRA'),
        ('DEBENTURES', 'Debêntures'), ('FUNDOS_INVESTIMENTO', 'Fundos de Investimento'),
        ('FUNDOS_IMOBILIARIOS', 'Fundos Imobiliários'), ('TESOURO_DIRETO', 'Tesouro Direto'),
        ('PREVIDENCIA', 'Previdência'), ('ETF', 'ETF'),
    ]
    OPCOES_ICONE = [
        ('fa-chart-line', 'Gráfico de Linha'), ('fa-landmark', 'Prédio/Banco'),
        ('fa-coins', 'Moedas'), ('fa-building', 'Prédio'), ('fa-seedling', 'Planta'), ('fa-shield-alt', 'Escudo'),
        ('fa-money-bill-wave', 'Notas de Dinheiro'), ('fa-vault', 'Cofre'), ('fa-piggy-bank', 'Porquinho/Poupança'),
    ]

    # Páginas já criadas no site: tipo do card -> nome da URL. Vamos acrescentando aqui.
    PAGINAS = {
        'CDB': 'produto_cdb',
        'LCI_LCA': 'produto_lci_lca',
        'CRI_CRA': 'produto_cri_cra',
        'DEBENTURES': 'produto_debentures',
        'FUNDOS_INVESTIMENTO': 'produto_fundos',
        'FUNDOS_IMOBILIARIOS': 'produto_fii',
        'PREVIDENCIA': 'produto_previdencia',
        'ETF': 'produto_etf',
        'TESOURO_DIRETO': 'produto_tesouro',
    }

    titulo = models.CharField(max_length=100)
    tipo_investimento = models.CharField(max_length=50, choices=OPCOES_TIPO, default='CDB')
    icone = models.CharField(max_length=30, choices=OPCOES_ICONE, default='fa-coins')
    descricao = models.TextField(verbose_name="Descrição Curta")
    ordem = models.IntegerField(default=0)

    @property
    def pagina_url(self):
        nome = self.PAGINAS.get(self.tipo_investimento)
        return reverse(nome) if nome else None

    def __str__(self):
        return self.titulo


class Visita(models.Model):
    contagem = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Total: {self.contagem}"
