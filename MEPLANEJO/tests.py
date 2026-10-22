from django.test import TestCase
from django.urls import reverse

from .calculos import aliquota_ir, brl, simular_cdb, calcular_meta, comparar_etf_fundo, serie_taxa_decaindo, simular_indexado, simular_fii, simular_fundo, simular_previdencia, tratar_valor
from .models import CardInvestimento


class CalculosTests(TestCase):
    def test_tratar_valor(self):
        self.assertEqual(tratar_valor('10.000,50'), 10000.5)
        self.assertEqual(tratar_valor('10000,50'), 10000.5)
        self.assertEqual(tratar_valor('10000.50'), 10000.5)
        self.assertEqual(tratar_valor('1.500'), 1500.0)
        self.assertEqual(tratar_valor('R$ 2.000,00'), 2000.0)
        self.assertEqual(tratar_valor(''), 0.0)

    def test_brl(self):
        self.assertEqual(brl(1234567.891), '1.234.567,89')

    def test_aliquotas(self):
        self.assertEqual(aliquota_ir(6), 0.225)
        self.assertEqual(aliquota_ir(7), 0.20)
        self.assertEqual(aliquota_ir(12), 0.20)
        self.assertEqual(aliquota_ir(13), 0.175)
        self.assertEqual(aliquota_ir(24), 0.175)
        self.assertEqual(aliquota_ir(25), 0.15)

    def test_cdb_sem_aporte(self):
        # 10.000 a 12% a.a. por 12 meses: juros 1.200, IR 20% = 240
        r, _ = simular_cdb(10000, 0, 12, 12)
        self.assertAlmostEqual(r['juros_brutos'], 1200, places=2)
        self.assertAlmostEqual(r['ir'], 240, places=2)
        self.assertAlmostEqual(r['liquido'], 10960, places=2)

    def test_cdb_fecha_as_contas(self):
        r, evolucao = simular_cdb(5000, 300, 30, 11.5)
        self.assertEqual(len(evolucao), 31)
        self.assertAlmostEqual(r['investido'], 5000 + 300 * 30, places=2)
        self.assertAlmostEqual(r['liquido'], r['investido'] + r['juros_brutos'] - r['ir'], places=2)
        self.assertAlmostEqual(r['juros_liquidos'], r['juros_brutos'] - r['ir'], places=2)
        self.assertTrue(0.15 * r['juros_brutos'] <= r['ir'] <= 0.225 * r['juros_brutos'])

    def test_ir_por_aporte_menor_que_aliquota_unica(self):
        # Aportes recentes pagam aliquota maior, mas o inicial (antigo) paga 15%:
        # o IR total fica entre 15% e 22,5% dos juros, nunca fora disso.
        r, _ = simular_cdb(10000, 1000, 36, 12)
        self.assertGreater(r['aliquota_efetiva'], 15)
        self.assertLess(r['aliquota_efetiva'], 22.5)


