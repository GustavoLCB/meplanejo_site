"""Funcoes de calculo e formatacao usadas pelo site (sem dependencia do Django)."""
import re


def tratar_valor(texto):
    """Converte '10.000,50', '10000,50', 'R$ 1.500' ou '10000.50' em float."""
    if texto is None:
        return 0.0
    s = str(texto).replace('R$', '').replace('%', '').replace(' ', '').strip()
    if not s:
        return 0.0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')
    return float(s)


def brl(valor):
    """1234.5 -> '1.234,50'"""
    return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def aliquota_ir(meses):
    """Tabela regressiva da renda fixa (1 mes = 30 dias)."""
    dias = meses * 30
    if dias <= 180:
        return 0.225
    if dias <= 360:
        return 0.20
    if dias <= 720:
        return 0.175
    return 0.15


def _posicao(inicial, aporte, meses_decorridos, taxa_mensal, isento=False):
    """Situacao da carteira apos `meses_decorridos` meses.

    O valor inicial rende desde o mes 0. Cada aporte e feito no fim do mes j
    (j = 1..m) e, por isso, tem idade m - j. O IR e calculado por aporte,
    pela idade de cada um (regra real da tabela regressiva).
    """
    m = meses_decorridos
    fator = 1 + taxa_mensal
    investido = inicial + aporte * m

    bruto = inicial * fator ** m
    juros_brutos = bruto - inicial
    ir = 0.0 if isento else juros_brutos * aliquota_ir(m)

    if aporte > 0:
        for idade in range(m):  # aportes com idade 0..m-1 (idade m-j para j=1..m)
            valor = aporte * fator ** idade
            ganho = valor - aporte
            bruto += valor
            juros_brutos += ganho
            if not isento:
                ir += ganho * aliquota_ir(idade)

    return {
        'mes': m,
        'investido': investido,
        'bruto': bruto,
        'juros_brutos': juros_brutos,
        'ir': ir,
        'liquido': bruto - ir,
    }


NOMES_MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
               'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


def _fechar_resumo(final, inicial, aporte, meses):
    """Acrescenta ao resultado final os totais e percentuais exibidos na tela."""
    final['aportes_mensais'] = aporte * meses
    final['inicial'] = inicial
    final['juros_liquidos'] = final['juros_brutos'] - final['ir']
    final['aliquota_efetiva'] = (final['ir'] / final['juros_brutos'] * 100) if final['juros_brutos'] > 0 else 0.0
    final['rentabilidade_liquida'] = (final['juros_liquidos'] / final['investido'] * 100) if final['investido'] > 0 else 0.0

    total = final['bruto']
    if total > 0:
        final['pct_investido'] = final['investido'] / total * 100
        final['pct_juros'] = final['juros_liquidos'] / total * 100
        final['pct_ir'] = final['ir'] / total * 100
    else:
        final['pct_investido'] = final['pct_juros'] = final['pct_ir'] = 0.0
    return final


def simular_cdb(inicial, aporte, meses, taxa_anual_pct, isento=False):
    """Renda fixa de titulos (CDB, LCI/LCA, CRI/CRA, debentures).

    isento=False usa a tabela regressiva; isento=True nao cobra IR (LCI/LCA, CRI/CRA,
    debentures incentivadas). Retorna (resumo, evolucao).
    """
    tm = (1 + taxa_anual_pct / 100) ** (1 / 12) - 1
    evolucao = [_posicao(inicial, aporte, m, tm, isento) for m in range(meses + 1)]
    return _fechar_resumo(dict(evolucao[-1]), inicial, aporte, meses), evolucao


TIPOS_FUNDO = {
    'renda_fixa': 'Fundo de Renda Fixa (longo prazo)',
    'renda_fixa_curto': 'Fundo de Renda Fixa (curto prazo)',
    'debentures_incentivadas': 'Fundo de Debêntures Incentivadas',
    'acoes': 'Fundo de Ações',
}


