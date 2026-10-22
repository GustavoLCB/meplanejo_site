from django import forms
from django.utils.safestring import mark_safe

from .calculos import TIPOS_FUNDO, tratar_valor


class CamposBase(forms.Form):
    """Campos comuns das paginas de produto (valor inicial, aporte e prazo)."""
    valor_inicial = forms.CharField(
        label='Valor Inicial (R$)', required=False,
        help_text='Quanto você já tem para investir hoje. Se vai começar do zero, deixe em branco e preencha o aporte mensal.',
        widget=forms.TextInput(attrs={'class': 'input-simulador campo-dinheiro', 'placeholder': 'digite aqui o valor',
                                      'inputmode': 'decimal', 'autocomplete': 'off'}))
    aporte_mensal = forms.CharField(
        label='Aporte Mensal (R$)', required=False,
        help_text='Quanto você pretende investir todo mês. Pode ficar em branco se for um investimento único.',
        widget=forms.TextInput(attrs={'class': 'input-simulador campo-dinheiro', 'placeholder': 'digite aqui o valor',
                                      'inputmode': 'decimal', 'autocomplete': 'off'}))
    periodos = forms.IntegerField(
        label='Quantidade de Períodos (Meses)', min_value=1, max_value=600,
        help_text='Por quantos meses o dinheiro ficará investido. Dica: 1 ano = 12 meses; 5 anos = 60; 10 anos = 120; 20 anos = 240.',
        error_messages={'required': 'Informe a quantidade de meses.'},
        widget=forms.NumberInput(attrs={'class': 'input-simulador', 'placeholder': 'digite aqui o valor'}))

    def _numero(self, campo, maximo, nome, minimo=0):
        texto = (self.cleaned_data.get(campo) or '').strip()
        if not texto:
            return None
        try:
            valor = tratar_valor(texto)
        except ValueError:
            raise forms.ValidationError('Digite um número válido, por exemplo 10.000,00.')
        if valor < minimo:
            if minimo == 0:
                raise forms.ValidationError(f'{nome} não pode ser negativo.')
            raise forms.ValidationError(f'{nome} não pode ser menor que {minimo:g}.'.replace('.', ','))
        if valor > maximo:
            raise forms.ValidationError('Valor muito alto.')
        return valor

    def clean_valor_inicial(self):
        return self._numero('valor_inicial', 1e12, 'O valor inicial') or 0.0

    def clean_aporte_mensal(self):
        return self._numero('aporte_mensal', 1e12, 'O aporte') or 0.0

    def clean(self):
        d = super().clean()
        if not self.errors and not d.get('valor_inicial') and not d.get('aporte_mensal'):
            raise forms.ValidationError('Informe um valor inicial ou um aporte mensal maior que zero.')
        return d


def _campo_dinheiro(label, ajuda=None, **extra):
    attrs = {'class': 'input-simulador campo-dinheiro', 'placeholder': 'digite aqui o valor',
             'inputmode': 'decimal', 'autocomplete': 'off'}
    attrs.update(extra)
    return forms.CharField(label=label, required=False, help_text=ajuda, widget=forms.TextInput(attrs=attrs))


def _campo_taxa(label, ajuda=None, **extra):
    attrs = {'class': 'input-simulador campo-taxa', 'placeholder': 'digite aqui o valor',
             'inputmode': 'decimal', 'autocomplete': 'off'}
    attrs.update(extra)
    return forms.CharField(label=label, required=False, help_text=ajuda, widget=forms.TextInput(attrs=attrs))


