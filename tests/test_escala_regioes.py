import unittest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from views.tab_config import formatar_nome_exibicao, aplicar_transferencia_slot
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

    def test_todas_regioes_disponiveis(self):
        """Verifica se todas as regiões cadastradas permanecem disponíveis no dropdown de qualquer slot."""
        todas_regioes = ['AX', 'BH', 'NL', 'PM', 'SL']
        opcoes_esperadas = ['—'] + sorted(todas_regioes)
        self.assertEqual(opcoes_esperadas, ['—', 'AX', 'BH', 'NL', 'PM', 'SL'])

    def test_aplicar_transferencia_slot(self):
        """Verifica se ao atribuir uma região já pertencente a outro técnico, ela é desocupada dele."""
        map_slots = {
            'tec_a': ['BH', 'NL', '—', '—'],
            'tec_b': ['PM', '—', '—', '—']
        }
        mock_session_state = {
            'sel_slot_tec_a_0': 'BH',
            'sel_slot_tec_a_1': 'NL',
            'sel_slot_tec_b_0': 'PM',
        }

        # Técnico B assume a região 'BH' no slot 1
        desocupados = aplicar_transferencia_slot(
            map_slots, 
            matricula_alvo='tec_b', 
            slot_idx_alvo=1, 
            nova_regiao='BH', 
            session_state_ref=mock_session_state
        )

        # Região BH deve ter saído do tec_a slot 0
        self.assertEqual(desocupados, [('tec_a', 0)])
        self.assertEqual(map_slots['tec_a'][0], '—')
        self.assertEqual(mock_session_state['sel_slot_tec_a_0'], '—')

        # Região BH deve estar no tec_b slot 1
        self.assertEqual(map_slots['tec_b'][1], 'BH')
        self.assertEqual(mock_session_state['sel_slot_tec_b_1'], 'BH')

        # Se tec_b transferir 'PM' do slot 0 para o slot 2
        desocupados_mesmo = aplicar_transferencia_slot(
            map_slots,
            matricula_alvo='tec_b',
            slot_idx_alvo=2,
            nova_regiao='PM',
            session_state_ref=mock_session_state
        )
        self.assertEqual(desocupados_mesmo, [('tec_b', 0)])
        self.assertEqual(map_slots['tec_b'][0], '—')
        self.assertEqual(map_slots['tec_b'][2], 'PM')

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
