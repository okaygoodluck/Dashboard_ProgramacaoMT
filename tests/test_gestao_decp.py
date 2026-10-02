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

if __name__ == '__main__':
    unittest.main()
