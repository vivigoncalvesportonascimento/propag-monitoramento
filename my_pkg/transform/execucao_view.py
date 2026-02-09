# my_pkg/transform/execucao_view.py
# -*- coding: utf-8 -*-
"""
Carrega a tabela de execução (fato) e incorpora dimensões (uo, ação e elemento_item),
aplicando o filtro global do painel:
    (fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261

Entrega um DataFrame 'Wide' (denormalizado) para permitir tabelas dinâmicas no Streamlit.
"""

from __future__ import annotations
import pandas as pd
from functools import lru_cache

# Lista completa de colunas solicitadas para o menu dinâmico
EXEC_VIEW_COLS = [
    # Dimensões de Tempo e Estrutura
    "ano",
    "uo_cod",
    "uo_sigla",          # Vem do merge com UO
    "acao_cod",
    "acao_desc",         # Vem do merge com Acao
    "elemento_item_cod",
    "elemento_item_desc",# Vem do merge com Elemento Item
    
    # Classificadores da Execução (estão na fato)
    "grupo_cod",
    "fonte_cod",
    "ipu_cod",
    
    # Detalhes Operacionais (estão na fato)
    "cnpj_cpf_formatado",
    "num_contrato_saida",
    "num_obra",
    "num_empenho",
    
    # Métricas (Valores)
    "vlr_empenhado",
    "vlr_liquidado",
    "vlr_pago_orcamentario",
]

# Caminhos dos arquivos (datapackages instalados via dpm)
PATH_EXEC = "datapackages/siafi-2026/data/execucao.csv.gz"
PATH_UO   = "datapackages/aux-classificadores/data/uo.csv"
PATH_ACAO = "datapackages/aux-classificadores/data/acao.csv"
PATH_ELI  = "datapackages/aux-classificadores/data/elemento_item.csv"


@lru_cache(maxsize=2)
def _load_execucao_raw() -> pd.DataFrame:
    """Lê a execução bruta com otimização de memória."""
    df = pd.read_csv(PATH_EXEC, compression="gzip", low_memory=False)
    return df


@lru_cache(maxsize=4)
def _load_dim_uo() -> pd.DataFrame:
    """Lê dimensão UO (ano, uo_cod -> uo_sigla)."""
    df = pd.read_csv(PATH_UO, low_memory=False)
    return df[["ano", "uo_cod", "uo_sigla"]].drop_duplicates()


@lru_cache(maxsize=4)
def _load_dim_acao() -> pd.DataFrame:
    """Lê dimensão Ação (ano, acao_cod -> acao_desc)."""
    df = pd.read_csv(PATH_ACAO, low_memory=False)
    return df[["ano", "acao_cod", "acao_desc"]].drop_duplicates()


@lru_cache(maxsize=4)
def _load_dim_elemento_item() -> pd.DataFrame:
    """Lê dimensão Elemento Item (ano, elemento_item_cod -> elemento_item_desc)."""
    df = pd.read_csv(PATH_ELI, low_memory=False)
    return df[["ano", "elemento_item_cod", "elemento_item_desc"]].drop_duplicates()


def _apply_global_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica a regra de negócio do Propag:
    (fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261
    """
    # Garante numérico para comparação
    cols_check = ["fonte_cod", "ipu_cod", "uo_cod"]
    for c in cols_check:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    
    # Filtro
    mask = (
        ((df["fonte_cod"] == 89) | (df["ipu_cod"] == 0)) 
        & (df["uo_cod"] != 1261)
    )
    return df.loc[mask].copy()


def load_execucao_view(restrict_uo: int | None = None) -> pd.DataFrame:
    """
    Gera a 'Tabela Fato Estendida' (Wide Table) contendo todas as colunas
    necessárias para a tabela dinâmica do painel.
    """
    # 1. Carrega e filtra a fato
    df = _load_execucao_raw()
    df = _apply_global_filter(df)

    # 2. Restrição de segurança (RLS) para usuários não-admin
    if restrict_uo is not None:
        df = df.loc[df["uo_cod"] == int(restrict_uo)].copy()

    # 3. JOINs com as Dimensões
    dim_uo = _load_dim_uo()
    df = df.merge(dim_uo, on=["ano", "uo_cod"], how="left")
    
    dim_acao = _load_dim_acao()
    df = df.merge(dim_acao, on=["ano", "acao_cod"], how="left")
    
    dim_eli = _load_dim_elemento_item()
    df = df.merge(dim_eli, on=["ano", "elemento_item_cod"], how="left")

    # 4. Tratamento de Tipos (Essencial para não dar erro de soma ou visualização vazia)
    
    # (A) Métricas -> Float (Preenche NaN com 0.0)
    metric_cols = ["vlr_empenhado", "vlr_liquidado", "vlr_pago_orcamentario"]
    for col in metric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    # (B) Dimensões de Texto (String)
    text_dims = [
        "cnpj_cpf_formatado", "num_contrato_saida", "num_obra", 
        "num_empenho", "uo_sigla", "acao_desc", "elemento_item_desc"
    ]
    for col in text_dims:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "")

    # (C) Dimensões Numéricas (Códigos) -> Int64 (permite nulo)
    int_cols = [
        "ano", "uo_cod", "acao_cod", "grupo_cod", 
        "fonte_cod", "ipu_cod", "elemento_item_cod"
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # 5. Seleção Final
    final_cols = [c for c in EXEC_VIEW_COLS if c in df.columns]
    
    return df[final_cols].copy()