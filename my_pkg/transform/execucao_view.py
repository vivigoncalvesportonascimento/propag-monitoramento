# my_pkg/transform/execucao_view.py
# -*- coding: utf-8 -*-
"""
Carrega a tabela de execução (fato) e incorpora dimensões (uo, ação e elemento_item),
aplicando o filtro global do painel.

<<<<<<< HEAD
SOLUÇÃO DE VÍNCULO:
Realiza a padronização de tipos (Int64) nas chaves de junção (ano + cod)
para garantir que as descrições (sigla, desc) sejam trazidas corretamente.
=======
Entrega um DataFrame 'Wide' (denormalizado) para permitir tabelas dinâmicas no Streamlit.
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
"""

from __future__ import annotations
import pandas as pd
from functools import lru_cache

<<<<<<< HEAD
# Lista completa de colunas de saída
EXEC_VIEW_COLS = [
    # Chaves
    "ano",
    "uo_cod",
    "acao_cod",
    "elemento_item_cod",
    
    # Descrições (vindas das tabelas auxiliares)
    "uo_sigla",
    "acao_desc",
    "elemento_item_desc",
    
    # Classificadores da Execução
=======
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
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    "grupo_cod",
    "fonte_cod",
    "ipu_cod",
    
<<<<<<< HEAD
    # Detalhes Operacionais
=======
    # Detalhes Operacionais (estão na fato)
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    "cnpj_cpf_formatado",
    "num_contrato_saida",
    "num_obra",
    "num_empenho",
    
<<<<<<< HEAD
    # Métricas
=======
    # Métricas (Valores)
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    "vlr_empenhado",
    "vlr_liquidado",
    "vlr_pago_orcamentario",
]

<<<<<<< HEAD
# Caminhos dos arquivos (datapackages)
=======
# Caminhos dos arquivos (datapackages instalados via dpm)
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
PATH_EXEC = "datapackages/siafi-2026/data/execucao.csv.gz"
PATH_UO   = "datapackages/aux-classificadores/data/uo.csv"
PATH_ACAO = "datapackages/aux-classificadores/data/acao.csv"
PATH_ELI  = "datapackages/aux-classificadores/data/elemento_item.csv"
<<<<<<< HEAD


