# my_pkg/transform/schema.py
from typing import List

ALL_COLS: List[str] = [
    "uo_cod","uo_sigla","acao_cod","acao_desc","intervencao_cod","intervencao_desc",
    "marcos_principais","novo_marco","valor_previsto_total","valor_replanejado_total",
    "1_bimestre_planejado","1_bimestre_replanejado","1_bimestre_realizado",
    "2_bimestre_planejado","2_bimestre_replanejado","2_bimestre_realizado",
    "3_bimestre_planejado","3_bimestre_replanejado","3_bimestre_realizado",
    "4_bimestre_planejado","4_bimestre_replanejado","4_bimestre_realizado",
    "5_bimestre_planejado","5_bimestre_replanejado","5_bimestre_realizado",
    "6_bimestre_planejado","6_bimestre_replanejado","6_bimestre_realizado",
]

NUMERIC_COLS: List[str] = [
    "valor_replanejado_total",
    "1_bimestre_replanejado","1_bimestre_realizado",
    "2_bimestre_replanejado","2_bimestre_realizado",
    "3_bimestre_replanejado","3_bimestre_realizado",
    "4_bimestre_replanejado","4_bimestre_realizado",
    "5_bimestre_replanejado","5_bimestre_realizado",
    "6_bimestre_replanejado","6_bimestre_realizado",
]

BOOL_COLS: List[str] = [
    "1_bimestre_planejado","2_bimestre_planejado","3_bimestre_planejado",
    "4_bimestre_planejado","5_bimestre_planejado","6_bimestre_planejado",
]

# Editáveis pelo usuário no app:
EDITABLE_COLS: List[str] = list(NUMERIC_COLS)

# Campos obrigatórios quando inserir uma linha nova:
REQUIRED_ON_NEW: List[str] = [
    "uo_cod","uo_sigla","acao_cod","acao_desc","intervencao_cod",
    "intervencao_desc","marcos_principais","valor_previsto_total"
]