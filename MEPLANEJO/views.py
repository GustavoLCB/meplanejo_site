from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
from django.shortcuts import render
from django.utils import timezone

from .calculos import (NOMES_MESES, TIPOS_FUNDO, brl, calcular_meta, comparar_etf_fundo, simular_cdb, simular_fii,
                       simular_fundo, simular_indexado, simular_previdencia, tratar_valor)
from .forms import (CDBForm, ContatoForm, CRIForm, DebentureForm, ETFForm, FIIForm, FundoForm, LCIForm,
                    MetaForm, PrevidenciaForm, SimuladorForm, TesouroForm)
from .models import CardInvestimento, Visita


def obter_visitas(request):
    obj, _ = Visita.objects.get_or_create(id=1)
    if not request.session.get('visitou'):
        Visita.objects.filter(id=1).update(contagem=F('contagem') + 1)
        obj.refresh_from_db()
        request.session['visitou'] = True
    return obj.contagem


def home(request):
    cards = CardInvestimento.objects.all().order_by('ordem')
    return render(request, 'home.html', {'cards': cards, 'total_visitas': obter_visitas(request)})


def contato(request):
    sucesso = erro = False
    if request.method == 'POST':
        form = ContatoForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            corpo = f"De: {dados['nome']} <{dados['email']}>\n\n{dados['mensagem']}"
            try:
                send_mail(f"Site: {dados['assunto']}", corpo, settings.EMAIL_HOST_USER,
                          ['gus.lopescb@gmail.com'])
                sucesso = True
                form = ContatoForm()
            except Exception:
                erro = True
    else:
        form = ContatoForm()
    return render(request, 'contato.html', {'form': form, 'sucesso': sucesso, 'erro': erro,
                                            'total_visitas': obter_visitas(request)})


def _pct(v):
    return brl(v) + '%'


def _texto_taxa_indexada(modo, d, resumo):
    """Descreve em uma linha a taxa usada (para a tela de resultado)."""
    if modo == 'pos':
        t = f"{brl(d['percentual_cdi'])}% do CDI"
        if d.get('cdi_futuro') is not None:
            return t, f"CDI {_pct(d['cdi_atual'])} → {_pct(d['cdi_futuro'])}"
        return t, f"CDI {_pct(d['cdi_atual'])} constante"
    if modo == 'pre':
        return 'Pré-fixado', f"{_pct(d['taxa_prefixada'])} a.a."
    nominal = ((1 + d['taxa_real'] / 100) * (1 + d['ipca_estimado'] / 100) - 1) * 100
    return f"IPCA + {brl(d['taxa_real'])}%", f"≈ {_pct(nominal)} a.a. (IPCA {_pct(d['ipca_estimado'])})"


def _resultado_indexado(modo, d, resumo, rotulo_extra='', **extras):
    tipo_taxa, exibida = _texto_taxa_indexada(modo, d, resumo)
    d = dict(d, taxa_efetiva=resumo['taxa_nominal_media'], tipo_taxa=tipo_taxa)
    r = _formatar_resultado(resumo, d)
    r['taxa_exibida'] = exibida
    r.update(extras)
    return r


def simulador(request):
    resultado, evolucao = None, []
    if request.method == 'POST':
        form = SimuladorForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            modo = d['tipo_indexador']
            resumo, linhas = simular_indexado(
                d['valor_inicial'], d['aporte_mensal'], d['periodos'], modo,
                percentual_cdi=d.get('percentual_cdi') or 0.0, cdi_atual=d.get('cdi_atual') or 0.0,
                cdi_futuro=d.get('cdi_futuro'), decaimento=d.get('decaimento') or 0,
                taxa_pre=d.get('taxa_prefixada') or 0.0, taxa_real=d.get('taxa_real') or 0.0,
                ipca=d.get('ipca_estimado') or 0.0, isento=d['isento_ir'])
            resultado = _resultado_indexado(modo, d, resumo, isento=d['isento_ir'])
            evolucao = _linhas_evolucao(linhas)
    else:
        form = SimuladorForm()
    return render(request, 'simulador.html', {'form': form, 'resultado': resultado, 'evolucao': evolucao,
                                              'total_visitas': obter_visitas(request)})