def _ensure_join_types(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Converte as colunas especificadas para Int64 (inteiro que aceita nulo).
    Isso é CRUCIAL para o merge funcionar entre tabelas diferentes.
    """
    for col in cols:
        if col in df.columns:
            # Primeiro converte para numeric (trata erros como NaN), depois para Int64
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df
=======
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122


@lru_cache(maxsize=2)
def _load_execucao_raw() -> pd.DataFrame:
<<<<<<< HEAD
    """Lê a execução bruta."""
=======
    """Lê a execução bruta com otimização de memória."""
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    df = pd.read_csv(PATH_EXEC, compression="gzip", low_memory=False)
    return df


@lru_cache(maxsize=4)
def _load_dim_uo() -> pd.DataFrame:
<<<<<<< HEAD
    """Lê dimensão UO e padroniza chaves."""
    df = pd.read_csv(PATH_UO, low_memory=False)
    # Seleciona colunas e remove duplicatas de chave
    df = df[["ano", "uo_cod", "uo_sigla"]].drop_duplicates(subset=["ano", "uo_cod"])
    # Padroniza chaves
    df = _ensure_join_types(df, ["ano", "uo_cod"])
    return df
=======
    """Lê dimensão UO (ano, uo_cod -> uo_sigla)."""
    df = pd.read_csv(PATH_UO, low_memory=False)
    return df[["ano", "uo_cod", "uo_sigla"]].drop_duplicates()
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122


@lru_cache(maxsize=4)
def _load_dim_acao() -> pd.DataFrame:
<<<<<<< HEAD
    """Lê dimensão Ação e padroniza chaves."""
    df = pd.read_csv(PATH_ACAO, low_memory=False)
    df = df[["ano", "acao_cod", "acao_desc"]].drop_duplicates(subset=["ano", "acao_cod"])
    df = _ensure_join_types(df, ["ano", "acao_cod"])
    return df
=======
    """Lê dimensão Ação (ano, acao_cod -> acao_desc)."""
    df = pd.read_csv(PATH_ACAO, low_memory=False)
    return df[["ano", "acao_cod", "acao_desc"]].drop_duplicates()
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122


@lru_cache(maxsize=4)
def _load_dim_elemento_item() -> pd.DataFrame:
<<<<<<< HEAD
    """Lê dimensão Elemento Item e padroniza chaves."""
    df = pd.read_csv(PATH_ELI, low_memory=False)
    df = df[["ano", "elemento_item_cod", "elemento_item_desc"]].drop_duplicates(subset=["ano", "elemento_item_cod"])
    df = _ensure_join_types(df, ["ano", "elemento_item_cod"])
    return df


def _apply_global_filter(df: pd.DataFrame) -> pd.DataFrame:
    """(fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261"""
    # Garante numérico para filtrar
    for c in ["fonte_cod", "ipu_cod", "uo_cod"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    
=======
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
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    mask = (
        ((df["fonte_cod"] == 89) | (df["ipu_cod"] == 0)) 
        & (df["uo_cod"] != 1261)
    )
    return df.loc[mask].copy()


def load_execucao_view(restrict_uo: int | None = None) -> pd.DataFrame:
    """
<<<<<<< HEAD
    Gera a tabela completa (Fato + Dimensões) com joins seguros.
    """
    # 1. Carrega Fato
    df = _load_execucao_raw()
    df = _apply_global_filter(df)

    # 2. Padroniza chaves na Fato ANTES do join
    # Isso garante que 1021.0 vire 1021 (Int64)
    join_keys = ["ano", "uo_cod", "acao_cod", "elemento_item_cod"]
    df = _ensure_join_types(df, join_keys)

    # 3. Restrição de segurança (RLS)
    if restrict_uo is not None:
        df = df.loc[df["uo_cod"] == int(restrict_uo)].copy()

    # 4. Carrega Dimensões (já padronizadas dentro das funções _load)
    dim_uo = _load_dim_uo()
    dim_acao = _load_dim_acao()
    dim_eli = _load_dim_elemento_item()

    # 5. Executa os Joins (Left Join)
    # Apenas registros que tem match de (ano + codigo) trarão a descrição
    df = df.merge(dim_uo, on=["ano", "uo_cod"], how="left")
    df = df.merge(dim_acao, on=["ano", "acao_cod"], how="left")
    df = df.merge(dim_eli, on=["ano", "elemento_item_cod"], how="left")

    # 6. Preenchimento de Falhas (Opcional mas recomendado)
    # Se não achar a descrição, preenche para não ficar vazio na tabela
    if "uo_sigla" in df.columns:
        df["uo_sigla"] = df["uo_sigla"].fillna("UO-" + df["uo_cod"].astype(str))
    if "acao_desc" in df.columns:
        df["acao_desc"] = df["acao_desc"].fillna("Ação " + df["acao_cod"].astype(str))

    # 7. Tratamento Final de Tipos
    
    # Métricas -> Float
    metric_cols = ["vlr_empenhado", "vlr_liquidado", "vlr_pago_orcamentario"]
    for col in metric_cols:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Dimensões de Texto -> String
    text_dims = [
        "cnpj_cpf_formatado", "num_contrato_saida", "num_obra", "num_empenho", 
        "uo_sigla", "acao_desc", "elemento_item_desc"
    ]
    for col in text_dims:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "").replace("<NA>", "")

    # Outros Códigos -> Int64
    other_ints = ["grupo_cod", "fonte_cod", "ipu_cod"]
    df = _ensure_join_types(df, other_ints)

    # Seleção Final
=======
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
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    final_cols = [c for c in EXEC_VIEW_COLS if c in df.columns]
    
    return df[final_cols].copy()