class PaginasTests(TestCase):
    def test_paginas_abrem(self):
        for nome in ['home', 'produto_cdb', 'produto_lci_lca', 'produto_cri_cra', 'produto_debentures',
                     'produto_fundos', 'produto_fii', 'produto_previdencia', 'produto_etf', 'produto_tesouro', 'simulador', 'simulador_metas', 'contato']:
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_card_cdb_aponta_para_pagina(self):
        card = CardInvestimento.objects.create(titulo='CDB', tipo_investimento='CDB', descricao='x')
        self.assertEqual(card.pagina_url, reverse('produto_cdb'))
        for tipo, nome in [('LCI_LCA', 'produto_lci_lca'), ('CRI_CRA', 'produto_cri_cra'),
                           ('DEBENTURES', 'produto_debentures'), ('FUNDOS_INVESTIMENTO', 'produto_fundos'),
                           ('FUNDOS_IMOBILIARIOS', 'produto_fii'), ('PREVIDENCIA', 'produto_previdencia'),
                           ('ETF', 'produto_etf')]:
            c = CardInvestimento.objects.create(titulo=tipo, tipo_investimento=tipo, descricao='x')
            self.assertEqual(c.pagina_url, reverse(nome))
        for tipo in ():
            em_breve = CardInvestimento.objects.create(titulo=tipo, tipo_investimento=tipo, descricao='x')
            self.assertIsNone(em_breve.pagina_url)

    def _post(self, **extra):
        dados = {'valor_inicial': '10.000,00', 'aporte_mensal': '500,00', 'periodos': '24',
                 'taxa_prefixada': '12,00', 'percentual_cdi': '', 'cdi_anual': ''}
        dados.update(extra)
        return self.client.post(reverse('produto_cdb'), dados)

    def test_pagina_cdb_comeca_sem_valores(self):
        r = self.client.get(reverse('produto_cdb'))
        self.assertContains(r, 'digite aqui o valor')
        self.assertNotContains(r, 'value="10.000,00"')
        self.assertNotContains(r, 'value="500,00"')

    def test_simulacao_taxa_prefixada(self):
        r = self._post()
        self.assertContains(r, 'Valor líquido final em 24 meses')
        self.assertContains(r, 'Imposto de Renda pago')
        self.assertContains(r, 'Prefixada')

    def test_simulacao_percentual_cdi(self):
        r = self._post(taxa_prefixada='', percentual_cdi='110', cdi_anual='10')  # 110% de 10% = 11% a.a.
        self.assertContains(r, 'Valor líquido final')
        self.assertContains(r, '110% do CDI')
        self.assertContains(r, '11,00% a.a.')

    def test_cdi_exige_cdi_anual(self):
        r = self._post(taxa_prefixada='', percentual_cdi='110', cdi_anual='')
        self.assertNotContains(r, 'Valor líquido final')
        self.assertContains(r, 'Informe o CDI anual vigente')

    def test_nao_aceita_os_dois_tipos_de_taxa(self):
        r = self._post(percentual_cdi='100', cdi_anual='10')
        self.assertNotContains(r, 'Valor líquido final')
        self.assertContains(r, 'não os dois')

    def test_exige_uma_taxa(self):
        r = self._post(taxa_prefixada='')
        self.assertNotContains(r, 'Valor líquido final')
        self.assertContains(r, 'Informe a taxa prefixada ou o percentual do CDI')

    def test_cdb_valida_campos(self):
        r = self._post(valor_inicial='abc', periodos='0', taxa_prefixada='-1')
        self.assertNotContains(r, 'Valor líquido final')
        self.assertContains(r, 'erro-campo')

    def test_cdb_exige_algum_valor(self):
        r = self._post(valor_inicial='', aporte_mensal='')
        self.assertContains(r, 'Informe um valor inicial ou um aporte')

    def test_so_aporte_mensal_funciona(self):
        r = self._post(valor_inicial='', aporte_mensal='1.000,00')
        self.assertContains(r, 'Valor líquido final')


class IsencaoETributacaoTests(TestCase):
    def test_titulo_isento_nao_paga_ir(self):
        r, _ = simular_cdb(10000, 500, 24, 11, isento=True)
        self.assertEqual(r['ir'], 0)
        self.assertAlmostEqual(r['liquido'], r['bruto'], places=6)

    def test_lci_na_pagina_nao_cobra_ir(self):
        r = self.client.post(reverse('produto_lci_lca'), {
            'valor_inicial': '10.000,00', 'aporte_mensal': '', 'periodos': '12', 'taxa_prefixada': '10,00'})
        self.assertContains(r, '(isento)')
        self.assertContains(r, 'R$ 11.000,00')  # 10.000 a 10% a.a. em 12 meses, sem IR

    def test_cri_na_pagina_nao_cobra_ir(self):
        r = self.client.post(reverse('produto_cri_cra'), {
            'valor_inicial': '10.000,00', 'aporte_mensal': '', 'periodos': '12', 'taxa_prefixada': '10,00'})
        self.assertContains(r, 'R$ 11.000,00')

    def test_debenture_comum_x_incentivada(self):
        base = {'valor_inicial': '10.000,00', 'aporte_mensal': '', 'periodos': '12', 'taxa_prefixada': '10,00'}
        comum = self.client.post(reverse('produto_debentures'), base)
        self.assertContains(comum, 'R$ 10.800,00')  # 1.000 de juros, IR 20% = 200
        incentivada = self.client.post(reverse('produto_debentures'), dict(base, incentivada='on'))
        self.assertContains(incentivada, 'R$ 11.000,00')
        self.assertContains(incentivada, '(isento)')

    def test_pagina_debentures_tem_flag(self):
        r = self.client.get(reverse('produto_debentures'))
        self.assertContains(r, 'Debênture incentivada (isenta de IR)?')


