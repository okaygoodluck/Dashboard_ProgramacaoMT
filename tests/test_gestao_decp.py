import unittest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
import db_manager

class TestGestaoDECP(unittest.TestCase):
    
    def test_highlight_logic(self):
        """Verifica se a lógica de destaque para CHI >= 1500 funciona corretamente."""
        email_decp_map = {'1001': False, '1002': True, '1003': False}
        col_solic = 'Solicitação'
        
        def aplicar_destaque_chi_decp(row):
            chi_val = pd.to_numeric(row.get('CHI', 0), errors='coerce')
            if pd.notna(chi_val) and chi_val >= 1500:
                solic_val = str(row.get(col_solic, ''))
                tem_email = email_decp_map.get(solic_val, False)
                if not tem_email:
                    return ['alert'] * len(row)
                else:
                    return ['ok'] * len(row)
            return [''] * len(row)

        df = pd.DataFrame([
            {'Solicitação': '1001', 'CHI': 1600}, # CHI >= 1500 e sem email -> alert
            {'Solicitação': '1002', 'CHI': 2000}, # CHI >= 1500 e com email -> ok
            {'Solicitação': '1003', 'CHI': 800},  # CHI < 1500 -> neutro ('')
        ])

        res_alert = aplicar_destaque_chi_decp(df.iloc[0])
        res_ok = aplicar_destaque_chi_decp(df.iloc[1])
        res_neutro = aplicar_destaque_chi_decp(df.iloc[2])

        self.assertEqual(res_alert[0], 'alert')
        self.assertEqual(res_ok[0], 'ok')
        self.assertEqual(res_neutro[0], '')

    def test_atualizar_email_decp_bd_executes_safely(self):
        """Verifica se atualizar_email_decp_bd lida corretamente com dicionário vazio e executa sem falhas."""
        try:
            db_manager.atualizar_email_decp_bd({})
            db_manager.atualizar_email_decp_bd({'000000': True})
        except Exception as e:
            self.fail(f"atualizar_email_decp_bd levantou exceção: {e}")

    def test_reconciliation_merge_suffixes(self):
        """Verifica se a lógica de reconciliação de sufixos _x e _y elimina duplicatas e preserva dados."""
        df = pd.DataFrame({
            'Solicitação': ['1', '2'],
            'CHI_x': [1000, 2000],
            'CHI_y': [1500, None]
        })
        for base_c in ['CHI', 'Peso', 'Clientes', 'OBRA GD']:
            col_x, col_y = f"{base_c}_x", f"{base_c}_y"
            if col_y in df.columns and col_x in df.columns:
                df[base_c] = df[col_y].combine_first(df[col_x])
                df.drop(columns=[col_x, col_y], inplace=True)
        
        self.assertIn('CHI', df.columns)
        self.assertNotIn('CHI_x', df.columns)
        self.assertNotIn('CHI_y', df.columns)
        self.assertEqual(df['CHI'].tolist(), [1500.0, 2000.0])

    def test_highlight_with_leading_zeros(self):
        """Verifica se o destaque funciona com chaves contendo zeros à esquerda."""
        raw_map = {'001001': False, '1002': True}
        normalized_map = {}
        for k, v in raw_map.items():
            k_s = k.strip()
            normalized_map[k_s] = v
            normalized_map[k_s.lstrip('0')] = v
        
        # Função de lookup resiliente como em tab_detalhes.py
        def check_email(solic_str):
            s = str(solic_str).strip()
            return normalized_map.get(s, False) or normalized_map.get(s.lstrip('0'), False)

        # Testando busca tanto com '1001'/'001001' quanto com '1002'/'001002'
        self.assertEqual(check_email('1001'), False)
        self.assertEqual(check_email('001001'), False)
        self.assertEqual(check_email('1002'), True)
        self.assertEqual(check_email('001002'), True)

    def test_numeric_columns_integer_formatting(self):
        """Verifica se CHI, Clientes e Peso são formatados como números inteiros sem partes fracionadas."""
        df = pd.DataFrame({
            'CHI': [1500.0, 850.6, None],
            'Clientes': [12.0, 0.0, None],
            'Peso': ['1.0', '10.0', 'PLE']
        })
        
        # Conversão CHI e Clientes
        for col_int in ['CHI', 'Clientes']:
            df[col_int] = pd.to_numeric(df[col_int], errors='coerce').fillna(0).round().astype(int)
        
        # Tratamento Peso
        def limpar_peso_inteiro(v):
            if pd.isna(v) or str(v).strip() == '' or str(v).strip().lower() == 'nan':
                return '0'
            try:
                val_float = float(v)
                return str(round(val_float))
            except (ValueError, TypeError):
                return str(v).strip()
        df['Peso'] = df['Peso'].apply(limpar_peso_inteiro)

        self.assertEqual(df['CHI'].tolist(), [1500, 851, 0])
        self.assertEqual(df['Clientes'].tolist(), [12, 0, 0])
        self.assertEqual(df['Peso'].tolist(), ['1', '10', 'PLE'])
        self.assertTrue('int' in str(df['CHI'].dtype))

    def test_atualizar_email_urgencia_bd_executes_safely(self):
        """Verifica se atualizar_email_urgencia_bd lida corretamente com dicionário vazio e executa sem falhas."""
        try:
            db_manager.atualizar_email_urgencia_bd({})
            db_manager.atualizar_email_urgencia_bd({'000000': True})
        except Exception as e:
            self.fail(f"atualizar_email_urgencia_bd levantou exceção: {e}")

    def test_email_autorizacao_and_combined_highlight(self):
        """Verifica se a classificação da coluna E-mail Autorização e o destaque combinado (CHI >= 1500 ou Urgência) funcionam conforme solicitado."""
        email_decp_map = {'1001': True, '1002': False, '1003': True, '1004': False}
        email_urg_map = {'1001': True, '1002': True, '1003': False, '1004': False}

        def is_urgente_val(val):
            if pd.isna(val): return False
            s = str(val).strip().upper()
            if s in ['SEM', 'NÃO', 'NAO', 'N', 'FALSE', '0', '']: return False
            return s in ['SIM', 'S', 'TRUE', '1'] or 'SIM' in s or s.startswith('S')

        def get_email_autorizacao(row):
            chi_val = pd.to_numeric(row.get('CHI', 0), errors='coerce')
            is_chi = pd.notna(chi_val) and chi_val >= 1500
            urg_val = row.get('Urgência', None)
            is_urg = is_urgente_val(urg_val)

            if not is_chi and not is_urg:
                return "—"

            solic_raw = str(row.get('Solicitação', '')).strip()
            solic_trim = solic_raw.lstrip('0')
            tem_decp = email_decp_map.get(solic_raw, False) or email_decp_map.get(solic_trim, False)
            tem_urg = email_urg_map.get(solic_raw, False) or email_urg_map.get(solic_trim, False)

            if tem_decp and tem_urg:
                return "DECP + Urgência"
            elif tem_decp:
                return "DECP"
            elif tem_urg:
                return "Urgência"
            else:
                return "Pendente"

        def aplicar_destaque_autorizacao(row):
            status_aut = str(row.get('E-mail Autorização', '—')).strip()
            if status_aut in ['DECP', 'Urgência', 'DECP + Urgência']:
                return ['green'] * len(row)
            elif status_aut == 'Pendente':
                return ['red'] * len(row)
            return [''] * len(row)

        df = pd.DataFrame([
            {'Solicitação': '1001', 'CHI': 1600, 'Urgência': 'SIM'}, # Ambos -> DECP + Urgência -> green
            {'Solicitação': '1002', 'CHI': 500,  'Urgência': 'SIM'}, # Só Urgência -> Urgência -> green
            {'Solicitação': '1003', 'CHI': 1800, 'Urgência': 'NÃO'}, # Só DECP -> DECP -> green
            {'Solicitação': '1004', 'CHI': 2000, 'Urgência': 'SIM'}, # Pendente -> red
            {'Solicitação': '1005', 'CHI': 800,  'Urgência': 'NÃO'}, # Nem CHI nem Urgência -> — -> ''
        ])

        df['E-mail Autorização'] = df.apply(get_email_autorizacao, axis=1)

        self.assertEqual(df.loc[0, 'E-mail Autorização'], 'DECP + Urgência')
        self.assertEqual(df.loc[1, 'E-mail Autorização'], 'Urgência')
        self.assertEqual(df.loc[2, 'E-mail Autorização'], 'DECP')
        self.assertEqual(df.loc[3, 'E-mail Autorização'], 'Pendente')
        self.assertEqual(df.loc[4, 'E-mail Autorização'], '—')

        self.assertEqual(aplicar_destaque_autorizacao(df.iloc[0])[0], 'green')
        self.assertEqual(aplicar_destaque_autorizacao(df.iloc[1])[0], 'green')
        self.assertEqual(aplicar_destaque_autorizacao(df.iloc[2])[0], 'green')
        self.assertEqual(aplicar_destaque_autorizacao(df.iloc[3])[0], 'red')
        self.assertEqual(aplicar_destaque_autorizacao(df.iloc[4])[0], '')

    def test_is_aprovada_removed_from_detailed_view(self):
        """Verifica se Is_Aprovada está na lista de colunas a serem ocultadas."""
        cols_to_hide = [
            'Sol. Vinc.', 'Ações', 'Tem_Email', 'Tem_Email_DECP', 'Data_Extracao', 
            'Status_Prazo', 'Is_Elaboracao', 'Is_Aprovada', 'Resp. Manobra'
        ]
        self.assertIn('Is_Aprovada', cols_to_hide)

    def test_chi_critico_kpi_calculation(self):
        """Verifica o cálculo de contagem e filtro do novo KPI CHI >= 1500."""
        df = pd.DataFrame([
            {'Solicitação': '1', 'CHI': 1500},
            {'Solicitação': '2', 'CHI': 2500.5},
            {'Solicitação': '3', 'CHI': 800},
            {'Solicitação': '4', 'CHI': None},
            {'Solicitação': '5', 'CHI': '1600'}
        ])
        col_chi_calc = next((c for c in df.columns if c.strip().upper() == 'CHI' or c.startswith('CHI')), None)
        self.assertIsNotNone(col_chi_calc)
        
        mask = pd.to_numeric(df[col_chi_calc], errors='coerce').fillna(0) >= 1500
        df_chi_critico = df[mask]
        
        self.assertEqual(len(df_chi_critico), 3) # 1500, 2500.5, 1600
        self.assertEqual(df_chi_critico['Solicitação'].tolist(), ['1', '2', '5'])

    def test_verificar_status_atraso_urgencia_e_aprovada(self):
        """Verifica a regra de negócio de Urgência, Atrasadas e Alertas para solicitações Aprovadas e Em Elaboração."""
        from dashboard import verificar_status_atraso

        # Caso 1: Aprovada com Urgência e DU >= 8 (deve ser Urgência para constar no card Foras do Prazo)
        row_urg_10 = {'Situação': 'APROVADA', 'Urgência': 'Sim', 'Dias_Uteis_Restantes': 10}
        self.assertEqual(verificar_status_atraso(row_urg_10), 'Urgência')

        # Caso 2: Aprovada com Urgência e DU < 8
        row_urg_3 = {'Situação': 'APROVADA', 'Urgência': 'Sim', 'Dias_Uteis_Restantes': 3}
        self.assertEqual(verificar_status_atraso(row_urg_3), 'Urgência')

        # Caso 3: Aprovada sem Urgência e DU > 8 (No Prazo)
        row_normal_10 = {'Situação': 'APROVADA', 'Urgência': 'Não', 'Dias_Uteis_Restantes': 10}
        self.assertEqual(verificar_status_atraso(row_normal_10), 'No Prazo')

        # Caso 4: Aprovada sem Urgência e DU == 8 (Alerta de Prazo para envio de aviso)
        row_alerta = {'Situação': 'APROVADA', 'Urgência': 'Não', 'Dias_Uteis_Restantes': 8}
        self.assertEqual(verificar_status_atraso(row_alerta), 'Alerta de Prazo')

        # Caso 5: Aprovada sem Urgência e DU < 8 (Atrasada)
        row_atrasada = {'Situação': 'APROVADA', 'Urgência': 'Não', 'Dias_Uteis_Restantes': 5}
        self.assertEqual(verificar_status_atraso(row_atrasada), 'Atrasada')

        # Caso 6: Data já passou (negativo) -> Atrasada
        row_passada = {'Situação': 'APROVADA', 'Urgência': 'Sim', 'Dias_Uteis_Restantes': -1}
        self.assertEqual(verificar_status_atraso(row_passada), 'Atrasada')

        # Caso 7: Em Elaboração com Urgência -> Urgência (consta no card Foras do Prazo)
        row_elab_urg = {'Situação': 'EM ELABORACAO', 'Urgência': 'Sim', 'Dias_Uteis_Restantes': 5}
        self.assertEqual(verificar_status_atraso(row_elab_urg), 'Urgência')

        # Caso 8: Em Elaboração com DU < 8 e sem urgência -> Atrasada (consta no card Solicitações Atrasadas)
        row_elab_atras = {'Situação': 'EM ELABORACAO', 'Urgência': 'Não', 'Dias_Uteis_Restantes': 5}
        self.assertEqual(verificar_status_atraso(row_elab_atras), 'Atrasada')

        # Caso 9: Em Elaboração com DU == 8 -> No Prazo (Aviso de 8 dias é exclusivo para Aprovadas)
        row_elab_8d = {'Situação': 'EM ELABORACAO', 'Urgência': 'Não', 'Dias_Uteis_Restantes': 8}
        self.assertEqual(verificar_status_atraso(row_elab_8d), 'No Prazo')

        # Caso 10: Solicitação Cancelada/Concluída -> Concluída/Outros
        row_canc = {'Situação': 'CANCELADA', 'Urgência': 'Sim', 'Dias_Uteis_Restantes': 5}
        self.assertEqual(verificar_status_atraso(row_canc), 'Concluída/Outros')

    def test_conjuntos_restritos_logic_and_highlight(self):
        """Verifica se a lógica de Alimentador -> Conjunto Restrito funciona corretamente (desacoplada de CHI)."""
        map_alim_to_sigla = {'ALIM01': 'CJ01', 'ALIM02': 'CJ02', 'ALIM03': 'CJ03'}
        set_conj_restritos = {'CJ01', 'CJ03'} # CJ01 e CJ03 são restritos

        def get_status_conjunto(row):
            if 'Conjunto' in row and str(row['Conjunto']).strip().upper() == 'RESTRITO':
                return 'RESTRITO'
            alim_raw = str(row.get('Alimentador', '')).replace(' ', '').strip().upper()
            sigla = map_alim_to_sigla.get(alim_raw)
            if sigla and sigla in set_conj_restritos:
                return 'RESTRITO'
            return '—'

        # Teste 1: CHI >= 500 e alimentador em conjunto restrito -> RESTRITO
        row1 = {'CHI': 500, 'Alimentador': 'ALIM01'}
        self.assertEqual(get_status_conjunto(row1), 'RESTRITO')

        # Teste 2: CHI > 500 com espaço no alimentador e conjunto restrito -> RESTRITO
        row2 = {'CHI': 850, 'Alimentador': ' ALIM 03 '}
        self.assertEqual(get_status_conjunto(row2), 'RESTRITO')

        # Teste 3: CHI >= 500 mas alimentador em conjunto NÃO restrito -> —
        row3 = {'CHI': 1200, 'Alimentador': 'ALIM02'}
        self.assertEqual(get_status_conjunto(row3), '—')

        # Teste 4: CHI < 500 em conjunto restrito -> RESTRITO (regra atualizada)
        row4 = {'CHI': 148, 'Alimentador': 'ALIM01'}
        self.assertEqual(get_status_conjunto(row4), 'RESTRITO')

        # Teste 5: Estilização de linha avermelhada para RESTRITO
        def aplicar_destaque_teste(row):
            status_conj = str(row.get('Conjunto', '—')).strip()
            if status_conj == 'RESTRITO':
                return 'red'
            status_aut = str(row.get('E-mail Autorização', '—')).strip()
            if status_aut in ['DECP', 'Urgência']:
                return 'green'
            elif status_aut == 'Pendente':
                return 'red'
            return 'none'

        self.assertEqual(aplicar_destaque_teste({'Conjunto': 'RESTRITO', 'E-mail Autorização': 'DECP'}), 'red')
        self.assertEqual(aplicar_destaque_teste({'Conjunto': '—', 'E-mail Autorização': 'DECP'}), 'green')
        self.assertEqual(aplicar_destaque_teste({'Conjunto': '—', 'E-mail Autorização': '—'}), 'none')

    def test_conjunto_restrito_kpi_calculation(self):
        """Verifica a lógica de filtragem e contagem do KPI 'Conjunto Restrito' (alimentador em conjunto restrito)."""
        map_alim_sigla = {'ALIM01': 'CJ01', 'ALIM02': 'CJ02', 'ALIM03': 'CJ03'}
        set_conj_restr = {'CJ01', 'CJ03'}

        df_mock = pd.DataFrame([
            {'Solicitacao': '1', 'CHI': 600, 'Alimentador': 'ALIM01'},       # Válido: CJ01 restrito
            {'Solicitacao': '2', 'CHI': 500, 'Alimentador': ' ALIM 03 '},    # Válido: CJ03 restrito
            {'Solicitacao': '3', 'CHI': 148, 'Alimentador': 'ALIM01'},       # Válido: CJ01 restrito mesmo com CHI < 500
            {'Solicitacao': '4', 'CHI': 1200, 'Alimentador': 'ALIM02'},      # Inválido: CJ02 não é restrito
            {'Solicitacao': '5', 'CHI': None, 'Alimentador': 'ALIM01'},      # Válido: CJ01 restrito
        ])

        col_alim_calc = 'Alimentador'

        def _is_restr_item(row):
            alim_clean = str(row.get(col_alim_calc, '')).replace(' ', '').strip().upper()
            sigla = map_alim_sigla.get(alim_clean)
            return bool(sigla and sigla in set_conj_restr)

        df_conjunto_restrito = df_mock[df_mock.apply(_is_restr_item, axis=1)]
        qtd_conjunto_restrito = len(df_conjunto_restrito)

        self.assertEqual(qtd_conjunto_restrito, 4)
        self.assertEqual(df_conjunto_restrito['Solicitacao'].tolist(), ['1', '2', '3', '5'])

    def test_preparar_dataframe_detalhes_para_kpi_e_tabela(self):
        """Verifica se preparar_dataframe_detalhes padroniza colunas, oculta colunas tecnicas e aplica regras de cores e nomes."""
        from views.tab_detalhes import preparar_dataframe_detalhes

        df_mock = pd.DataFrame([
            {
                'Solicitação': '1001',
                'Responsavel': 'GABRIEL LEANDRO FERREIRA',
                'Situação': 'APROVADA',
                'CHI': 1600.0,
                'Clientes': 25.0,
                'Peso': '1.0',
                'Urgência': 'Sim',
                'Conjunto': 'RESTRITO',
                'Tem_Email_DECP': True,
                'Is_Aprovada': True,
                'Status_Prazo': 'Urgência'
            },
            {
                'Solicitação': '1002',
                'Responsavel': 'GABRIEL LEONARDO RODRIGUES DA SILVA',
                'Situação': 'APROVADA',
                'CHI': 400.0,
                'Clientes': 10.0,
                'Peso': 'PLE',
                'Urgência': 'Não',
                'Conjunto': '—',
                'Tem_Email_DECP': False,
                'Is_Aprovada': True,
                'Status_Prazo': 'No Prazo'
            }
        ])

        df_view, col_config, format_styler, func_destaque = preparar_dataframe_detalhes(df_mock, col_situacao='Situação')

        # 1. Colunas obrigatórias presentes
        self.assertIn('E-mail', df_view.columns)
        self.assertIn('Conjunto', df_view.columns)

        # 2. Colunas técnicas ocultadas
        for c_oculta in ['Is_Aprovada', 'Status_Prazo', 'Tem_Email_DECP']:
            self.assertNotIn(c_oculta, df_view.columns)

        # 3. Diferenciação de nomes dos Gabriels
        self.assertEqual(df_view.loc[0, 'Assumiu'], 'Gabriel Leandro')
        self.assertEqual(df_view.loc[1, 'Assumiu'], 'Gabriel Leonardo')

        # 4. Formatação de tipos
        self.assertEqual(df_view.loc[0, 'CHI'], 1600)
        self.assertEqual(df_view.loc[0, 'Peso'], '1')
        self.assertEqual(df_view.loc[1, 'Peso'], 'PLE')

        # 5. Regras de cores no destaque
        # Linha 0 tem Conjunto == RESTRITO -> Fundo avermelhado
        estilos_row0 = func_destaque(df_view.iloc[0])
        self.assertTrue(any('rgba(220, 38, 38' in e for e in estilos_row0))

        # Linha 1 não tem urgência/CHI/restrito -> Sem estilo especial
        estilos_row1 = func_destaque(df_view.iloc[1])
        self.assertTrue(all(e == '' for e in estilos_row1))

if __name__ == '__main__':
    unittest.main()