def produto_tesouro(request):
    resultado, evolucao = None, []
    if request.method == 'POST':
        form = TesouroForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            titulo = d['titulo']
            modo = {'selic': 'pos', 'prefixado': 'pre', 'ipca': 'ipca'}[titulo]
            usa_cupons = bool(d['cupons']) and titulo != 'selic'
            dados = dict(d, percentual_cdi=100.0, cdi_atual=d.get('selic_atual'), cdi_futuro=d.get('selic_futura'))
            resumo, linhas = simular_indexado(
                d['valor_inicial'], d['aporte_mensal'], d['periodos'], modo,
                percentual_cdi=100.0, cdi_atual=d.get('selic_atual') or 0.0, cdi_futuro=d.get('selic_futura'),
                decaimento=d.get('decaimento') or 0, taxa_pre=d.get('taxa_prefixada') or 0.0,
                taxa_real=d.get('taxa_real') or 0.0, ipca=d.get('ipca_estimado') or 0.0,
                cupons=usa_cupons, reinvestir=bool(d['reinvestir']), custodia_pct=0.20,
                isencao_custodia=10000.0 if titulo == 'selic' else 0.0)
            resultado = _resultado_indexado(modo, dados, resumo, reinvestir=bool(d['reinvestir']))
            if titulo == 'selic':
                resultado['tipo_taxa'] = 'Tesouro Selic'
                resultado['taxa_exibida'] = resultado['taxa_exibida'].replace('CDI', 'Selic')
            resultado['cupons_pagos'] = brl(resumo['cupons']) if usa_cupons else ''
            resultado['ir_cupons'] = brl(resumo['ir_cupons'])
            resultado['custodia_b3'] = brl(resumo['custodia']) if resumo['custodia'] else ''
            evolucao = _linhas_evolucao(linhas)
    else:
        form = TesouroForm()
    return render(request, 'produtos/tesouro.html', {'form': form, 'resultado': resultado, 'evolucao': evolucao,
                                                     'total_visitas': obter_visitas(request)})


def simulador_metas(request):
    res = None
    if request.method == 'POST':
        form = MetaForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            m = calcular_meta(d['valor_objetivo'], d['valor_inicial'], d['tempo'], d['taxa_juros'], d['tipo_taxa'])
            res = {'atingida': m['atingida'], 'objetivo': brl(m['objetivo']), 'inicial': brl(d['valor_inicial']),
                   'inicial_no_fim': brl(m['inicial_no_fim']), 'aporte': brl(m['aporte']),
                   'total_aportado': brl(m['total_aportado']), 'juros': brl(m['juros']),
                   'tempo': d['tempo'], 'taxa_anual': brl(m['taxa_anual']), 'taxa_mensal': brl(m['taxa_mensal']),
                   'sobra': brl(m['inicial_no_fim'] - m['objetivo']) if m['atingida'] else ''}
    else:
        form = MetaForm()
    return render(request, 'simulador_metas.html', {'form': form, 'resultado': res,
                                                    'total_visitas': obter_visitas(request)})


VALORES_EM_REAIS = ('inicial', 'aportes_mensais', 'investido', 'bruto', 'juros_brutos', 'ir',
                    'ir_comecotas', 'ir_resgate', 'liquido', 'juros_liquidos')


def _formatar_resultado(resumo, d):
    """Converte o resumo numerico em textos prontos para a tela."""
    r = {k: (brl(v) if k in VALORES_EM_REAIS else v) for k, v in resumo.items()}
    r['periodos'] = d['periodos']
    r['taxa_anual'] = brl(d['taxa_efetiva'])
    r['tipo_taxa'] = d['tipo_taxa']
    r['aliquota_efetiva'] = brl(resumo['aliquota_efetiva'])
    r['rentabilidade_liquida'] = brl(resumo['rentabilidade_liquida'])
    for k in ('pct_investido', 'pct_juros', 'pct_ir'):  # largura das barras (ponto decimal para o CSS)
        r[k] = f"{resumo[k]:.2f}"
    return r