def simular_fundo(inicial, aporte, meses, taxa_anual_pct, tipo, mes_inicio):
    """Simula um fundo de investimento com a tributacao de cada tipo.

    - renda_fixa (longo prazo): come-cotas de 15% no fim de maio e novembro e, no resgate,
      ajuste para a tabela regressiva (22,5% / 20% / 17,5% / 15%) sobre o ganho total.
    - renda_fixa_curto: come-cotas de 20%; no resgate, 22,5% ate 180 dias e 20% depois.
    - acoes: sem come-cotas; 15% sobre o ganho no resgate.
    - debentures_incentivadas: isento de IR para pessoa fisica, sem come-cotas.

    O valor inicial e cada aporte formam um "lote" com tributacao propria. `mes_inicio`
    (1-12) e o mes da aplicacao; aportes entram no fim de cada mes.
    """
    f = 1 + ((1 + taxa_anual_pct / 100) ** (1 / 12) - 1)
    lotes = []
    if inicial > 0:
        lotes.append({'valor': inicial, 'base': inicial, 'custo': inicial, 'cc': 0.0, 'idade': 0})
    cc_total = 0.0
    bruto_ref = inicial

    def posicao(m):
        valor_total = sum(l['valor'] for l in lotes)
        ir_resgate = 0.0
        if tipo != 'debentures_incentivadas':
            for l in lotes:
                ganho_total = l['valor'] + l['cc'] - l['custo']
                if ganho_total <= 0:
                    continue
                if tipo == 'acoes':
                    aliq = 0.15
                elif tipo == 'renda_fixa_curto':
                    aliq = 0.225 if l['idade'] * 30 <= 180 else 0.20
                else:
                    aliq = aliquota_ir(l['idade'])
                ir_resgate += max(0.0, ganho_total * aliq - l['cc'])
        investido = inicial + aporte * m
        bruto = valor_total + cc_total  # ganho do fundo antes de qualquer imposto
        return {
            'mes': m, 'investido': investido, 'bruto': bruto,
            'juros_brutos': bruto - investido,
            'ir': cc_total + ir_resgate,
            'ir_comecotas': cc_total, 'ir_resgate': ir_resgate,
            'liquido': valor_total - ir_resgate,
        }

    evolucao = [posicao(0)]
    for m in range(1, meses + 1):
        for l in lotes:
            l['valor'] *= f
            l['idade'] += 1
        mes_calendario = (mes_inicio - 1 + m - 1) % 12 + 1
        if tipo in ('renda_fixa', 'renda_fixa_curto') and mes_calendario in (5, 11):
            aliq_cc = 0.20 if tipo == 'renda_fixa_curto' else 0.15
            for l in lotes:
                ganho = l['valor'] - l['base']
                if ganho > 0:
                    imposto = ganho * aliq_cc
                    l['valor'] -= imposto
                    l['cc'] += imposto
                    cc_total += imposto
                l['base'] = l['valor']
        if aporte > 0:
            lotes.append({'valor': aporte, 'base': aporte, 'custo': aporte, 'cc': 0.0, 'idade': 0})
        evolucao.append(posicao(m))
    return _fechar_resumo(dict(evolucao[-1]), inicial, aporte, meses), evolucao