class RendaFixaForm(CamposBase):
    """Titulos de renda fixa: taxa prefixada OU percentual do CDI (um dos dois)."""
    taxa_prefixada = _campo_taxa('Taxa Prefixada (% ao ano)')
    percentual_cdi = _campo_taxa('Percentual do CDI (%)')
    cdi_anual = _campo_taxa('CDI Anual Vigente (%)')

    def clean_taxa_prefixada(self):
        return self._numero('taxa_prefixada', 200, 'A taxa')

    def clean_percentual_cdi(self):
        return self._numero('percentual_cdi', 1000, 'O percentual')

    def clean_cdi_anual(self):
        return self._numero('cdi_anual', 200, 'O CDI')

    def clean(self):
        d = super().clean()
        if self.errors:
            return d
        pre, pct, cdi = d.get('taxa_prefixada'), d.get('percentual_cdi'), d.get('cdi_anual')
        if pre is not None and pct is not None:
            raise forms.ValidationError('Preencha a taxa prefixada OU o percentual do CDI, não os dois.')
        if pre is None and pct is None:
            raise forms.ValidationError('Informe a taxa prefixada ou o percentual do CDI.')
        if pct is not None:
            if not cdi:
                self.add_error('cdi_anual', 'Informe o CDI anual vigente para calcular o percentual.')
                return d
            d['taxa_efetiva'] = cdi * pct / 100
            d['tipo_taxa'] = f'{pct:g}% do CDI'.replace('.', ',')
        else:
            d['taxa_efetiva'] = pre
            d['tipo_taxa'] = 'Prefixada'
        return d


# Cada pagina usa o mesmo formulario; a diferenca esta na tributacao aplicada na view.
CDBForm = LCIForm = CRIForm = RendaFixaForm


class DebentureForm(RendaFixaForm):
    incentivada = forms.BooleanField(
        label='Debênture incentivada (isenta de IR)?', required=False,
        widget=forms.CheckboxInput(attrs={'class': 'check-simulador'}))


class FundoForm(CamposBase):
    tipo_fundo = forms.ChoiceField(
        label='Tipo de Fundo', choices=list(TIPOS_FUNDO.items()),
        widget=forms.Select(attrs={'class': 'input-simulador'}))
    percentual_cdi = _campo_taxa('Percentual do CDI Estimado (%)')
    cdi_anual = _campo_taxa('CDI Anual Vigente (%)')

    def clean_percentual_cdi(self):
        valor = self._numero('percentual_cdi', 1000, 'O percentual')
        if valor is None:
            raise forms.ValidationError('Informe o percentual do CDI que o fundo deve render.')
        return valor

    def clean_cdi_anual(self):
        valor = self._numero('cdi_anual', 200, 'O CDI')
        if valor is None:
            raise forms.ValidationError('Informe o CDI anual vigente.')
        return valor

    def clean(self):
        d = super().clean()
        if not self.errors:
            d['taxa_efetiva'] = d['cdi_anual'] * d['percentual_cdi'] / 100
            d['tipo_taxa'] = f"{d['percentual_cdi']:g}% do CDI".replace('.', ',')
        return d


class FIIForm(CamposBase):
    dividend_yield = _campo_taxa('Dividend Yield Mensal (% ao mês)')
    valorizacao_anual = _campo_taxa('Valorização Anual das Cotas (%) - pode ser negativa', **{'data-negativo': '1'})
    reinvestir = forms.BooleanField(
        label='Reinvestir os dividendos?', required=False,
        widget=forms.CheckboxInput(attrs={'class': 'check-simulador'}))

    def clean_dividend_yield(self):
        valor = self._numero('dividend_yield', 10, 'O dividend yield')
        if valor is None:
            raise forms.ValidationError('Informe o dividend yield mensal, por exemplo 0,85.')
        return valor

    def clean_valorizacao_anual(self):
        valor = self._numero('valorizacao_anual', 100, 'A valorização', minimo=-50)
        return 0.0 if valor is None else valor