def _linhas_evolucao(linhas):
    return [{'mes': l['mes'], 'investido': brl(l['investido']), 'bruto': brl(l['bruto']),
             'ir': brl(l['ir']), 'liquido': brl(l['liquido'])} for l in linhas]


def _produto_renda_fixa(request, template, form_class, isento_fn=lambda d: False):
    resultado, evolucao = None, []
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            isento = isento_fn(d)
            resumo, linhas = simular_cdb(d['valor_inicial'], d['aporte_mensal'], d['periodos'],
                                         d['taxa_efetiva'], isento=isento)
            resultado = _formatar_resultado(resumo, d)
            resultado['isento'] = isento
            evolucao = _linhas_evolucao(linhas)
    else:
        form = form_class()
    return render(request, template, {'form': form, 'resultado': resultado, 'evolucao': evolucao,
                                      'total_visitas': obter_visitas(request)})


def produto_cdb(request):
    return _produto_renda_fixa(request, 'produtos/cdb.html', CDBForm)


def produto_lci_lca(request):
    return _produto_renda_fixa(request, 'produtos/lci_lca.html', LCIForm, isento_fn=lambda d: True)


def produto_cri_cra(request):
    return _produto_renda_fixa(request, 'produtos/cri_cra.html', CRIForm, isento_fn=lambda d: True)


def produto_debentures(request):
    return _produto_renda_fixa(request, 'produtos/debentures.html', DebentureForm,
                               isento_fn=lambda d: d['incentivada'])


def produto_fundos(request):
    resultado, evolucao = None, []
    mes_inicio = timezone.localdate().month
    if request.method == 'POST':
        form = FundoForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            resumo, linhas = simular_fundo(d['valor_inicial'], d['aporte_mensal'], d['periodos'],
                                           d['taxa_efetiva'], d['tipo_fundo'], mes_inicio)
            resultado = _formatar_resultado(resumo, d)
            resultado['fundo'] = True
            resultado['perfil'] = TIPOS_FUNDO[d['tipo_fundo']]
            resultado['tem_comecotas'] = d['tipo_fundo'] in ('renda_fixa', 'renda_fixa_curto')
            resultado['isento'] = d['tipo_fundo'] == 'debentures_incentivadas'
            evolucao = _linhas_evolucao(linhas)
    else:
        form = FundoForm()
    return render(request, 'produtos/fundos.html', {
        'form': form, 'resultado': resultado, 'evolucao': evolucao,
        'mes_inicio_nome': NOMES_MESES[mes_inicio - 1], 'total_visitas': obter_visitas(request)})


def _formatar_valores(dic, chaves_dinheiro, chaves_percentual=()):
    r = dict(dic)
    for k in chaves_dinheiro:
        r[k] = brl(dic[k])
    for k in chaves_percentual:
        r[k] = brl(dic[k])
    return r


def produto_fii(request):
    resultado, evolucao = None, []
    if request.method == 'POST':
        form = FIIForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            resumo, linhas = simular_fii(d['valor_inicial'], d['aporte_mensal'], d['periodos'],
                                         d['dividend_yield'], d['valorizacao_anual'], d['reinvestir'])
            resultado = _formatar_valores(
                resumo, ['inicial', 'aportes_mensais', 'investido', 'dividendos_total', 'dividendos_reinvestidos',
                         'dividendos_em_caixa', 'valor_cotas', 'custo', 'ganho_capital', 'ir_venda',
                         'renda_mensal_final', 'patrimonio_liquido', 'resultado_liquido'],
                ['rentabilidade_liquida'])
            resultado['periodos'] = d['periodos']
            resultado['dividend_yield'] = brl(d['dividend_yield'])
            resultado['valorizacao_anual'] = brl(d['valorizacao_anual'])
            resultado['prejuizo'] = resumo['ganho_capital'] < 0
            resultado['ganho_capital'] = brl(abs(resumo['ganho_capital']))
            evolucao = [{'mes': l['mes'], 'investido': brl(l['investido']), 'valor': brl(l['valor']),
                         'dividendo': brl(l['dividendo']), 'dividendos_acum': brl(l['dividendos_acum'])}
                        for l in linhas]
    else:
        form = FIIForm()
    return render(request, 'produtos/fii.html', {'form': form, 'resultado': resultado, 'evolucao': evolucao,
                                                 'total_visitas': obter_visitas(request)})