def simular_fii(inicial, aporte, meses, dy_mensal_pct, valorizacao_anual_pct, reinvestir):
    """Simula uma carteira de FIIs.

    - A cota varia `valorizacao_anual_pct` ao ano; o fundo paga `dy_mensal_pct` do valor
      das cotas todo mes (dividendos isentos de IR para pessoa fisica).
    - Se `reinvestir`, o dividendo compra novas cotas (entra no custo); senao fica em caixa.
    - Aportes entram no fim de cada mes. Na venda de tudo, o ganho de capital paga 20%.
    """
    g = (1 + valorizacao_anual_pct / 100) ** (1 / 12) - 1
    dy = dy_mensal_pct / 100
    valor, custo, caixa = float(inicial), float(inicial), 0.0
    dividendos_total = reinvestido = 0.0
    evolucao = [{'mes': 0, 'investido': inicial, 'valor': valor, 'dividendo': 0.0, 'dividendos_acum': 0.0}]
    for m in range(1, meses + 1):
        valor *= 1 + g
        div = valor * dy
        dividendos_total += div
        if reinvestir:
            valor += div
            custo += div
            reinvestido += div
        else:
            caixa += div
        valor += aporte
        custo += aporte
        evolucao.append({'mes': m, 'investido': inicial + aporte * m, 'valor': valor,
                         'dividendo': div, 'dividendos_acum': dividendos_total})
    ganho = valor - custo
    ir_venda = 0.20 * ganho if ganho > 0 else 0.0
    investido = inicial + aporte * meses
    patrimonio = valor - ir_venda + caixa
    resumo = {
        'inicial': inicial, 'aportes_mensais': aporte * meses, 'investido': investido,
        'dividendos_total': dividendos_total, 'dividendos_reinvestidos': reinvestido, 'dividendos_em_caixa': caixa,
        'valor_cotas': valor, 'custo': custo, 'ganho_capital': ganho, 'ir_venda': ir_venda,
        'renda_mensal_final': valor * dy, 'patrimonio_liquido': patrimonio,
        'resultado_liquido': patrimonio - investido,
        'rentabilidade_liquida': ((patrimonio - investido) / investido * 100) if investido > 0 else 0.0,
        'reinvestir': reinvestir,
    }
    return resumo, evolucao


def aliquota_previdencia_regressiva(meses):
    """Tabela regressiva da previdencia, pelo tempo de cada aporte."""
    if meses <= 24:
        return 0.35
    if meses <= 48:
        return 0.30
    if meses <= 72:
        return 0.25
    if meses <= 96:
        return 0.20
    if meses <= 120:
        return 0.15
    return 0.10