class FundosTests(TestCase):
    def test_fundo_de_acoes_15_por_cento_sem_comecotas(self):
        r, _ = simular_fundo(10000, 0, 12, 10, 'acoes', mes_inicio=1)
        self.assertAlmostEqual(r['juros_brutos'], 1000, places=2)
        self.assertAlmostEqual(r['ir'], 150, places=2)
        self.assertEqual(r['ir_comecotas'], 0)
        self.assertAlmostEqual(r['liquido'], 10850, places=2)

    def test_fundo_debentures_incentivadas_isento(self):
        r, _ = simular_fundo(10000, 500, 24, 11, 'debentures_incentivadas', mes_inicio=3)
        self.assertEqual(r['ir'], 0)
        self.assertAlmostEqual(r['liquido'], r['bruto'], places=6)

    def test_fundo_renda_fixa_comecotas_e_ajuste(self):
        # Inicio em janeiro: come-cotas em maio (m=5) e novembro (m=11) dentro de 12 meses.
        r, evo = simular_fundo(10000, 0, 12, 12, 'renda_fixa', mes_inicio=1)
        self.assertGreater(r['ir_comecotas'], 0)
        # Sem aportes, imposto total = aliquota final (12 meses = 20%) sobre o ganho total.
        self.assertAlmostEqual(r['ir'], 0.20 * r['juros_brutos'], places=6)
        self.assertAlmostEqual(r['liquido'], r['investido'] + r['juros_brutos'] - r['ir'], places=6)
        self.assertEqual(evo[4]['ir_comecotas'], 0)   # antes de maio nao ha come-cotas
        self.assertGreater(evo[5]['ir_comecotas'], 0)  # apos maio, sim

    def test_comecotas_reduz_rendimento_frente_ao_cdb(self):
        fundo, _ = simular_fundo(10000, 0, 36, 12, 'renda_fixa', mes_inicio=1)
        cdb, _ = simular_cdb(10000, 0, 36, 12)
        self.assertLess(fundo['liquido'], cdb['liquido'])
        self.assertGreater(fundo['liquido'], cdb['liquido'] * 0.99)

    def test_fundo_renda_fixa_com_aportes_fecha_as_contas(self):
        r, evo = simular_fundo(5000, 300, 30, 11, 'renda_fixa', mes_inicio=6)
        self.assertEqual(len(evo), 31)
        self.assertAlmostEqual(r['liquido'], r['investido'] + r['juros_brutos'] - r['ir'], places=6)
        self.assertTrue(0.15 * r['juros_brutos'] - 1e-6 <= r['ir'] <= 0.225 * r['juros_brutos'] + 1e-6)

    def test_pagina_fundos_simulacao(self):
        base = {'valor_inicial': '10.000,00', 'aporte_mensal': '200,00', 'periodos': '36',
                'percentual_cdi': '100', 'cdi_anual': '10,50'}
        for tipo, texto in [('renda_fixa', 'Come-cotas'), ('acoes', 'Fundo de Ações'),
                            ('debentures_incentivadas', 'isento')]:
            r = self.client.post(reverse('produto_fundos'), dict(base, tipo_fundo=tipo))
            self.assertContains(r, 'Valor líquido final em 36 meses')
            self.assertContains(r, texto)

    def test_fundo_exige_percentual_e_cdi(self):
        r = self.client.post(reverse('produto_fundos'), {
            'valor_inicial': '1.000,00', 'periodos': '12', 'tipo_fundo': 'acoes'})
        self.assertNotContains(r, 'Valor líquido final')
        self.assertContains(r, 'Informe o percentual do CDI')
        self.assertContains(r, 'Informe o CDI anual')

    def test_pagina_fundos_sem_campo_de_taxa_prefixada(self):
        r = self.client.get(reverse('produto_fundos'))
        self.assertNotContains(r, 'Taxa Prefixada')
        self.assertContains(r, 'Percentual do CDI Estimado')


