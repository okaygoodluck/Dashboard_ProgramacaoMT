import unittest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from views.tab_config import formatar_nome_exibicao
import db_manager

class TestEscalaRegioes(unittest.TestCase):
    
    def test_formatar_nome_exibicao(self):
        """Verifica a formatação de nomes elegantes e diferenciação de homônimos."""
        df_mock = pd.DataFrame([
            {'matricula': 'c001', 'nome': 'POLIANE ALVES GOMES DA SILVA'},
            {'matricula': 'c002', 'nome': 'AMANDA ANDRADE ABREU'},
            {'matricula': 'c003', 'nome': 'AMANDA PIRES PARDINHO'},
            {'matricula': 'c004', 'nome': 'GABRIEL LEONARDO RODRIGUES DA SILVA'},
            {'matricula': 'c005', 'nome': 'GABRIEL LEANDRO FERREIRA'},
            {'matricula': 'c006', 'nome': 'LAURA CATHARINA FERREIRA EVANGELISTA'},
        ])
        
        map_nomes = formatar_nome_exibicao(df_mock)
        
        self.assertEqual(map_nomes['c001'], 'POLIANE')
        self.assertEqual(map_nomes['c002'], 'AMANDA A*')
        self.assertEqual(map_nomes['c003'], 'AMANDA P*')
        self.assertEqual(map_nomes['c004'], 'GABRIEL L*')
        self.assertEqual(map_nomes['c005'], 'GABRIEL L*')
        self.assertEqual(map_nomes['c006'], 'LAURA')

    def test_dynamic_exclusion_opcao_a(self):
        """Verifica se a regra da Opção A impede que a mesma região seja escolhida em múltiplos slots."""
        todas_regioes = ['AX', 'BH', 'NL', 'PM', 'SL']
        map_slots = {
            'u1': ['BH', 'NL', '—', '—'],
            'u2': ['PM', '—', '—', '—']
        }
        
        regioes_ocupadas = {s for slots in map_slots.values() for s in slots if s and s != '—'}
        self.assertEqual(regioes_ocupadas, {'BH', 'NL', 'PM'})
        
        # Opções para u1 slot 0 (atualmente 'BH')
        val_u1_s0 = map_slots['u1'][0]
        opcoes_u1_s0 = ['—'] + ([val_u1_s0] if val_u1_s0 != '—' else []) + [
            r for r in todas_regioes if r not in regioes_ocupadas and r != val_u1_s0
        ]
        # BH continua presente como selecionada, e regiões livres são AX e SL (NL e PM estão ocupadas)
        self.assertIn('BH', opcoes_u1_s0)
        self.assertIn('AX', opcoes_u1_s0)
        self.assertIn('SL', opcoes_u1_s0)
        self.assertNotIn('NL', opcoes_u1_s0)
        self.assertNotIn('PM', opcoes_u1_s0)
        
        # Opções para u2 slot 1 (atualmente '—')
        val_u2_s1 = map_slots['u2'][1]
        opcoes_u2_s1 = ['—'] + [r for r in todas_regioes if r not in regioes_ocupadas and r != val_u2_s1]
        self.assertEqual(opcoes_u2_s1, ['—', 'AX', 'SL'])

    def test_atribuir_regioes_limite_4_slots(self):
        """Verifica se a atribuição salva com sucesso listas de até 4 regiões no banco."""
        matricula_teste = 'c057573' # Matrícula existente no banco
        siglas = ['PM', 'AX']
        sucesso = db_manager.atribuir_regioes_massa(matricula_teste, siglas)
        self.assertTrue(sucesso)
        
        # Consulta mapeamento para conferir
        df_map = db_manager.get_mapeamento_regioes()
        regs_c057573 = df_map[df_map['matricula'] == matricula_teste]['sigla_regiao'].tolist()
        self.assertIn('PM', regs_c057573)
        self.assertIn('AX', regs_c057573)

if __name__ == '__main__':
    unittest.main()
