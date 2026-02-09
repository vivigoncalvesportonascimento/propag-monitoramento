# my_pkg/transform/rp_view.py
# -*- coding: utf-8 -*-
"""
Carrega a tabela de Restos a Pagar (fato), calcula as métricas derivadas
e incorpora dimensões (uo, ação e elemento_item).

Aplica o filtro global do painel:
(fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261
"""

from __future__ import annotations
import pandas as pd
from functools import lru_cache

# Colunas finais que estarão disponíveis para o painel
RP_VIEW_COLS = [
    # Chaves e Dimensões Temporais
    "ano",
    "ano_rp",
    "uo_cod",
    "acao_cod",
    "elemento_item_cod",
    
    # Descrições (Join)
    "uo_sigla",
    "acao_desc",
    "elemento_item_desc",
    
    # Classificadores
    "grupo_cod",
    "fonte_cod",
    "ipu_cod",
    
    # Detalhes Operacionais
    "num_empenho",
    "cnpj_cpf_formatado",
    "razao_social_credor",
    "num_contrato_saida",
    "num_obra",
    
    # Métricas Calculadas (Processados)
    "calc_inscrito_rpp",
    "calc_cancelado_rpp",
    "calc_pago_rpp",
    "calc_saldo_rpp",
    
    # Métricas Calculadas (Não Processados)
    "calc_inscrito_rpnp",
    "calc_cancelado_rpnp",
    "calc_liquidado_rpnp",
    "calc_saldo_rpnp",
    "calc_pago_rpnp"
]

# Caminhos
PATH_RP   = "datapackages/siafi-2026/data/restos_pagar.csv.gz"
PATH_UO   = "datapackages/aux-classificadores/data/uo.csv"
PATH_ACAO = "datapackages/aux-classificadores/data/acao.csv"
PATH_ELI  = "datapackages/aux-classificadores/data/elemento_item.csv"