AJUDA_RENTABILIDADE = mark_safe(
    'Quanto você espera que o dinheiro do plano renda <strong>por ano</strong>, já <strong>descontadas as taxas</strong> do plano. Exemplo: digite 9 para 9% ao ano.'
    '<details class="ajuda-det"><summary>Não entendi: o que preencher aqui? (explicação e exemplos)</summary>'
    '<p><strong>O que é:</strong> o seu plano de previdência investe o dinheiro em um fundo. Aqui você informa quanto espera que esse fundo renda por ano, '
    '<u>depois</u> de descontar a taxa de administração (e a de carregamento, se houver). É o que realmente sobra para você.</p>'
    '<p><strong>Onde encontrar:</strong> no extrato, na lâmina ou no site do banco/seguradora do plano, procure "rentabilidade dos últimos 12 meses" e "dos últimos 5 anos", '
    'além da "taxa de administração". Confira se a rentabilidade divulgada já está líquida de taxas.</p>'
    '<p><strong>Que valor usar:</strong> seja conservador, porque o passado não garante o futuro. Como referência, planos de renda fixa costumam render perto do CDI. '
    'Exemplo: se você espera que o CDI fique em 10% ao ano e o plano rende 100% do CDI, mas cobra 1% de taxa, use cerca de 9%.</p>'
    '<p><strong>Dica para ver o resultado em valores de hoje:</strong> use a rentabilidade <u>real</u> (acima da inflação). Se você espera 10% ao ano e uma inflação de 4%, '
    'a rentabilidade real é de cerca de 5,8% (1,10 ÷ 1,04 − 1). Assim o saldo final mostra o poder de compra, não apenas o número.</p>'
    '</details>')

AJUDA_ALIQUOTA_PROGRESSIVA = mark_safe(
    'Vale só para a <strong>tabela progressiva</strong>: é o percentual de IR que você acha que vai pagar sobre o resgate (de 0 a 27,5%). <strong>Na dúvida, use 15%.</strong>'
    '<details class="ajuda-det"><summary>Não entendi: o que preencher aqui? (explicação e exemplos)</summary>'
    '<p><strong>O que é:</strong> na tabela progressiva, o imposto segue as faixas do Imposto de Renda da pessoa física (de 0% a 27,5%), a mesma que incide sobre o seu salário. '
    'O quanto você vai pagar depende da sua <u>renda total no ano do resgate</u>, que a gente não sabe hoje. Por isso o simulador pede uma estimativa da alíquota.</p>'
    '<p><strong>Como estimar:</strong><br>'
    '• Renda baixa no ano do resgate (por exemplo, só uma aposentadoria pequena): de 0% a 7,5%.<br>'
    '• Renda média: de 15% a 22,5%.<br>'
    '• Renda alta, ou um resgate grande que empurra a sua renda do ano para cima: 27,5%.</p>'
    '<p><strong>Por que 15% na dúvida:</strong> é o percentual que a instituição retém na fonte quando você resgata pela progressiva. Depois, o valor é ajustado na sua declaração anual.</p>'
    '<p><strong>Como usar o resultado:</strong> faça duas simulações, uma com 15% e outra com 27,5%. Se a regressiva ganha mesmo no melhor caso da progressiva, '
    'ela é a mais vantajosa para você. Se a progressiva ganha até no pior caso, escolha a progressiva.</p>'
    '<p><strong>Observação:</strong> este campo não altera o cálculo da tabela regressiva, que tem alíquotas fixas por tempo de aplicação.</p>'
    '</details>')

AJUDA_RENDA_BRUTA = mark_safe(
    'Vale só para o <strong>PGBL</strong>: soma do que você recebe de rendimentos tributáveis em um ano, <strong>antes dos descontos</strong>. Ela define o seu limite de dedução (12%).'
    '<details class="ajuda-det"><summary>Não entendi: o que preencher aqui? (explicação e exemplos)</summary>'
    '<p><strong>O que é:</strong> a soma anual de salários (incluindo 13º e férias), pró-labore, aposentadoria, aluguéis, ganhos de autônomo e outros rendimentos que entram no seu Imposto de Renda, '
    '<u>antes</u> de descontar INSS, dependentes ou outras deduções. Rendimentos isentos (como poupança, LCI/LCA, FGTS) não entram.</p>'
    '<p><strong>Para que serve:</strong> no PGBL você pode abater do IR as contribuições de até <strong>12% dessa renda</strong>. Exemplo: renda bruta de R$ 120.000 por ano &rarr; '
    'limite de R$ 14.400 por ano (R$ 1.200 por mês). Logo abaixo do campo, o simulador mostra esse limite enquanto você digita.</p>'
    '<p><strong>Como estimar:</strong> use o informe de rendimentos do ano anterior ou multiplique o salário bruto mensal por 13 (e some o terço de férias). '
    'Exemplo: salário bruto de R$ 10.000 &rarr; cerca de R$ 133.000 por ano.</p>'
    '<p><strong>Atenção:</strong> a dedução só vale na <u>declaração completa</u> e para quem contribui para o INSS ou para um regime próprio de previdência. '
    'Se você usa a declaração simplificada, o VGBL costuma ser mais indicado.</p>'
    '</details>')

