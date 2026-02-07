import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from my_pkg.transform.metrics import load_metrics
import time

# --- Configuração da Página ---
st.set_page_config(
    page_title="Propag Monitoramento",
    layout="wide",
    page_icon="📊"
)

# --- Função Auxiliar de Formatação ---
def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 1. Carregar Dados de Métricas (Cabeçalho) ---
try:
    vlr_plano, vlr_liquidado, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar bases locais de métricas: {e}")
    vlr_plano, vlr_liquidado, saldo = 0, 0, 0

# --- Layout do Cabeçalho ---
st.title("Propag - Monitoramento do Plano de Aplicação de Investimentos")
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Valor Total do Plano", format_currency(vlr_plano))
with col2:
    st.metric("Valor Total Liquidado", format_currency(vlr_liquidado))
with col3:
    st.metric("Saldo a Liquidar", format_currency(saldo))

st.markdown("---")

# --- 2. Conexão com Google Sheets ---
# TTL define de quanto em quanto tempo ele recarrega do banco (cache).
# Vamos colocar um valor baixo para ver edições logo.
conn = st.connection("gsheets", type=GSheetsConnection)

# Carrega os dados da planilha
try:
    data = conn.read(ttl=5)
except Exception as e:
    st.error("Erro ao conectar no Google Sheets. Verifique o secrets.toml e as permissões.")
    st.stop()

# Garantir tipos de dados corretos (Pandas às vezes carrega como texto)
# Lista de colunas numéricas editáveis
numeric_cols = [
    'valor_replanejado_total', 
    '1_bimestre_replanejado', '1_bimestre_realizado',
    '2_bimestre_replanejado', '2_bimestre_realizado',
    '3_bimestre_replanejado', '3_bimestre_realizado',
    '4_bimestre_replanejado', '4_bimestre_realizado',
    '5_bimestre_replanejado', '5_bimestre_realizado',
    '6_bimestre_replanejado', '6_bimestre_realizado'
]

# Preenche vazios com 0.0 para evitar erro de cálculo e converte
for col in numeric_cols:
    if col in data.columns:
        data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0.0)

# --- 3. Filtros ---
st.subheader("Filtros e Seleção")

# Filtro 1: Unidade Orçamentária
uos_disponiveis = data['uo_sigla'].unique().tolist()
uo_selecionada = st.selectbox("Selecione a Unidade Orçamentária (UO)", ["Todos"] + uos_disponiveis)

df_filtrado = data.copy()
if uo_selecionada != "Todos":
    df_filtrado = df_filtrado[df_filtrado['uo_sigla'] == uo_selecionada]

# Filtro 2 e 3: Intervenção OU Ação
col_f1, col_f2 = st.columns(2)
with col_f1:
    acoes_disponiveis = df_filtrado['acao_desc'].unique().tolist()
    acao_selecionada = st.selectbox("Filtrar por Ação Orçamentária", ["Todas"] + acoes_disponiveis)

with col_f2:
    intervencoes_disponiveis = df_filtrado['intervencao_desc'].unique().tolist()
    intervencao_selecionada = st.selectbox("Filtrar por Intervenção", ["Todas"] + intervencoes_disponiveis)

# Lógica de aviso e aplicação dos filtros
if acao_selecionada != "Todas" and intervencao_selecionada != "Todas":
    st.warning("⚠️ Você selecionou filtros de Ação e Intervenção simultaneamente. Mostrando a interseção.")

if acao_selecionada != "Todas":
    df_filtrado = df_filtrado[df_filtrado['acao_desc'] == acao_selecionada]

if intervencao_selecionada != "Todas":
    st.markdown(f"### Intervenção Selecionada: **{intervencao_selecionada}**")
    df_filtrado = df_filtrado[df_filtrado['intervencao_desc'] == intervencao_selecionada]
else:
    st.markdown("*Nenhuma intervenção específica selecionada.*")

# --- 4. Tabela Editável ---
st.markdown("### Dados para Preenchimento")
st.info("Edite os valores diretamente na tabela. Para adicionar uma nova linha, clique no '+' na parte inferior da tabela.")

# Configuração de colunas para o editor
# Bloqueia colunas que não devem ser editadas
column_config = {
    "uo_cod": st.column_config.NumberColumn(disabled=True),
    "uo_sigla": st.column_config.TextColumn(disabled=True),
    "acao_cod": st.column_config.NumberColumn(disabled=True),
    "acao_desc": st.column_config.TextColumn(disabled=True),
    "intervencao_cod": st.column_config.NumberColumn(disabled=True),
    "intervencao_desc": st.column_config.TextColumn(disabled=True),
    "marcos_principais": st.column_config.TextColumn(disabled=True),
    "valor_previsto_total": st.column_config.TextColumn(disabled=True), # Originalmente string no schema
    "novo_marco": st.column_config.SelectboxColumn(
        "Novo Marco?",
        options=["Sim", "Não"],
        default="Sim", # Padrão para novas linhas
        required=True
    )
}

# Criamos o editor
# num_rows="dynamic" permite adicionar/remover linhas
edited_df = st.data_editor(
    df_filtrado,
    num_rows="dynamic",
    column_config=column_config,
    use_container_width=True,
    key="editor_principal"
)

# --- 5. Lógica de Salvamento ---

# Botão para salvar
if st.button("💾 Salvar Alterações no Google Sheets", type="primary"):
    
    # 5.1 Validação de Novas Linhas
    # Identifica linhas que foram adicionadas (não estavam no original filtrado)
    # Lógica simplificada: Verifica se tem campos nulos nas colunas obrigatórias
    
    # Vamos validar se há linhas com NaN em colunas críticas
    cols_obrigatorias = [
        'uo_cod', 'uo_sigla', 'acao_cod', 'acao_desc', 
        'intervencao_cod', 'intervencao_desc', 'novo_marco'
    ]
    
    # Verifica NaN ou strings vazias
    tem_erro = False
    if edited_df[cols_obrigatorias].isnull().any().any():
        tem_erro = True
    
    if tem_erro:
        st.error("❌ Erro: Existem campos obrigatórios em branco. Por favor preencha todas as colunas de identificação para as novas linhas.")
    else:
        # 5.2 Atualização do DataFrame Mestre
        # Como filtramos os dados (df_filtrado), não podemos apenas salvar o edited_df
        # Precisamos atualizar o 'data' original com as mudanças feitas no 'edited_df'
        # e adicionar as linhas novas.
        
        # Estratégia: 
        # 1. Remover as linhas antigas que correspondem ao filtro atual do dataframe mestre
        # 2. Adicionar o edited_df ao dataframe mestre
        
        # Pega os índices do filtro original
        indices_originais = df_filtrado.index
        
        # Remove do dataframe mestre (data) as linhas que estavam sendo editadas
        data_sem_filtro = data.drop(indices_originais)
        
        # Concatena o que sobrou com o que foi editado
        final_df = pd.concat([data_sem_filtro, edited_df], ignore_index=True)
        
        # Força "Sim" no campo novo_marco para linhas que não tinham valor (novas)
        # O default do column_config ajuda na UI, mas aqui garantimos no backend
        final_df['novo_marco'] = final_df['novo_marco'].fillna('Sim')
        
        # Salva no Google Sheets
        try:
            conn.update(data=final_df)
            st.success("✅ Dados atualizados com sucesso no Google Sheets!")
            st.balloons()
            time.sleep(2)
            st.rerun() # Recarrega a página para refletir dados
        except Exception as e:
            st.error(f"Erro ao salvar no Google Sheets: {e}")