class FundoCurtoPrazoTests(TestCase):
    def test_curto_prazo_comecotas_20_e_ajuste_225(self):
        # Janeiro, 6 meses: come-cotas em maio (20%) e, no resgate com 180 dias, 22,5% sobre o ganho.
        r, _ = simular_fundo(10000, 0, 6, 12, 'renda_fixa_curto', mes_inicio=1)
        self.assertGreater(r['ir_comecotas'], 0)
        self.assertAlmostEqual(r['ir'], 0.225 * r['juros_brutos'], places=6)

    def test_curto_prazo_apos_180_dias_20(self):
        r, _ = simular_fundo(10000, 0, 12, 12, 'renda_fixa_curto', mes_inicio=1)
        self.assertAlmostEqual(r['ir'], 0.20 * r['juros_brutos'], places=6)

    def test_curto_paga_mais_imposto_que_longo_em_prazo_longo(self):
        curto, _ = simular_fundo(10000, 0, 36, 12, 'renda_fixa_curto', mes_inicio=1)
        longo, _ = simular_fundo(10000, 0, 36, 12, 'renda_fixa', mes_inicio=1)
        self.assertLess(curto['liquido'], longo['liquido'])

    def test_pagina_aceita_curto_prazo(self):
        r = self.client.post(reverse('produto_fundos'), {
            'valor_inicial': '10.000,00', 'periodos': '24', 'percentual_cdi': '100', 'cdi_anual': '10',
            'tipo_fundo': 'renda_fixa_curto'})
        self.assertContains(r, 'curto prazo')
        self.assertContains(r, 'Come-cotas')


class FIITests(TestCase):
    def test_dividendos_sem_reinvestir(self):
        r, evo = simular_fii(10000, 0, 12, 1, 0, reinvestir=False)
        self.assertAlmostEqual(r['dividendos_total'], 1200, places=6)  # 1% de 10.000 por 12 meses
        self.assertAlmostEqual(r['valor_cotas'], 10000, places=6)
        self.assertEqual(r['ir_venda'], 0)  # sem ganho de capital
        self.assertAlmostEqual(r['patrimonio_liquido'], 11200, places=6)
        self.assertEqual(len(evo), 13)

    def test_reinvestindo_rende_mais(self):
        sem, _ = simular_fii(10000, 500, 60, 0.8, 0, reinvestir=False)
        com, _ = simular_fii(10000, 500, 60, 0.8, 0, reinvestir=True)
        self.assertGreater(com['patrimonio_liquido'], sem['patrimonio_liquido'])
        self.assertGreater(com['renda_mensal_final'], sem['renda_mensal_final'])

    def test_ir_20_sobre_ganho_de_capital(self):
        r, _ = simular_fii(10000, 0, 12, 0.5, 10, reinvestir=False)
        self.assertAlmostEqual(r['ganho_capital'], 1000, places=2)  # 10% de valorizacao
        self.assertAlmostEqual(r['ir_venda'], 200, places=2)

    def test_prejuizo_nao_paga_ir(self):
        r, _ = simular_fii(10000, 0, 12, 0.5, -20, reinvestir=False)
        self.assertLess(r['ganho_capital'], 0)
        self.assertEqual(r['ir_venda'], 0)

    def test_reinvestir_entra_no_custo(self):
        r, _ = simular_fii(10000, 0, 12, 1, 0, reinvestir=True)
        self.assertAlmostEqual(r['custo'], 10000 + r['dividendos_reinvestidos'], places=6)
        self.assertAlmostEqual(r['ganho_capital'], 0, places=6)  # preco parado: sem ganho de capital

    def test_pagina_fii(self):
        r = self.client.post(reverse('produto_fii'), {
            'valor_inicial': '10.000,00', 'aporte_mensal': '500,00', 'periodos': '60',
            'dividend_yield': '0,85', 'valorizacao_anual': '-3', 'reinvestir': 'on'})
        self.assertContains(r, 'Renda mensal estimada ao final')
        self.assertContains(r, 'Reinvestidos em novas cotas')

    def test_pagina_fii_exige_dy(self):
        r = self.client.post(reverse('produto_fii'), {'valor_inicial': '1.000,00', 'periodos': '12'})
        self.assertNotContains(r, 'Renda mensal estimada')
        self.assertContains(r, 'Informe o dividend yield')

    def test_valorizacao_muito_negativa_e_recusada(self):
        r = self.client.post(reverse('produto_fii'), {
            'valor_inicial': '1.000,00', 'periodos': '12', 'dividend_yield': '1', 'valorizacao_anual': '-80'})
        self.assertNotContains(r, 'Renda mensal estimada')
        self.assertContains(r, 'erro-campo')