AJUDA_ALIQUOTA_MARGINAL = mark_safe(
    'Vale só para o <strong>PGBL</strong>: a faixa do IR em que a sua renda se encaixa hoje (7,5%, 15%, 22,5% ou 27,5%). É quanto cada R$ 1 abatido te devolve de imposto.'
    '<details class="ajuda-det"><summary>Não entendi: o que preencher aqui? (explicação e exemplos)</summary>'
    '<p><strong>O que é:</strong> é a <u>maior</u> alíquota que incide sobre a sua renda tributável (depois de INSS e dependentes). Quando você deduz uma contribuição do PGBL, '
    'o imposto que deixa de pagar é essa contribuição multiplicada por essa alíquota.</p>'
    '<p><strong>Exemplo:</strong> alíquota marginal de 27,5% e contribuição dedutível de R$ 12.000 no ano &rarr; restituição estimada de R$ 3.300 (12.000 × 27,5%).</p>'
    '<p><strong>Como achar:</strong> compare a sua renda mensal tributável com a tabela mensal do IRPF no site da Receita Federal. '
    'Se a sua renda estiver na faixa de isenção (0%), o PGBL não traz benefício fiscal e o VGBL tende a ser melhor. As faixas e a isenção foram alteradas recentemente, '
    'então confira a tabela em vigor.</p>'
    '</details>')

AJUDA_TIPO_PLANO = mark_safe(
    '<strong>PGBL:</strong> abate o IR hoje (declaração completa), mas o imposto no resgate incide sobre <u>todo</u> o valor. '
    '<strong>VGBL:</strong> não abate o IR hoje, mas o imposto incide <u>só sobre o rendimento</u>.')


class PrevidenciaForm(CamposBase):
    field_order = ['tipo_plano', 'valor_inicial', 'aporte_mensal', 'periodos', 'rentabilidade_anual',
                   'aliquota_progressiva', 'renda_bruta_anual', 'aliquota_marginal']

    tipo_plano = forms.ChoiceField(
        label='Tipo de Plano', choices=[('pgbl', 'PGBL'), ('vgbl', 'VGBL')], help_text=AJUDA_TIPO_PLANO,
        widget=forms.Select(attrs={'class': 'input-simulador'}))
    rentabilidade_anual = _campo_taxa('Rentabilidade Anual do Plano, líquida de taxas (%)', AJUDA_RENTABILIDADE)
    aliquota_progressiva = _campo_taxa('Alíquota Estimada do IR na Retirada, se tabela progressiva (%)',
                                       AJUDA_ALIQUOTA_PROGRESSIVA)
    renda_bruta_anual = _campo_dinheiro('Renda Bruta Anual Tributável (R$) - só PGBL', AJUDA_RENDA_BRUTA,
                                        **{'data-so-se': 'id_tipo_plano:pgbl', 'data-limite-deducao': '12'})
    aliquota_marginal = _campo_taxa('Sua Alíquota Marginal de IR Hoje (%) - só PGBL', AJUDA_ALIQUOTA_MARGINAL,
                                    **{'data-so-se': 'id_tipo_plano:pgbl'})
    def clean_rentabilidade_anual(self):
        valor = self._numero('rentabilidade_anual', 100, 'A rentabilidade')
        if valor is None:
            raise forms.ValidationError('Informe a rentabilidade anual esperada do plano.')
        return valor

    def clean_aliquota_progressiva(self):
        valor = self._numero('aliquota_progressiva', 27.5, 'A alíquota')
        if valor is None:
            raise forms.ValidationError('Informe uma alíquota estimada (de 0 a 27,5%).')
        return valor

    def clean_renda_bruta_anual(self):
        return self._numero('renda_bruta_anual', 1e12, 'A renda')

    def clean_aliquota_marginal(self):
        return self._numero('aliquota_marginal', 27.5, 'A alíquota')

    def clean(self):
        d = super().clean()
        if not self.errors and d.get('tipo_plano') == 'pgbl':
            if not d.get('renda_bruta_anual'):
                self.add_error('renda_bruta_anual', 'No PGBL, informe a renda bruta anual para calcular a dedução.')
            if d.get('aliquota_marginal') is None:
                self.add_error('aliquota_marginal', 'No PGBL, informe sua alíquota marginal (0 a 27,5%).')
        return d