def _ensure_join_types(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Garante tipo Int64 para chaves de join."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


@lru_cache(maxsize=2)
def _load_rp_raw() -> pd.DataFrame:
    """Lê a base bruta de Restos a Pagar."""
    df = pd.read_csv(PATH_RP, compression="gzip", low_memory=False)
    return df


@lru_cache(maxsize=4)
def _load_dim_uo() -> pd.DataFrame:
    """Dimensão UO."""
    df = pd.read_csv(PATH_UO, low_memory=False)
    df = df[["ano", "uo_cod", "uo_sigla"]].drop_duplicates(subset=["ano", "uo_cod"])
    df = _ensure_join_types(df, ["ano", "uo_cod"])
    return df


@lru_cache(maxsize=4)
def _load_dim_acao() -> pd.DataFrame:
    """Dimensão Ação."""
    df = pd.read_csv(PATH_ACAO, low_memory=False)
    df = df[["ano", "acao_cod", "acao_desc"]].drop_duplicates(subset=["ano", "acao_cod"])
    df = _ensure_join_types(df, ["ano", "acao_cod"])
    return df


@lru_cache(maxsize=4)
def _load_dim_elemento_item() -> pd.DataFrame:
    """Dimensão Elemento Item."""
    df = pd.read_csv(PATH_ELI, low_memory=False)
    df = df[["ano", "elemento_item_cod", "elemento_item_desc"]].drop_duplicates(subset=["ano", "elemento_item_cod"])
    df = _ensure_join_types(df, ["ano", "elemento_item_cod"])
    return df


def _apply_global_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Filtro: (fonte=89 OR ipu=0) AND uo!=1261"""
    for c in ["fonte_cod", "ipu_cod", "uo_cod"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    
    mask = (
        ((df["fonte_cod"] == 89) | (df["ipu_cod"] == 0)) 
        & (df["uo_cod"] != 1261)
    )
    return df.loc[mask].copy()


def _calculate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Realiza o cálculo das colunas de métricas solicitadas.
    Preenche NaN com 0.0 antes de calcular para evitar propagação de nulos.
    """
    # Lista de colunas base necessárias para os cálculos
    cols_base = [
        "vlr_inscrito_rpp", "vlr_cancelado_rpp", "vlr_desconto_rpp", "vlr_restabelecido_rpp",
        "vlr_pago_rpp", "vlr_anulacao_pagamento_rpp", "vlr_retencao_rpp", "vlr_anulacao_retencao_rpp",
        "vlr_saldo_rpp", 
        "vlr_inscrito_rpnp", "vlr_cancelado_rpnp", "vlr_restabelecido_rpnp",
        "vlr_despesa_liquidada_rpnp", "vlr_saldo_rpnp", "vlr_despesa_liquidada_pagar"
    ]
    
    # Garante que todas existam e sejam float
    for c in cols_base:
        if c not in df.columns:
            df[c] = 0.0
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # --- PROCESSADOS (RPP) ---
    # Inscrito Processado
    df["calc_inscrito_rpp"] = df["vlr_inscrito_rpp"]
    
    # Cancelado Processado
    df["calc_cancelado_rpp"] = (
        df["vlr_cancelado_rpp"] + df["vlr_desconto_rpp"] - df["vlr_restabelecido_rpp"]
    )
    
    # Pago Processado
    df["calc_pago_rpp"] = (
        df["vlr_pago_rpp"] - df["vlr_anulacao_pagamento_rpp"] 
        + df["vlr_retencao_rpp"] - df["vlr_anulacao_retencao_rpp"]
    )
    
    # Saldo Processado
    df["calc_saldo_rpp"] = df["vlr_saldo_rpp"]

    # --- NÃO PROCESSADOS (RPNP) ---
    # Inscrito Não Processado
    df["calc_inscrito_rpnp"] = df["vlr_inscrito_rpnp"]
    
    # Cancelado Não Processado
    df["calc_cancelado_rpnp"] = (
        df["vlr_cancelado_rpnp"] - df["vlr_restabelecido_rpnp"]
    )
    
    # Liquidado Não Processado
    df["calc_liquidado_rpnp"] = df["vlr_despesa_liquidada_rpnp"]
    
    # Saldo Não Processado
    df["calc_saldo_rpnp"] = df["vlr_saldo_rpnp"]
    
    # Pago Não Processado (Fórmula solicitada)
    df["calc_pago_rpnp"] = (
        df["vlr_saldo_rpp"] + df["vlr_despesa_liquidada_rpnp"] - df["vlr_despesa_liquidada_pagar"]
    )

    return df


def load_rp_view(restrict_uo: int | None = None) -> pd.DataFrame:
    """Gera a tabela completa de RP com métricas calculadas e joins."""
    # 1. Carrega e Filtra
    df = _load_rp_raw()
    df = _apply_global_filter(df)
    
    # 2. Calcula Métricas
    df = _calculate_metrics(df)

    # 3. Padroniza Chaves
    join_keys = ["ano", "uo_cod", "acao_cod", "elemento_item_cod"]
    df = _ensure_join_types(df, join_keys)

    # 4. RLS (Segurança)
    if restrict_uo is not None:
        df = df.loc[df["uo_cod"] == int(restrict_uo)].copy()

    # 5. Joins com Dimensões
    dim_uo = _load_dim_uo()
    dim_acao = _load_dim_acao()
    dim_eli = _load_dim_elemento_item()

    df = df.merge(dim_uo, on=["ano", "uo_cod"], how="left")
    df = df.merge(dim_acao, on=["ano", "acao_cod"], how="left")
    df = df.merge(dim_eli, on=["ano", "elemento_item_cod"], how="left")

    # 6. Preenchimento visual
    if "uo_sigla" in df.columns:
        df["uo_sigla"] = df["uo_sigla"].fillna("UO-" + df["uo_cod"].astype(str))
    if "acao_desc" in df.columns:
        df["acao_desc"] = df["acao_desc"].fillna("Ação " + df["acao_cod"].astype(str))

    # 7. Tipagem Final
    # Strings
    text_dims = [
        "cnpj_cpf_formatado", "num_contrato_saida", "num_obra", "num_empenho", 
        "razao_social_credor", "uo_sigla", "acao_desc", "elemento_item_desc"
    ]
    for col in text_dims:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "").replace("<NA>", "")
            
    # Ints
    int_cols = ["ano", "ano_rp", "grupo_cod", "fonte_cod", "ipu_cod"]
    df = _ensure_join_types(df, int_cols)

    # 8. Seleção
    final_cols = [c for c in RP_VIEW_COLS if c in df.columns]
    
    return df[final_cols].copy()