class PrevidenciaTests(TestCase):
    def test_regressiva_acima_de_10_anos_e_10_por_cento_vgbl(self):
        r, _ = simular_previdencia(10000, 0, 132, 8, 'vgbl', 15)
        rendimento = r['bruto'] - r['investido']
        self.assertAlmostEqual(r['ir_regressiva'], 0.10 * rendimento, places=4)
        self.assertAlmostEqual(r['ir_progressiva'], 0.15 * rendimento, places=4)
        self.assertEqual(r['melhor'], 'regressiva')

    def test_pgbl_ir_sobre_o_total(self):
        r, _ = simular_previdencia(10000, 0, 132, 8, 'pgbl', 15, renda_bruta_anual=100000, aliq_marginal_pct=27.5)
        self.assertAlmostEqual(r['ir_regressiva'], 0.10 * r['bruto'], places=4)

    def test_beneficio_fiscal_do_pgbl(self):
        # 12% de 100.000 = 12.000 deduziveis por ano; 500/mes = 6.000/ano (abaixo do limite).
        r, _ = simular_previdencia(0, 500, 24, 8, 'pgbl', 15, renda_bruta_anual=100000, aliq_marginal_pct=27.5)
        self.assertAlmostEqual(r['beneficio_fiscal'], 2 * 6000 * 0.275, places=6)
        # aportando 2.000/mes (24.000/ano), a deducao trava em 12.000/ano
        r2, _ = simular_previdencia(0, 2000, 24, 8, 'pgbl', 15, renda_bruta_anual=100000, aliq_marginal_pct=27.5)
        self.assertAlmostEqual(r2['beneficio_fiscal'], 2 * 12000 * 0.275, places=6)

    def test_vgbl_nao_tem_beneficio(self):
        r, _ = simular_previdencia(10000, 500, 60, 8, 'vgbl', 15)
        self.assertEqual(r['beneficio_fiscal'], 0)

    def test_regressiva_por_aporte(self):
        # Aportes recentes pagam mais: a aliquota efetiva fica acima de 10% mesmo com 11 anos de plano.
        r, _ = simular_previdencia(10000, 500, 132, 8, 'vgbl', 15)
        self.assertGreater(r['ir_regressiva'] / (r['bruto'] - r['investido']), 0.10)

    def test_paginas_previdencia(self):
        base = {'valor_inicial': '10.000,00', 'aporte_mensal': '500,00', 'periodos': '120',
                'rentabilidade_anual': '9', 'aliquota_progressiva': '15'}
        r = self.client.post(reverse('produto_previdencia'), dict(base, tipo_plano='vgbl'))
        self.assertContains(r, 'Tabela regressiva')
        self.assertNotContains(r, 'Restituição de IR somada')
        r = self.client.post(reverse('produto_previdencia'), dict(
            base, tipo_plano='pgbl', renda_bruta_anual='120.000,00', aliquota_marginal='27,5'))
        self.assertContains(r, 'Restituição de IR somada')

    def test_pgbl_exige_renda_e_aliquota(self):
        r = self.client.post(reverse('produto_previdencia'), {
            'tipo_plano': 'pgbl', 'valor_inicial': '1.000,00', 'periodos': '60', 'rentabilidade_anual': '8',
            'aliquota_progressiva': '15'})
        self.assertNotContains(r, 'Saldo acumulado em')
        self.assertContains(r, 'informe a renda bruta anual')