AJUDA_RENT_BRUTA = mark_safe(
    'Quanto o índice (ou a carteira) rende por ano, <strong>antes de descontar as taxas</strong>. Exemplo: 10 para 10% ao ano.'
    '<details class="ajuda-det"><summary>Não entendi: o que preencher aqui? (explicação e exemplos)</summary>'
    '<p>Para comparar de forma justa, o ETF e o fundo investem em algo parecido e rendem o <u>mesmo percentual bruto</u>. '
    'A diferença do resultado vem das <strong>taxas</strong> e dos <strong>impostos</strong>. Use um cenário conservador: o passado não garante o futuro.</p>'
    '<p>Exemplo: se você espera que o índice renda 10% ao ano, digite 10. O simulador desconta a taxa de cada um e depois calcula o imposto.</p>'
    '</details>')

AJUDA_TAXA_ETF = mark_safe(
    'Taxa de administração do ETF, em % ao ano. Em geral fica entre <strong>0,10% e 0,50%</strong>. Digite 0,20 para 0,20% ao ano.'
    '<details class="ajuda-det"><summary>Onde encontro essa taxa?</summary>'
    '<p>No site da gestora ou da B3, na página do ETF (procure "taxa de administração"). Exemplos de referência: BOVA11, cerca de 0,10% ao ano; '
    'IVVB11, cerca de 0,24%; IMAB11, cerca de 0,20%. Os valores mudam, então confira o atual.</p>'
    '</details>')

AJUDA_TAXA_FUNDO = mark_safe(
    'Taxa de administração do fundo tradicional, em % ao ano. Fundos ativos costumam cobrar de <strong>0,5% a 2%</strong>. Digite 1,50 para 1,5% ao ano.'
    '<details class="ajuda-det"><summary>Onde encontro essa taxa?</summary>'
    '<p>Na lâmina do fundo, no site da corretora ou do banco. Se o fundo também tem taxa de performance, some uma estimativa dela à taxa de administração '
    'para ter o custo total.</p>'
    '</details>')


class ETFForm(CamposBase):
    field_order = ['tipo_comparacao', 'valor_inicial', 'aporte_mensal', 'periodos', 'rentabilidade_bruta',
                   'taxa_etf', 'taxa_fundo']

    tipo_comparacao = forms.ChoiceField(
        label='O que comparar?',
        choices=[('renda_fixa', 'ETF de Renda Fixa x Fundo de Renda Fixa (longo prazo)'),
                 ('acoes', 'ETF de Ações x Fundo de Ações')],
        help_text=mark_safe('No de renda fixa, o fundo tradicional sofre <strong>come-cotas</strong>; no de ações, ambos pagam 15% sobre o lucro, '
                            'e a diferença está só na <strong>taxa</strong>.'),
        widget=forms.Select(attrs={'class': 'input-simulador'}))
    rentabilidade_bruta = _campo_taxa('Rentabilidade Anual Bruta, antes das taxas (%)', AJUDA_RENT_BRUTA)
    taxa_etf = _campo_taxa('Taxa de Administração do ETF (% ao ano)', AJUDA_TAXA_ETF)
    taxa_fundo = _campo_taxa('Taxa de Administração do Fundo (% ao ano)', AJUDA_TAXA_FUNDO)

    def clean_rentabilidade_bruta(self):
        valor = self._numero('rentabilidade_bruta', 100, 'A rentabilidade')
        if valor is None:
            raise forms.ValidationError('Informe a rentabilidade anual bruta esperada.')
        return valor

    def clean_taxa_etf(self):
        valor = self._numero('taxa_etf', 10, 'A taxa')
        if valor is None:
            raise forms.ValidationError('Informe a taxa do ETF (use 0 se não houver).')
        return valor

    def clean_taxa_fundo(self):
        valor = self._numero('taxa_fundo', 10, 'A taxa')
        if valor is None:
            raise forms.ValidationError('Informe a taxa do fundo (use 0 se não houver).')
        return valor


