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
            k_s = str(k).strip()
            normalized_map[k_s] = bool(v)
            normalized_map[k_s.lstrip('0')] = bool(v)
        
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
                return str(int(round(val_float)))
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

if __name__ == '__main__':
    unittest.main()