class ETFTests(TestCase):
    def test_taxa_zero_etf_15_por_cento_sobre_o_lucro(self):
        r, evo = comparar_etf_fundo(10000, 0, 12, 10, 0, 0, 'acoes', mes_inicio=1)
        self.assertAlmostEqual(r['etf']['ir'], 150, places=2)
        self.assertAlmostEqual(r['etf']['liquido'], 10850, places=2)
        # Fundo de acoes tambem paga 15%: sem taxa, empatam
        self.assertAlmostEqual(r['etf']['liquido'], r['fundo']['liquido'], places=2)
        self.assertEqual(len(evo), 13)

    def test_taxa_menor_rende_mais_em_acoes(self):
        r, _ = comparar_etf_fundo(10000, 0, 240, 10, 0.2, 2.0, 'acoes', mes_inicio=1)
        self.assertEqual(r['melhor'], 'etf')
        self.assertGreater(r['diferenca'], 0)
        # Mesmo exemplo da pagina: ~R$ 64.6 mil x ~R$ 44.9 mil antes do IR (taxa de 0,2% x 2%)
        self.assertAlmostEqual(r['etf']['valor_antes_ir'], 64634.52, places=1)
        self.assertAlmostEqual(r['fundo']['valor_antes_ir'], 44913.33, places=1)

    def test_etf_renda_fixa_vence_fundo_com_comecotas_mesma_taxa(self):
        r, _ = comparar_etf_fundo(10000, 500, 36, 12, 0.3, 0.3, 'renda_fixa', mes_inicio=1)
        self.assertGreater(r['fundo']['ir_comecotas'], 0)
        self.assertGreater(r['diferenca'], 0)  # sem come-cotas e sem tabela por tempo
        self.assertEqual(r['melhor'], 'etf')

    def test_efeito_da_taxa_positivo(self):
        r, _ = comparar_etf_fundo(10000, 200, 120, 10, 0.5, 1.5, 'acoes', mes_inicio=1)
        self.assertGreater(r['etf']['efeito_taxa'], 0)
        self.assertGreater(r['fundo']['efeito_taxa'], r['etf']['efeito_taxa'])

    def test_pagina_etf(self):
        base = {'valor_inicial': '10.000,00', 'aporte_mensal': '300,00', 'periodos': '120',
                'rentabilidade_bruta': '10', 'taxa_etf': '0,20', 'taxa_fundo': '1,50'}
        for tipo in ('renda_fixa', 'acoes'):
            r = self.client.post(reverse('produto_etf'), dict(base, tipo_comparacao=tipo))
            self.assertContains(r, 'Fundo tradicional')
            self.assertContains(r, 'Efeito da taxa')
        self.assertContains(r, 'IR (15% só no resgate)')

    def test_pagina_etf_exige_campos(self):
        r = self.client.post(reverse('produto_etf'), {'valor_inicial': '1.000,00', 'periodos': '12',
                                                       'tipo_comparacao': 'acoes'})
        self.assertNotContains(r, 'Total aportado em')
        self.assertContains(r, 'Informe a rentabilidade anual bruta')
        self.assertContains(r, 'Informe a taxa do ETF')


class AjudaTests(TestCase):
    def test_previdencia_explica_os_campos(self):
        r = self.client.get(reverse('produto_previdencia'))
        self.assertContains(r, 'Na dúvida, use 15%')
        self.assertContains(r, 'antes dos descontos')
        self.assertContains(r, 'descontadas as taxas')
        self.assertContains(r, 'data-limite-deducao')
        self.assertContains(r, 'Não entendi: o que preencher aqui?')