class MetaForm(forms.Form):
    valor_objetivo = _campo_dinheiro('Quanto quer ter? (R$)', ajuda='O valor total que você quer juntar até o fim do prazo.')
    valor_inicial = _campo_dinheiro('Quanto já tem? (R$)', ajuda='O que você já tem guardado hoje. Pode ficar em branco.')
    taxa_juros = _campo_taxa('Juros esperados (%)', ajuda='Quanto você espera que o dinheiro renda. Informe ao ano ou ao mês, conforme escolher ao lado.')
    tipo_taxa = forms.ChoiceField(choices=[('anual', 'Ao Ano'), ('mensal', 'Ao Mês')], label='A taxa é ...',
                                  widget=forms.Select(attrs={'class': 'input-simulador'}))
    tempo = forms.IntegerField(label='Prazo (Meses)', min_value=1, max_value=1200,
                               help_text='Em quantos meses você quer chegar lá. 1 ano = 12 meses; 10 anos = 120.',
                               error_messages={'required': 'Informe o prazo em meses.'},
                               widget=forms.NumberInput(attrs={'class': 'input-simulador', 'placeholder': 'digite aqui o valor'}))

    def _num(self, campo, maximo=1e12):
        texto = (self.cleaned_data.get(campo) or '').strip()
        if not texto:
            return None
        try:
            valor = tratar_valor(texto)
        except ValueError:
            raise forms.ValidationError('Digite um número válido, por exemplo 10.000,00.')
        if valor < 0:
            raise forms.ValidationError('O valor não pode ser negativo.')
        if valor > maximo:
            raise forms.ValidationError('Valor muito alto.')
        return valor

    def clean_valor_objetivo(self):
        valor = self._num('valor_objetivo')
        if not valor:
            raise forms.ValidationError('Informe o valor que você quer juntar.')
        return valor

    def clean_valor_inicial(self):
        return self._num('valor_inicial') or 0.0

    def clean_taxa_juros(self):
        valor = self._num('taxa_juros', 1000)
        if valor is None:
            raise forms.ValidationError('Informe a taxa de juros esperada.')
        return valor


AJUDA_INDEXADOR = mark_safe(
    '<details class="ajuda-det"><summary>Não entendi: qual escolher?</summary>'
    '<p><strong>Pós-fixado:</strong> rende uma porcentagem do CDI (ex.: 100% do CDI). Se o CDI muda, o rendimento muda.</p>'
    '<p><strong>Pré-fixado:</strong> a taxa é combinada na compra e não muda (ex.: 12% ao ano).</p>'
    '<p><strong>IPCA+:</strong> híbrido. Rende a inflação (IPCA) <em>mais</em> uma taxa fixa (ex.: IPCA + 6%). '
    'Como não sabemos a inflação futura, você informa uma estimativa.</p></details>')
AJUDA_DECAIMENTO = mark_safe(
    '<details class="ajuda-det"><summary>Não entendi: o que é o tempo de decaimento?</summary>'
    '<p>É em quantos meses você acha que o CDI sai do valor de hoje e chega ao valor futuro que você estimou. '
    'A mudança é feita <strong>aos poucos, em linha reta</strong>. Exemplo: CDI de hoje 14%, CDI futuro 10%, decaimento de 24 meses: '
    'em 12 meses o CDI estará em 12%, e em 24 meses em 10%, onde fica até o fim.</p>'
    '<p>Se deixar em branco (ou zero) e informar um CDI futuro, ele vale desde o primeiro mês.</p></details>')


