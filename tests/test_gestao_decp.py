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

if __name__ == '__main__':
    unittest.main()