class MetasETesouroTests(TestCase):
    def test_meta_ja_atingida_nao_inverte_o_sinal(self):
        m = calcular_meta(3_000_000, 1_458_000, 120, 10, 'anual')
        self.assertTrue(m['atingida'])
        self.assertEqual(m['aporte'], 0)
        # Taxa maior so aumenta a folga, nunca "cria" aporte
        m2 = calcular_meta(3_000_000, 1_458_000, 120, 0.85, 'mensal')
        self.assertTrue(m2['atingida'])
        self.assertGreater(m2['inicial_no_fim'], m['inicial_no_fim'])

    def test_meta_com_aporte(self):
        m = calcular_meta(1_000_000, 0, 120, 10, 'anual')
        self.assertFalse(m['atingida'])
        self.assertAlmostEqual(m['aporte'], 5_003.41, places=1)
        # Taxa maior -> aporte menor
        self.assertLess(calcular_meta(1_000_000, 0, 120, 12, 'anual')['aporte'], m['aporte'])
        self.assertAlmostEqual(m['total_aportado'] + m['juros'], 1_000_000, places=2)

    def test_pagina_metas_exemplo_do_usuario(self):
        r = self.client.post(reverse('simulador_metas'), {
            'valor_objetivo': '3.000.000,00', 'valor_inicial': '1.458.000,00', 'taxa_juros': '10',
            'tipo_taxa': 'anual', 'tempo': '120'})
        self.assertContains(r, 'Meta já atingida')
        self.assertContains(r, 'campo-dinheiro')

    def test_indexado_pre_igual_cdb(self):
        a, _ = simular_cdb(10000, 500, 36, 12)
        b, _ = simular_indexado(10000, 500, 36, 'pre', taxa_pre=12)
        self.assertAlmostEqual(a['liquido'], b['liquido'], places=4)

    def test_pos_com_decaimento(self):
        fixo, _ = simular_indexado(10000, 0, 24, 'pos', percentual_cdi=100, cdi_atual=14)
        cai, _ = simular_indexado(10000, 0, 24, 'pos', percentual_cdi=100, cdi_atual=14, cdi_futuro=8, decaimento=12)
        self.assertLess(cai['liquido'], fixo['liquido'])
        self.assertEqual(serie_taxa_decaindo(14, 10, 24, 24)[11], 12)
        self.assertEqual(serie_taxa_decaindo(14, 10, 24, 30)[-1], 10)

    def test_ipca_e_hibrido(self):
        r, _ = simular_indexado(10000, 0, 60, 'ipca', taxa_real=6, ipca=4.5, isento=True)
        self.assertAlmostEqual(r['liquido'], 10000 * (1.06 * 1.045) ** 5, places=2)

    def test_cupons_pagam_mais_imposto_que_sem_cupom(self):
        s, _ = simular_indexado(10000, 0, 60, 'pre', taxa_pre=12)
        c, _ = simular_indexado(10000, 0, 60, 'pre', taxa_pre=12, cupons=True)
        self.assertGreater(c['cupons'], 0)
        self.assertGreater(c['ir'], s['ir'])
        self.assertLess(c['liquido'], s['liquido'])

    def test_custodia_selic_isenta_ate_10_mil(self):
        pequeno, _ = simular_indexado(9000, 0, 12, 'pos', percentual_cdi=100, cdi_atual=10, custodia_pct=0.2, isencao_custodia=10000)
        self.assertEqual(pequeno['custodia'], 0)
        grande, _ = simular_indexado(30000, 0, 12, 'pos', percentual_cdi=100, cdi_atual=10, custodia_pct=0.2, isencao_custodia=10000)
        self.assertGreater(grande['custodia'], 30)

    def test_pagina_simulador_novo(self):
        for dados in (
            {'tipo_indexador': 'pos', 'percentual_cdi': '110', 'cdi_atual': '14,5', 'cdi_futuro': '10', 'decaimento': '24'},
            {'tipo_indexador': 'pre', 'taxa_prefixada': '12,5'},
            {'tipo_indexador': 'ipca', 'taxa_real': '6', 'ipca_estimado': '4,5'},
        ):
            base = {'valor_inicial': '10.000,00', 'aporte_mensal': '500,00', 'periodos': '60'}
            r = self.client.post(reverse('simulador'), dict(base, **dados))
            self.assertContains(r, 'Valor líquido final')
        r = self.client.post(reverse('simulador'), dict(base, tipo_indexador='ipca'))
        self.assertContains(r, 'Informe a taxa fixa do IPCA+')
        self.assertContains(r, 'Informe o IPCA estimado')

    def test_pagina_tesouro(self):
        r = self.client.get(reverse('produto_tesouro'))
        self.assertContains(r, 'Tesouro IPCA+')
        base = {'valor_inicial': '10.000,00', 'aporte_mensal': '', 'periodos': '60'}
        for dados in ({'titulo': 'selic', 'selic_atual': '14'},
                      {'titulo': 'prefixado', 'taxa_prefixada': '13', 'cupons': 'on', 'reinvestir': 'on'},
                      {'titulo': 'ipca', 'taxa_real': '7,5', 'ipca_estimado': '4', 'cupons': 'on'}):
            r = self.client.post(reverse('produto_tesouro'), dict(base, **dados))
            self.assertContains(r, 'Valor líquido final')
            self.assertContains(r, 'custódia da B3')
        self.assertContains(r, 'Cupons de juros recebidos')


class ContatoTests(TestCase):
    def test_contato_abre_whatsapp(self):
        r = self.client.get(reverse('contato'))
        self.assertContains(r, 'https://wa.me/5521981814140?text=')
        self.assertContains(r, '(21) 98181-4140')
        self.assertNotContains(r, '<form')