class SimuladorForm(CamposBase):
    """Simulador geral: pos-fixado, pre-fixado ou IPCA+ (hibrido)."""
    tipo_indexador = forms.ChoiceField(
        label='Tipo de Rendimento', help_text=AJUDA_INDEXADOR,
        choices=[('pos', 'Pós-fixado (% do CDI)'), ('pre', 'Pré-fixado'), ('ipca', 'IPCA+ (híbrido)')],
        widget=forms.Select(attrs={'class': 'input-simulador'}))
    percentual_cdi = _campo_taxa('Percentual do CDI (%)', **{'data-so-se': 'id_tipo_indexador:pos'})
    cdi_atual = _campo_taxa('CDI Atual (% ao ano)', **{'data-so-se': 'id_tipo_indexador:pos'})
    cdi_futuro = _campo_taxa('CDI Estimado no Futuro (% ao ano)', ajuda='Opcional. Se em branco, o CDI de hoje é mantido.',
                             **{'data-so-se': 'id_tipo_indexador:pos'})
    decaimento = forms.IntegerField(
        label='Tempo de Decaimento (meses)', required=False, min_value=0, max_value=600, help_text=AJUDA_DECAIMENTO,
        widget=forms.NumberInput(attrs={'class': 'input-simulador', 'placeholder': 'digite aqui o valor',
                                        'data-so-se': 'id_tipo_indexador:pos'}))
    taxa_prefixada = _campo_taxa('Taxa Pré-fixada (% ao ano)', **{'data-so-se': 'id_tipo_indexador:pre'})
    taxa_real = _campo_taxa('Taxa Fixa do IPCA+ (% ao ano)', ajuda='A parte fixa do título. Ex.: em IPCA + 6%, digite 6.',
                            **{'data-so-se': 'id_tipo_indexador:ipca'})
    ipca_estimado = _campo_taxa('IPCA Estimado (% ao ano)', ajuda='A inflação média que você espera no período.',
                                **{'data-so-se': 'id_tipo_indexador:ipca'})
    isento_ir = forms.BooleanField(label='Isento de IR? (LCI, LCA, CRI, CRA, debênture incentivada...)', required=False,
                                   widget=forms.CheckboxInput(attrs={'class': 'check-simulador'}))
    field_order = ['valor_inicial', 'aporte_mensal', 'periodos', 'tipo_indexador', 'percentual_cdi', 'cdi_atual',
                   'cdi_futuro', 'decaimento', 'taxa_prefixada', 'taxa_real', 'ipca_estimado', 'isento_ir']

    def clean_percentual_cdi(self):
        return self._numero('percentual_cdi', 1000, 'O percentual')

    def clean_cdi_atual(self):
        return self._numero('cdi_atual', 200, 'O CDI')

    def clean_cdi_futuro(self):
        return self._numero('cdi_futuro', 200, 'O CDI')

    def clean_taxa_prefixada(self):
        return self._numero('taxa_prefixada', 200, 'A taxa')

    def clean_taxa_real(self):
        return self._numero('taxa_real', 200, 'A taxa')

    def clean_ipca_estimado(self):
        return self._numero('ipca_estimado', 200, 'O IPCA')

    def clean(self):
        d = super().clean()
        if self.errors:
            return d
        tipo = d.get('tipo_indexador')
        exigidos = {'pos': [('percentual_cdi', 'Informe o percentual do CDI.'), ('cdi_atual', 'Informe o CDI atual.')],
                    'pre': [('taxa_prefixada', 'Informe a taxa pré-fixada.')],
                    'ipca': [('taxa_real', 'Informe a taxa fixa do IPCA+.'), ('ipca_estimado', 'Informe o IPCA estimado.')]}
        for campo, msg in exigidos.get(tipo, []):
            if d.get(campo) is None:
                self.add_error(campo, msg)
        return d


AJUDA_TESOURO_TITULO = mark_safe(
    '<details class="ajuda-det"><summary>Não entendi: qual título escolher?</summary>'
    '<p><strong>Tesouro Selic:</strong> acompanha a taxa Selic. Preço estável, ideal para reserva de emergência.</p>'
    '<p><strong>Tesouro Prefixado:</strong> taxa fixa combinada na compra. Você sabe quanto vai receber se esperar até o vencimento.</p>'
    '<p><strong>Tesouro IPCA+:</strong> inflação (IPCA) mais uma taxa fixa. Protege o seu poder de compra.</p></details>')