def simular_previdencia(inicial, aporte, meses, rent_anual_pct, plano, aliq_progressiva_pct,
                        renda_bruta_anual=0.0, aliq_marginal_pct=0.0):
    """Simula PGBL/VGBL ate o resgate total, comparando as duas tabelas de IR.

    - Regressiva: cada aporte e taxado pelo seu proprio tempo (35% ... 10%).
    - Progressiva: usa a aliquota estimada informada pelo usuario sobre a base de calculo.
    - PGBL: o IR incide sobre o total resgatado; VGBL, so sobre os rendimentos.
    - PGBL: a restituicao anual e a parcela deduzida (ate 12% da renda bruta) x aliquota marginal.
    """
    f = (1 + rent_anual_pct / 100) ** (1 / 12) - 1
    f = 1 + f
    pgbl = plano == 'pgbl'
    aliq_prog = aliq_progressiva_pct / 100

    def posicao(m):
        lotes = []  # (idade em meses, custo)
        if inicial > 0:
            lotes.append((m, inicial))
        if aporte > 0:
            lotes.extend((idade, aporte) for idade in range(m))
        bruto = ir_reg = ir_prog = 0.0
        for idade, custo in lotes:
            valor = custo * f ** idade
            base = valor if pgbl else valor - custo
            bruto += valor
            ir_reg += base * aliquota_previdencia_regressiva(idade)
            ir_prog += base * aliq_prog
        investido = inicial + aporte * m
        return {'mes': m, 'investido': investido, 'bruto': bruto,
                'ir_regressiva': ir_reg, 'liquido_regressiva': bruto - ir_reg,
                'ir_progressiva': ir_prog, 'liquido_progressiva': bruto - ir_prog}

    evolucao = [posicao(m) for m in range(meses + 1)]
    final = dict(evolucao[-1])

    beneficio = 0.0
    if pgbl:
        for ano in range((meses + 11) // 12):
            meses_no_ano = min(12, meses - 12 * ano)
            aportado_no_ano = aporte * meses_no_ano + (inicial if ano == 0 else 0)
            deducao = min(aportado_no_ano, 0.12 * renda_bruta_anual)
            beneficio += deducao * aliq_marginal_pct / 100

    final.update({
        'inicial': inicial, 'aportes_mensais': aporte * meses,
        'rendimentos': final['bruto'] - final['investido'],
        'beneficio_fiscal': beneficio, 'pgbl': pgbl,
        'aliq_efetiva_regressiva': (final['ir_regressiva'] / final['bruto'] * 100) if final['bruto'] > 0 else 0.0,
        'aliq_efetiva_progressiva': (final['ir_progressiva'] / final['bruto'] * 100) if final['bruto'] > 0 else 0.0,
        'melhor': 'regressiva' if final['liquido_regressiva'] >= final['liquido_progressiva'] else 'progressiva',
    })
    return final, evolucao


def rentabilidade_liquida_de_taxa(rent_bruta_pct, taxa_adm_pct):
    """Rentabilidade anual depois da taxa de administracao (cobrada sobre o patrimonio, ao ano)."""
    return ((1 + rent_bruta_pct / 100) * (1 - taxa_adm_pct / 100) - 1) * 100


def _simular_etf(inicial, aporte, meses, rent_anual_pct):
    """ETF: imposto de 15% sobre o ganho total, so na venda (sem come-cotas)."""
    f = (1 + rent_anual_pct / 100) ** (1 / 12)
    valor = float(inicial)
    linhas = []
    for m in range(meses + 1):
        if m > 0:
            valor = valor * f + aporte
        investido = inicial + aporte * m
        ganho = valor - investido
        ir = 0.15 * ganho if ganho > 0 else 0.0
        linhas.append({'mes': m, 'investido': investido, 'valor': valor, 'ir': ir, 'liquido': valor - ir})
    return linhas


def comparar_etf_fundo(inicial, aporte, meses, rent_bruta_pct, taxa_etf_pct, taxa_fundo_pct, tipo, mes_inicio):
    """Compara um ETF (15% sobre o ganho na venda, sem come-cotas, taxa baixa) com um fundo
    tradicional do mesmo tipo ('renda_fixa' longo prazo ou 'acoes'), com taxa propria.

    Mostra tambem o efeito da taxa de administracao: quanto cada um renderia, depois dos
    impostos, se nao cobrasse taxa nenhuma.
    """
    r_etf = rentabilidade_liquida_de_taxa(rent_bruta_pct, taxa_etf_pct)
    r_fundo = rentabilidade_liquida_de_taxa(rent_bruta_pct, taxa_fundo_pct)

    etf = _simular_etf(inicial, aporte, meses, r_etf)
    etf_sem_taxa = _simular_etf(inicial, aporte, meses, rent_bruta_pct)
    fundo, fundo_linhas = simular_fundo(inicial, aporte, meses, r_fundo, tipo, mes_inicio)
    fundo_sem_taxa, _ = simular_fundo(inicial, aporte, meses, rent_bruta_pct, tipo, mes_inicio)

    e = etf[-1]
    investido = e['investido']
    resultado = {
        'investido': investido,
        'etf': {'valor_antes_ir': e['valor'], 'ir': e['ir'], 'liquido': e['liquido'],
                'efeito_taxa': etf_sem_taxa[-1]['liquido'] - e['liquido'], 'rent_liq_anual': r_etf,
                'rentabilidade_liquida': (e['liquido'] - investido) / investido * 100 if investido > 0 else 0.0},
        'fundo': {'valor_antes_ir': fundo['bruto'] - fundo['ir_comecotas'], 'ir': fundo['ir'],
                  'ir_comecotas': fundo['ir_comecotas'], 'ir_resgate': fundo['ir_resgate'],
                  'liquido': fundo['liquido'], 'efeito_taxa': fundo_sem_taxa['liquido'] - fundo['liquido'],
                  'rent_liq_anual': r_fundo,
                  'rentabilidade_liquida': (fundo['liquido'] - investido) / investido * 100 if investido > 0 else 0.0},
        'diferenca': e['liquido'] - fundo['liquido'],
        'melhor': 'etf' if e['liquido'] >= fundo['liquido'] else 'fundo',
    }
    evolucao = [{'mes': a['mes'], 'investido': a['investido'], 'etf': a['liquido'], 'fundo': b['liquido']}
                for a, b in zip(etf, fundo_linhas)]
    return resultado, evolucao


# ---------------------------------------------------------------------------
# Metas
# ---------------------------------------------------------------------------
def taxa_mensal_equivalente(taxa_pct, periodo):
    """Converte uma taxa em % (ao ano ou ao mes) para taxa mensal decimal."""
    taxa = taxa_pct / 100
    return (1 + taxa) ** (1 / 12) - 1 if periodo == 'anual' else taxa


def calcular_meta(objetivo, inicial, meses, taxa_pct, periodo):
    """Quanto aportar por mes (fim do mes) para chegar ao objetivo.

    Se o valor que ja existe, so com os juros, ja alcanca o objetivo no prazo, nao ha aporte a
    fazer (`atingida=True`). Valores brutos, antes do Imposto de Renda.
    """
    tm = taxa_mensal_equivalente(taxa_pct, periodo)
    fator = (1 + tm) ** meses
    inicial_no_fim = inicial * fator
    resultado = {'atingida': inicial_no_fim >= objetivo, 'inicial_no_fim': inicial_no_fim,
                 'aporte': 0.0, 'total_aportado': 0.0, 'juros': 0.0, 'objetivo': objetivo,
                 'taxa_mensal': tm * 100, 'taxa_anual': ((1 + tm) ** 12 - 1) * 100}
    if resultado['atingida']:
        resultado['juros'] = inicial_no_fim - inicial
        return resultado
    falta = objetivo - inicial_no_fim
    aporte = falta / meses if tm == 0 else falta * tm / (fator - 1)
    resultado['aporte'] = aporte
    resultado['total_aportado'] = aporte * meses
    resultado['juros'] = objetivo - inicial - aporte * meses
    return resultado


# ---------------------------------------------------------------------------
# Simulador geral e Tesouro Direto: taxa que muda ao longo do tempo, cupons, custodia
# ---------------------------------------------------------------------------
def serie_taxa_decaindo(atual, futura, decaimento, meses):
    """Taxa anual (%) de cada mes (1..meses): sai de `atual` e chega a `futura` em linha reta
    ao longo de `decaimento` meses; depois fica em `futura`. Sem decaimento, `futura` vale desde
    o primeiro mes. Sem `futura`, a taxa fica sempre em `atual`."""
    if futura is None:
        return [atual] * meses
    if not decaimento or decaimento <= 0:
        return [futura] * meses
    return [atual + (futura - atual) * min(1.0, k / decaimento) for k in range(1, meses + 1)]


def simular_indexado(inicial, aporte, meses, modo, *, percentual_cdi=100.0, cdi_atual=0.0,
                     cdi_futuro=None, decaimento=0, taxa_pre=0.0, taxa_real=0.0, ipca=0.0,
                     isento=False, cupons=False, reinvestir=True, custodia_pct=0.0,
                     isencao_custodia=0.0):
    """Renda fixa com tres formas de rendimento, mes a mes:

    - 'pos':  % do CDI (ou da Selic), com o CDI indo de `cdi_atual` a `cdi_futuro` em `decaimento` meses;
    - 'pre':  taxa prefixada anual;
    - 'ipca': IPCA estimado + taxa real (hibrido): (1 + real) x (1 + IPCA) - 1.

    Tributacao pela tabela regressiva, separada por aporte (lote); `isento` zera o IR.
    `cupons=True` (so pre/ipca) paga juros a cada 6 meses de vida de cada lote: o cupom paga o
    juro acumulado, o principal segue (corrigido pelo IPCA no caso do hibrido) e o cupom e
    tributado na hora, pela idade do lote. `reinvestir` aplica o cupom liquido em novo lote
    com as mesmas condicoes; senao ele fica parado em caixa. `custodia_pct` e a taxa anual da
    B3 (Tesouro Direto), cobrada so sobre o que passa de `isencao_custodia`.
    Retorna (resumo, evolucao).
    """
    if modo == 'pos':
        cdis = serie_taxa_decaindo(cdi_atual, cdi_futuro, decaimento, meses)
        anuais = [c * percentual_cdi / 100 for c in cdis]
        reais = [0.0] * meses
    elif modo == 'pre':
        anuais = [taxa_pre] * meses
        reais = [0.0] * meses
    else:
        anuais = [((1 + taxa_real / 100) * (1 + ipca / 100) - 1) * 100] * meses
        reais = [ipca] * meses
    infl_m = [(1 + i / 100) ** (1 / 12) - 1 for i in reais]
    fatores = [(1 + a / 100) ** (1 / 12) for a in anuais]
    tem_cupom = cupons and modo != 'pos'
    taxa_custodia_m = 1 - (1 - custodia_pct / 100) ** (1 / 12) if custodia_pct else 0.0

    lotes = []
    if inicial > 0:
        lotes.append({'p': inicial, 'a': 0.0, 'custo': inicial, 'idade': 0, 'taxado': 0.0})
    caixa = ir_cupons = cupons_brutos = custodia_total = 0.0

    def posicao(m):
        valor = sum(l['p'] + l['a'] for l in lotes)
        ir_resgate = 0.0
        if not isento:
            for l in lotes:
                ganho = l['p'] + l['a'] + l['taxado'] - l['custo']
                if ganho > 0:
                    ir_resgate += ganho * aliquota_ir(l['idade'])
        investido = inicial + aporte * m
        bruto = valor + caixa + ir_cupons
        ir = ir_cupons + ir_resgate
        return {'mes': m, 'investido': investido, 'bruto': bruto, 'juros_brutos': bruto - investido,
                'ir': ir, 'liquido': bruto - ir, 'custodia': custodia_total,
                'cupons': cupons_brutos, 'ir_cupons': ir_cupons}

    evolucao = [posicao(0)]
    for k in range(1, meses + 1):
        f = fatores[k - 1]
        novos = []
        for l in lotes:
            l['idade'] += 1
            total = (l['p'] + l['a']) * f
            if tem_cupom:
                l['p'] *= 1 + infl_m[k - 1]
                l['a'] = total - l['p']
            else:
                l['p'] = total
            if tem_cupom and l['idade'] % 6 == 0 and l['a'] > 0:
                bruto_cupom = l['a']
                imposto = 0.0 if isento else bruto_cupom * aliquota_ir(l['idade'])
                liquido_cupom = bruto_cupom - imposto
                ir_cupons += imposto
                cupons_brutos += bruto_cupom
                l['a'] = 0.0
                if reinvestir:
                    novos.append({'p': liquido_cupom, 'a': 0.0, 'custo': liquido_cupom, 'idade': 0, 'taxado': 0.0})
                else:
                    caixa += liquido_cupom
        lotes.extend(novos)
        if taxa_custodia_m:
            total_pos = sum(l['p'] + l['a'] for l in lotes)
            cobranca = max(0.0, total_pos - isencao_custodia) * taxa_custodia_m
            if cobranca > 0 and total_pos > 0:
                custodia_total += cobranca
                corte = cobranca / total_pos
                for l in lotes:
                    parte = (l['p'] + l['a']) * corte
                    l['taxado'] += parte  # a taxa da B3 nao abate o IR: volta para a base
                    l['p'] -= l['p'] * corte
                    l['a'] -= l['a'] * corte
        if aporte > 0:
            lotes.append({'p': aporte, 'a': 0.0, 'custo': aporte, 'idade': 0, 'taxado': 0.0})
        evolucao.append(posicao(k))

    final = dict(evolucao[-1])
    resumo = _fechar_resumo(final, inicial, aporte, meses)
    resumo['custodia'] = custodia_total
    resumo['cupons'] = cupons_brutos
    resumo['ir_cupons'] = ir_cupons
    resumo['taxa_nominal_media'] = (sum(anuais) / len(anuais)) if anuais else 0.0
    resumo['taxa_nominal_inicial'] = anuais[0] if anuais else 0.0
    resumo['taxa_nominal_final'] = anuais[-1] if anuais else 0.0
    return resumo, evolucao
