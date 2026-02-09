# my_pkg/transform/metrics.py
# -*- coding: utf-8 -*-
"""
Métricas do topo do painel:

- Valor Total do Plano:
  Somatório de 'limite_propag' da base data-raw/propag_investimentos_limite_2026.csv
- Valor Total Liquidado:
  Soma:
    * 'vlr_liquidado' da base datapackages/siafi-2026/data/execucao.csv.gz (ano=2026)
    * 'vlr_despesa_liquidada_rpnp' da base datapackages/siafi-2026/data/restos_pagar.csv.gz (ano=2026)
  Somente quando (fonte_cod = 89 OR ipu_cod = 0) E (uo_cod != 1261 — exclui SEE)
- Saldo a Liquidar = Valor Total do Plano - Valor Total Liquidado
"""

from __future__ import annotations
import os
import pandas as pd


def _to_float_br(series: pd.Series) -> pd.Series:
    """Converte textos no formato 'R$ 1.234,56' para float com ponto decimal."""
    s = series.astype(str)
    s = s.str.replace("R$", "", regex=False)
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def load_metrics() -> tuple[float, float, float]:
    """
    Retorna (valor_total_plano, valor_total_liquidado, saldo_a_liquidar)
    alinhado ao filtro global do painel.
    """
    path_limites = "data-raw/propag_investimentos_limite_2026.csv"
    path_execucao = "datapackages/siafi-2026/data/execucao.csv.gz"
    path_rp = "datapackages/siafi-2026/data/restos_pagar.csv.gz"

    # Se faltar qualquer arquivo, retorna zero para não quebrar o app.
    for arq in (path_limites, path_execucao, path_rp):
        if not os.path.exists(arq):
            return 0.0, 0.0, 0.0

    # --- Valor Total do Plano ---
    # CSV de limites está geralmente em "pt-BR" com ; , e .
    df_lim = pd.read_csv(path_limites, sep=";", encoding="latin1", low_memory=False)
    if df_lim["limite_propag"].dtype == "O":
        df_lim["limite_propag"] = _to_float_br(df_lim["limite_propag"])
    valor_total_plano = float(df_lim["limite_propag"].sum())

    # --- Valor Total Liquidado (execução + RP liquidado) ---
    # Execução no exercício (2026)
    df_exec = pd.read_csv(path_execucao, compression="gzip", low_memory=False)
    # Garante tipos numéricos
    for c in ("ano", "uo_cod", "fonte_cod", "ipu_cod"):
        if c in df_exec.columns:
            df_exec[c] = pd.to_numeric(df_exec[c], errors="coerce")
    if "vlr_liquidado" in df_exec.columns:
        df_exec["vlr_liquidado"] = pd.to_numeric(df_exec["vlr_liquidado"], errors="coerce").fillna(0.0)

    filtro_exec = (
        (df_exec["ano"] == 2026)
        & (((df_exec["fonte_cod"] == 89) | (df_exec["ipu_cod"] == 0)))
        & (df_exec["uo_cod"] != 1261)  # exclui SEE
    )
    total_execucao = float(df_exec.loc[filtro_exec, "vlr_liquidado"].sum())

    # Restos a pagar liquidados em 2026
    df_rp = pd.read_csv(path_rp, compression="gzip", low_memory=False)
    for c in ("ano", "uo_cod", "fonte_cod", "ipu_cod"):
        if c in df_rp.columns:
            df_rp[c] = pd.to_numeric(df_rp[c], errors="coerce")
    if "vlr_despesa_liquidada_rpnp" in df_rp.columns:
        df_rp["vlr_despesa_liquidada_rpnp"] = pd.to_numeric(
            df_rp["vlr_despesa_liquidada_rpnp"], errors="coerce"
        ).fillna(0.0)

    filtro_rp = (
        (df_rp["ano"] == 2026)
        & (((df_rp["fonte_cod"] == 89) | (df_rp["ipu_cod"] == 0)))
        & (df_rp["uo_cod"] != 1261)  # exclui SEE
    )
    total_rp = float(df_rp.loc[filtro_rp, "vlr_despesa_liquidada_rpnp"].sum())

    valor_total_liquidado = total_execucao + total_rp
    saldo_a_liquidar = valor_total_plano - valor_total_liquidado
    return valor_total_plano, valor_total_liquidado, saldo_a_liquidar