import pandas as pd
import os

def load_metrics():
    """
    Carrega e calcula as métricas do painel Propag.
    Retorna: (valor_total_plano, valor_total_liquidado, saldo_a_liquidar)
    """
    
    # --- 1. Definir caminhos (ajuste conforme necessário) ---
    # Assume que o script roda da raiz do projeto
    path_limites = "data-raw/propag_investimentos_limite_2026.csv"
    path_execucao = "datapackages/siafi-2026/data/execucao.csv.gz"
    path_rp = "datapackages/siafi-2026/data/restos_pagar.csv.gz"

    # Verifica se arquivos existem para evitar erro fatal
    if not all(os.path.exists(p) for p in [path_limites, path_execucao, path_rp]):
        return 0.0, 0.0, 0.0 # Retorna zeros se não achar as bases

    # --- 2. Carregar e Calcular Valor Total do Plano ---
    # O arquivo de limites parece usar encoding utf-8 (padrão)
    df_limites = pd.read_csv(path_limites)
    
    # Tratamento: converter string para float se necessário (pt-br para us)
    if df_limites['limite_propag'].dtype == 'O':
        df_limites['limite_propag'] = df_limites['limite_propag'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df_limites['limite_propag'] = pd.to_numeric(df_limites['limite_propag'], errors='coerce').fillna(0)
    
    valor_total_plano = df_limites['limite_propag'].sum()

    # --- 3. Calcular Valor Total Liquidado ---
    # Lógica: fonte_cod = 89 OU ipu_cod = 0. Ano = 2026.
    
    # 3.1 Base Execução
    df_exec = pd.read_csv(path_execucao, compression='gzip')
    filtro_exec = (df_exec['ano'] == 2026) & \
                  ((df_exec['fonte_cod'] == 89) | (df_exec['ipu_cod'] == 0))
    total_execucao = df_exec.loc[filtro_exec, 'vlr_liquidado'].sum()

    # 3.2 Base Restos a Pagar
    df_rp = pd.read_csv(path_rp, compression='gzip')
    # Atenção: "deve ser considerada a variável ano e não ano_rp"
    filtro_rp = (df_rp['ano'] == 2026) & \
                ((df_rp['fonte_cod'] == 89) | (df_rp['ipu_cod'] == 0))
    total_rp = df_rp.loc[filtro_rp, 'vlr_despesa_liquidada_rpnp'].sum()

    valor_total_liquidado = total_execucao + total_rp

    # --- 4. Saldo ---
    saldo_a_liquidar = valor_total_plano - valor_total_liquidado

    return valor_total_plano, valor_total_liquidado, saldo_a_liquidar