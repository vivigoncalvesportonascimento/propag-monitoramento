# my_pkg/transform/metrics.py
import os
import pandas as pd


def load_metrics():
    """
    Carrega e calcula as métricas do painel Propag.
    Regras:
      - Ano = 2026 (limites, execução e RP)
      - Considerar Propag se (fonte_cod == 89) OU (ipu_cod == 0)
      - Valor Total do Plano: soma de 'limite_propag' (limites)
      - Valor Total Liquidado: soma de 'vlr_liquidado' (execução) + 'vlr_despesa_liquidada_rpnp' (RP)
      - Em RP, considerar a variável 'ano' (não 'ano_rp')
    Retorna: (valor_total_plano, valor_total_liquidado, saldo_a_liquidar)
    """

    print("--- INICIANDO CÁLCULO DE MÉTRICAS ---")

    # 1) Caminhos das bases (ajuste se necessário)
    path_limites = "data-raw/propag_investimentos_limite_2026.csv"
    path_execucao = "datapackages/siafi-2026/data/execucao.csv.gz"
    path_rp = "datapackages/siafi-2026/data/restos_pagar.csv.gz"

    # 2) Verificação de existência
    for arq in (path_limites, path_execucao, path_rp):
        if not os.path.exists(arq):
            print(f"ERRO CRÍTICO: Arquivo não encontrado: {arq}")
            # Permite abrir o app, mesmo sem dados
            return 0.0, 0.0, 0.0

    try:
        # --- 3) Valor Total do Plano (limites) ---
        # CSV com padrão BR: ; como separador e , como decimal
        df_lim = pd.read_csv(
            path_limites, sep=";", encoding="latin1", thousands=".", decimal=","
        )

        # Tratamento se vier string tipo "R$ 1.234,56"
        if df_lim["limite_propag"].dtype == "O":
            df_lim["limite_propag"] = (
                df_lim["limite_propag"]
                .astype(str)
                .str.replace("R$", "", regex=False)
                .str.replace(".", "", regex=False)  # remove milhar
                .str.replace(",", ".", regex=False)  # vírgula -> ponto
            )
        df_lim["limite_propag"] = pd.to_numeric(
            df_lim["limite_propag"], errors="coerce"
        ).fillna(0.0)

        valor_total_plano = float(df_lim["limite_propag"].sum())
        print(f"Valor Total Plano: {valor_total_plano:,.2f}")

        # --- 4) Execução (SIAFI - exercício 2026) ---
        df_exec = pd.read_csv(path_execucao, compression="gzip")
        filtro_exec = (df_exec["ano"] == 2026) & (
            (df_exec["fonte_cod"] == 89) | (df_exec["ipu_cod"] == 0)
        )
        total_execucao = float(df_exec.loc[filtro_exec, "vlr_liquidado"].sum())

        # --- 5) Restos a Pagar (liquidados em 2026) ---
        # Observação: usar a variável 'ano' (NÃO 'ano_rp').
        df_rp = pd.read_csv(path_rp, compression="gzip")
        filtro_rp = (df_rp["ano"] == 2026) & (
            (df_rp["fonte_cod"] == 89) | (df_rp["ipu_cod"] == 0)
        )
        total_rp = float(
            df_rp.loc[filtro_rp, "vlr_despesa_liquidada_rpnp"].sum()
        )

        # --- 6) Consolidação ---
        valor_total_liquidado = total_execucao + total_rp
        saldo_a_liquidar = valor_total_plano - valor_total_liquidado

        print(f"Valor Total Liquidado: {valor_total_liquidado:,.2f}")
        print(f"Saldo a Liquidar: {saldo_a_liquidar:,.2f}")

        return valor_total_plano, valor_total_liquidado, saldo_a_liquidar

    except Exception as e:
        print(f"ERRO NO PROCESSAMENTO DOS DADOS: {e}")
        import traceback

        traceback.print_exc()
        return 0.0, 0.0, 0.0