AJUDA_CUPONS = mark_safe(
    '<details class="ajuda-det"><summary>Não entendi: o que são juros semestrais (cupons)?</summary>'
    '<p>Em vez de receber tudo no vencimento, você recebe os juros <strong>de 6 em 6 meses</strong>. Cada cupom já vem com o Imposto de Renda descontado '
    '(pela tabela regressiva, conforme o tempo do título).</p>'
    '<p>Se marcar "reinvestir", o simulador aplica o cupom líquido de novo, nas mesmas condições; se não marcar, o dinheiro fica parado, sem render.</p></details>')


class TesouroForm(CamposBase):
    titulo = forms.ChoiceField(
        label='Título do Tesouro Direto', help_text=AJUDA_TESOURO_TITULO,
        choices=[('selic', 'Tesouro Selic'), ('prefixado', 'Tesouro Prefixado'), ('ipca', 'Tesouro IPCA+')],
        widget=forms.Select(attrs={'class': 'input-simulador'}))
    selic_atual = _campo_taxa('Selic Atual (% ao ano)', **{'data-so-se': 'id_titulo:selic'})
    selic_futura = _campo_taxa('Selic Estimada no Futuro (% ao ano)', ajuda='Opcional. Se em branco, a Selic de hoje é mantida.',
                               **{'data-so-se': 'id_titulo:selic'})
    decaimento = forms.IntegerField(
        label='Tempo de Decaimento (meses)', required=False, min_value=0, max_value=600,
        help_text='Em quantos meses a Selic vai de hoje até a estimada (em linha reta). Em branco: a estimada vale desde o início.',
        widget=forms.NumberInput(attrs={'class': 'input-simulador', 'placeholder': 'digite aqui o valor',
                                        'data-so-se': 'id_titulo:selic'}))
    taxa_prefixada = _campo_taxa('Taxa do Título Prefixado (% ao ano)', **{'data-so-se': 'id_titulo:prefixado'})
    taxa_real = _campo_taxa('Taxa Fixa do IPCA+ (% ao ano)', ajuda='A parte fixa do título. Ex.: IPCA + 7,5%, digite 7,5.',
                            **{'data-so-se': 'id_titulo:ipca'})
    ipca_estimado = _campo_taxa('IPCA Estimado (% ao ano)', ajuda='A inflação média que você espera até o vencimento.',
                                **{'data-so-se': 'id_titulo:ipca'})
    cupons = forms.BooleanField(
        label='Com juros semestrais (cupons)?', required=False, help_text=AJUDA_CUPONS,
        widget=forms.CheckboxInput(attrs={'class': 'check-simulador', 'data-so-se': 'id_titulo:prefixado|ipca'}))
    reinvestir = forms.BooleanField(
        label='Reinvestir os cupons?', required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'check-simulador', 'data-so-se': 'id_titulo:prefixado|ipca'}))
    field_order = ['valor_inicial', 'aporte_mensal', 'periodos', 'titulo', 'selic_atual', 'selic_futura', 'decaimento',
                   'taxa_prefixada', 'taxa_real', 'ipca_estimado', 'cupons', 'reinvestir']

    def clean_selic_atual(self):
        return self._numero('selic_atual', 200, 'A Selic')

    def clean_selic_futura(self):
        return self._numero('selic_futura', 200, 'A Selic')

    def clean_taxa_prefixada(self):
        return self._numero('taxa_prefixada', 200, 'A taxa')

    def clean_taxa_real(self):
        return self._numero('taxa_real', 200, 'A taxa')

    def clean_ipca_estimado(self):
        return self._numero('ipca_estimado', 200, 'O IPCA')

    def clean(self):
        d = super().clean()
        if self.errors:
            return d
        exigidos = {'selic': [('selic_atual', 'Informe a Selic atual.')],
                    'prefixado': [('taxa_prefixada', 'Informe a taxa do título.')],
                    'ipca': [('taxa_real', 'Informe a taxa fixa do IPCA+.'), ('ipca_estimado', 'Informe o IPCA estimado.')]}
        for campo, msg in exigidos.get(d.get('titulo'), []):
            if d.get(campo) is None:
                self.add_error(campo, msg)
        return d
