# my_pkg/transform/metrics.py
import os
import pandas as pd

def _to_float_br(series: pd.Series) -> pd.Series:
    s = series.astype(str)
    s = s.str.replace("R$", "", regex=False)
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def load_metrics():
    path_limites  = "data-raw/propag_investimentos_limite_2026.csv"
    path_execucao = "datapackages/siafi-2026/data/execucao.csv.gz"
    path_rp       = "datapackages/siafi-2026/data/restos_pagar.csv.gz"

    for arq in (path_limites, path_execucao, path_rp):
        if not os.path.exists(arq):
            return 0.0, 0.0, 0.0

    df_lim = pd.read_csv(path_limites, sep=";", encoding="latin1", thousands=".", decimal=",")
    if df_lim["limite_propag"].dtype == "O":
        df_lim["limite_propag"] = _to_float_br(df_lim["limite_propag"])
    valor_total_plano = float(df_lim["limite_propag"].sum())

    df_exec = pd.read_csv(path_execucao, compression="gzip", low_memory=False)
    filtro_exec = (df_exec["ano"] == 2026) & (
        (df_exec["fonte_cod"] == 89) | (df_exec["ipu_cod"] == 0)
    )
    total_execucao = float(df_exec.loc[filtro_exec, "vlr_liquidado"].sum())

    df_rp = pd.read_csv(path_rp, compression="gzip", low_memory=False)
    filtro_rp = (df_rp["ano"] == 2026) & (
        (df_rp["fonte_cod"] == 89) | (df_rp["ipu_cod"] == 0)
    )
    total_rp = float(df_rp.loc[filtro_rp, "vlr_despesa_liquidada_rpnp"].sum())

    valor_total_liquidado = total_execucao + total_rp
    saldo_a_liquidar = valor_total_plano - valor_total_liquidado
    return valor_total_plano, valor_total_liquidado, saldo_a_liquidar