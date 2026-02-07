import pandas as pd
import os
import sys

def load_metrics():
    """
    Carrega e calcula as métricas do painel Propag.
    Retorna: (valor_total_plano, valor_total_liquidado, saldo_a_liquidar)
    """
    print("--- INICIANDO CÁLCULO DE MÉTRICAS ---")

    # 1. Definição dos caminhos
    # Ajuste se seus arquivos estiverem em pastas diferentes
    path_limites = "data-raw/propag_investimentos_limite_2026.csv"
    path_execucao = "datapackages/siafi-2026/data/execucao.csv.gz"
    path_rp = "datapackages/siafi-2026/data/restos_pagar.csv.gz"

    # 2. Verificação de existência dos arquivos
    arquivos = [path_limites, path_execucao, path_rp]
    for arq in arquivos:
        if not os.path.exists(arq):
            print(f"ERRO CRÍTICO: Arquivo não encontrado: {arq}")
            # Retorna zeros para o painel abrir mesmo sem dados, mas avisa no terminal
            return 0.0, 0.0, 0.0

    try:
        # --- 3. Calcular Valor Total do Plano ---
        print(f"Lendo base de limites: {path_limites}")
        # O encoding 'latin1' ou 'cp1252' é comum em arquivos do Excel/Gov BR
        # sep=';' é o padrão brasileiro, thousands='.' remove pontos de milhar, decimal=',' ajusta decimais
        df_limites = pd.read_csv(
            path_limites, 
            sep=';', 
            encoding='latin1', 
            thousands='.', 
            decimal=','
        )
        
        # Limpeza extra caso a coluna venha suja (ex: "R$ 1.000,00")
        if df_limites['limite_propag'].dtype == 'O':
            df_limites['limite_propag'] = (
                df_limites['limite_propag']
                .astype(str)
                .str.replace('R$', '', regex=False)
                .str.replace('.', '', regex=False) # Tira ponto de milhar
                .str.replace(',', '.', regex=False) # Troca virgula por ponto
            )
            df_limites['limite_propag'] = pd.to_numeric(df_limites['limite_propag'], errors='coerce').fillna(0)
        
        valor_total_plano = df_limites['limite_propag'].sum()
        print(f"Valor Total Plano calculado: {valor_total_plano}")

        # --- 4. Calcular Execução (SIAFI) ---
        print("Lendo base de execução (pode demorar um pouco)...")
        # Bases do DPM (SIAFI) geralmente são padrão CSV (sep=',') e UTF-8
        df_exec = pd.read_csv(path_execucao, compression='gzip')
        
        filtro_exec = (df_exec['ano'] == 2026) & \
                      ((df_exec['fonte_cod'] == 89) | (df_exec['ipu_cod'] == 0))
        total_execucao = df_exec.loc[filtro_exec, 'vlr_liquidado'].sum()

        print("Lendo base de Restos a Pagar...")
        df_rp = pd.read_csv(path_rp, compression='gzip')
        
        filtro_rp = (df_rp['ano'] == 2026) & \
                    ((df_rp['fonte_cod'] == 89) | (df_rp['ipu_cod'] == 0))
        total_rp = df_rp.loc[filtro_rp, 'vlr_despesa_liquidada_rpnp'].sum()

        valor_total_liquidado = total_execucao + total_rp
        print(f"Valor Total Liquidado calculado: {valor_total_liquidado}")

        # --- 5. Saldo ---
        saldo_a_liquidar = valor_total_plano - valor_total_liquidado
        
        return valor_total_plano, valor_total_liquidado, saldo_a_liquidar

    except Exception as e:
        print(f"ERRO NO PROCESSAMENTO DOS DADOS: {e}")
        # Mostra onde o erro aconteceu
        import traceback
        traceback.print_exc()
        return 0.0, 0.0, 0.0