def produto_previdencia(request):
    resultado, evolucao = None, []
    if request.method == 'POST':
        form = PrevidenciaForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            resumo, linhas = simular_previdencia(
                d['valor_inicial'], d['aporte_mensal'], d['periodos'], d['rentabilidade_anual'], d['tipo_plano'],
                d['aliquota_progressiva'], d['renda_bruta_anual'] or 0.0, d['aliquota_marginal'] or 0.0)
            resultado = _formatar_valores(
                resumo, ['inicial', 'aportes_mensais', 'investido', 'bruto', 'rendimentos', 'ir_regressiva',
                         'liquido_regressiva', 'ir_progressiva', 'liquido_progressiva', 'beneficio_fiscal'],
                ['aliq_efetiva_regressiva', 'aliq_efetiva_progressiva'])
            resultado['periodos'] = d['periodos']
            resultado['plano'] = d['tipo_plano'].upper()
            resultado['aliquota_progressiva'] = brl(d['aliquota_progressiva'])
            resultado['rentabilidade_anual'] = brl(d['rentabilidade_anual'])
            resultado['total_regressiva'] = brl(resumo['liquido_regressiva'] + resumo['beneficio_fiscal'])
            resultado['total_progressiva'] = brl(resumo['liquido_progressiva'] + resumo['beneficio_fiscal'])
            resultado['diferenca'] = brl(abs(resumo['liquido_regressiva'] - resumo['liquido_progressiva']))
            evolucao = [{'mes': l['mes'], 'investido': brl(l['investido']), 'bruto': brl(l['bruto']),
                         'liq_reg': brl(l['liquido_regressiva']), 'liq_prog': brl(l['liquido_progressiva'])}
                        for l in linhas]
    else:
        form = PrevidenciaForm()
    return render(request, 'produtos/previdencia.html', {'form': form, 'resultado': resultado, 'evolucao': evolucao,
                                                         'total_visitas': obter_visitas(request)})


def produto_etf(request):
    resultado, evolucao = None, []
    mes_inicio = timezone.localdate().month
    if request.method == 'POST':
        form = ETFForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            r, linhas = comparar_etf_fundo(d['valor_inicial'], d['aporte_mensal'], d['periodos'],
                                           d['rentabilidade_bruta'], d['taxa_etf'], d['taxa_fundo'],
                                           d['tipo_comparacao'], mes_inicio)
            fmt = lambda dic, chaves: {k: (brl(v) if k in chaves else v) for k, v in dic.items()}  # noqa: E731
            dinheiro = ('valor_antes_ir', 'ir', 'ir_comecotas', 'ir_resgate', 'liquido', 'efeito_taxa')
            resultado = {
                'periodos': d['periodos'], 'investido': brl(r['investido']),
                'etf': fmt(r['etf'], dinheiro), 'fundo': fmt(r['fundo'], dinheiro),
                'diferenca': brl(abs(r['diferenca'])), 'melhor': r['melhor'],
                'acoes': d['tipo_comparacao'] == 'acoes',
                'rent_bruta': brl(d['rentabilidade_bruta']), 'taxa_etf': brl(d['taxa_etf']),
                'taxa_fundo': brl(d['taxa_fundo']),
            }
            for chave in ('etf', 'fundo'):
                resultado[chave]['rent_liq_anual'] = brl(r[chave]['rent_liq_anual'])
                resultado[chave]['rentabilidade_liquida'] = brl(r[chave]['rentabilidade_liquida'])
            evolucao = [{'mes': l['mes'], 'investido': brl(l['investido']), 'etf': brl(l['etf']),
                         'fundo': brl(l['fundo'])} for l in linhas]
    else:
        form = ETFForm()
    return render(request, 'produtos/etf.html', {
        'form': form, 'resultado': resultado, 'evolucao': evolucao,
        'mes_inicio_nome': NOMES_MESES[mes_inicio - 1], 'total_visitas': obter_visitas(request)})
