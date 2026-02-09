# my_pkg/transform/execucao_view.py
# -*- coding: utf-8 -*-
"""
Carrega a tabela de execução (fato) e incorpora dimensões (uo, ação e elemento_item),
aplicando o filtro global do painel:
    (fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261

Entrega apenas as colunas solicitadas para a visualização do Streamlit.
"""

from __future__ import annotations
import pandas as pd
from functools import lru_cache

# Colunas de saída na ordem desejada (como você especificou)
EXEC_VIEW_COLS = [
    "ano",
    "mes_cod",
    "uo_cod",
    "uo_sigla",
    "acao_cod",
    "acao_desc",
    "grupo_cod",
    "fonte_cod",
    "ipu_cod",
    "elemento_item_cod",
    "elemento_item_desc",
    "cnpj_cpf_formatado",
    "num_contrato_saida",
    "num_obra",
    "num_empenho",
    "vlr_empenhado",
    "vlr_liquidado",
    "vlr_liquidado_retido",
    "vlr_pago_orcamentario",
]

# Arquivos (instalados via dpm / datapackage)
PATH_EXEC = "datapackages/siafi-2026/data/execucao.csv.gz"
PATH_UO = "datapackages/aux-classificadores/data/uo.csv"
PATH_ACAO = "datapackages/aux-classificadores/data/acao.csv"
PATH_ELI = "datapackages/aux-classificadores/data/elemento_item.csv"


@lru_cache(maxsize=2)
def _load_execucao_raw() -> pd.DataFrame:
    """Lê a execução com dtype automático e baixa memória."""
    df = pd.read_csv(PATH_EXEC, compression="gzip", low_memory=False)
    return df


@lru_cache(maxsize=4)
def _load_dim_uo() -> pd.DataFrame:
    """Lê dimensão UO e deixa só o necessário para o join."""
    uo = pd.read_csv(PATH_UO, low_memory=False)
    uo = uo[["ano", "uo_cod", "uo_sigla"]].drop_duplicates()
    return uo


@lru_cache(maxsize=4)
def _load_dim_acao() -> pd.DataFrame:
    """Lê dimensão Ação e deixa só o necessário para o join."""
    ac = pd.read_csv(PATH_ACAO, low_memory=False)
    ac = ac[["ano", "acao_cod", "acao_desc"]].drop_duplicates()
    return ac


@lru_cache(maxsize=4)
def _load_dim_elemento_item() -> pd.DataFrame:
    """Lê dimensão Elemento Item e deixa só o necessário para o join."""
    eli = pd.read_csv(PATH_ELI, low_memory=False)
    eli = eli[["ano", "elemento_item_cod", "elemento_item_desc"]].drop_duplicates()
    return eli


def _apply_global_filter(df: pd.DataFrame) -> pd.DataFrame:
    """(fonte_cod = 89 OR ipu_cod = 0) AND uo_cod != 1261"""
    return df.loc[
        ((df["fonte_cod"] == 89) | (df["ipu_cod"] == 0)) & (df["uo_cod"] != 1261)
    ].copy()


def load_execucao_view(restrict_uo: int | None = None) -> pd.DataFrame:
    """
    Retorna a visão de execução com dimensões e já filtrada pelo critério global.
    Se `restrict_uo` for informado, restringe também a essa UO (útil para usuários não-admin).
    """
    df = _load_execucao_raw()
    df = _apply_global_filter(df)

    # Opcional: restringe por UO do usuário (RLS adicional)
    if restrict_uo is not None:
        df = df.loc[df["uo_cod"] == int(restrict_uo)].copy()

    # JOINs com dimensões (sempre por ano + código)
    uo = _load_dim_uo()
    df = df.merge(uo, on=["ano", "uo_cod"], how="left")

    ac = _load_dim_acao()
    df = df.merge(ac, on=["ano", "acao_cod"], how="left")

    eli = _load_dim_elemento_item()
    df = df.merge(eli, on=["ano", "elemento_item_cod"], how="left")

    # Seleção/ordem final de colunas
    keep = [c for c in EXEC_VIEW_COLS if c in df.columns]
    out = df[keep].copy()

    # Tipos numéricos garantidos
    for col in ["vlr_empenhado", "vlr_liquidado", "vlr_liquidado_retido", "vlr_pago_orcamentario"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    # Inteiros que às vezes vêm como floats
    for col in ["mes_cod", "uo_cod", "acao_cod", "grupo_cod", "fonte_cod", "ipu_cod",
                "elemento_item_cod", "num_contrato_saida", "num_obra", "num_empenho"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")

    return out