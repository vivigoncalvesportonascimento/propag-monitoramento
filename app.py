# app.py
import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from my_pkg.transform.metrics import load_metrics
import time

# --- Config da Página ---
st.set_page_config(
    page_title="Propag - Monitoramento do Plano de Aplicação de Investimentos",
    layout="wide",
    page_icon="📊"
)

# --- Função de formatação BR ---
def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- Cabeçalho: três métricas ---
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar bases locais de métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

st.title("Propag - Monitoramento do Plano de Aplicação de Investimentos")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Valor Total do Plano", brl(vlr_plano))
with c2:
    st.metric("Valor Total Liquidado", brl(vlr_liq))
with c3:
    st.metric("Saldo a Liquidar", brl(saldo))

st.divider()

# --- Conexão com Google Sheets ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Ler do secrets e permitir override via sidebar
ss = st.secrets.get("connections", {}).get("gsheets", {})
spreadsheet = ss.get("spreadsheet")
worksheet = ss.get("worksheet", "Página1")

with st.sidebar:
    st.header("Fonte de Dados (Google Sheets)")
    spreadsheet = st.text_input("URL/ID da Planilha", value=str(spreadsheet or ""))
    worksheet = st.text_input("Aba (worksheet)", value=str(worksheet or "Página1"))
    st.caption("Use a URL ou o ID. A aba deve existir e conter cabeçalho na linha 1.")

if not spreadsheet:
    st.error("❌ Configure a URL/ID da planilha em .streamlit/secrets.toml ou na sidebar.")
    st.stop()

try:
    data = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=5)
except Exception as e:
    st.error(f"Erro ao conectar no Google Sheets: {e}")
    st.stop()

# --- Tipagem e colunas esperadas ---
all_cols = [
    "uo_cod","uo_sigla","acao_cod","acao_desc","intervencao_cod","intervencao_desc",
    "marcos_principais","novo_marco","valor_previsto_total","valor_replanejado_total",
    "1_bimestre_planejado","1_bimestre_replanejado","1_bimestre_realizado",
    "2_bimestre_planejado","2_bimestre_replanejado","2_bimestre_realizado",
    "3_bimestre_planejado","3_bimestre_replanejado","3_bimestre_realizado",
    "4_bimestre_planejado","4_bimestre_replanejado","4_bimestre_realizado",
    "5_bimestre_planejado","5_bimestre_replanejado","5_bimestre_realizado",
    "6_bimestre_planejado","6_bimestre_replanejado","6_bimestre_realizado",
]
for c in all_cols:
    if c not in data.columns:
        data[c] = None

numeric_cols = [
    "valor_replanejado_total",
    "1_bimestre_replanejado","1_bimestre_realizado",
    "2_bimestre_replanejado","2_bimestre_realizado",
    "3_bimestre_replanejado","3_bimestre_realizado",
    "4_bimestre_replanejado","4_bimestre_realizado",
    "5_bimestre_replanejado","5_bimestre_realizado",
    "6_bimestre_replanejado","6_bimestre_realizado",
]
for col in numeric_cols:
    data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

# --- Filtros ---
st.subheader("Filtros")
col_f_uo, col_f_acao, col_f_int = st.columns([1,1,1])

with col_f_uo:
    uos = sorted([x for x in data["uo_sigla"].dropna().unique().tolist()])
    uo_sel = st.selectbox("Unidade Orçamentária (UO)", ["Todas"] + uos)

df_f = data.copy()
if uo_sel != "Todas":
    df_f = df_f[df_f["uo_sigla"] == uo_sel]

with col_f_acao:
    acoes = sorted([x for x in df_f["acao_desc"].dropna().unique().tolist()])
    acao_sel = st.selectbox("Ação Orçamentária", ["Todas"] + acoes)

with col_f_int:
    intervs = sorted([x for x in df_f["intervencao_desc"].dropna().unique().tolist()])
    interv_sel = st.selectbox("Intervenção", ["Todas"] + intervs)

# Exigir Intervenção OU Ação
if acao_sel == "Todas" and interv_sel == "Todas":
    st.info("🛈 Selecione **a Intervenção** ou **a Ação Orçamentária** para continuar.")
    st.stop()

# Se selecionar Intervenção, mostrar texto acima da tabela
if interv_sel != "Todas":
    st.markdown(f"### Intervenção Selecionada: **{interv_sel}**")

# Aplica filtros
if acao_sel != "Todas":
    df_f = df_f[df_f["acao_desc"] == acao_sel]
if interv_sel != "Todas":
    df_f = df_f[df_f["intervencao_desc"] == interv_sel]

st.divider()
st.subheader("Dados para Preenchimento")

st.info(
    "Edite os campos permitidos diretamente na tabela. "
    "Para **inserir nova linha**, use o botão `+` ao final da tabela. "
    "Novas linhas serão marcadas automaticamente como `novo_marco = 'Sim'`."
)

# Somente os campos solicitados como editáveis
editable_cols = set(numeric_cols)

column_config = {
    "uo_cod":                st.column_config.NumberColumn(disabled=True),
    "uo_sigla":              st.column_config.TextColumn(disabled=True),
    "acao_cod":              st.column_config.NumberColumn(disabled=True),
    "acao_desc":             st.column_config.TextColumn(disabled=True),
    "intervencao_cod":       st.column_config.NumberColumn(disabled=True),
    "intervencao_desc":      st.column_config.TextColumn(disabled=True),
    "marcos_principais":     st.column_config.TextColumn(disabled=True),
    "valor_previsto_total":  st.column_config.TextColumn(disabled=True),  # string segundo schema
    "1_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "2_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "3_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "4_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "5_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "6_bimestre_planejado":  st.column_config.CheckboxColumn(disabled=True),
    "novo_marco": st.column_config.SelectboxColumn(
        "Novo Marco?",
        options=["Sim","Não"],
        default="Sim",
        required=True
    )
}

# Garante default de 'novo_marco'
df_f["novo_marco"] = df_f["novo_marco"].fillna("Sim").astype(str)

edited_df = st.data_editor(
    df_f,
    num_rows="dynamic",
    use_container_width=True,
    column_config=column_config,
    disabled=[c for c in all_cols if (c not in editable_cols and c != "novo_marco")],
    key="editor_principal"
)

# --- Validação e Salvamento ---
if st.button("💾 Salvar alterações no Google Sheets", type="primary"):
    # Campos obrigatórios para novas linhas
    obrigatorias = [
        "uo_cod","uo_sigla","acao_cod","acao_desc",
        "intervencao_cod","intervencao_desc","marcos_principais",
        "valor_previsto_total","novo_marco"
    ]

    linhas_incompletas = edited_df[obrigatorias].isnull().any(axis=1) | (edited_df[obrigatorias] == "").any(axis=1)
    if linhas_incompletas.any():
        st.error("❌ Necessário preencher **todos os campos da linha**.")
        st.stop()

    edited_df["novo_marco"] = edited_df["novo_marco"].replace("", "Sim").fillna("Sim")

    # Atualiza o dataframe mestre preservando linhas fora do filtro
    data_sem = data.drop(df_f.index)
    final_df = pd.concat([data_sem, edited_df], ignore_index=True)

    try:
        conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=final_df)
        st.success("✅ Dados atualizados com sucesso no Google Sheets!")
        st.balloons()
        time.sleep(1.5)
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")