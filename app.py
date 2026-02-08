# streamlit/app.py
import time
import pandas as pd
import streamlit as st
from st_gsheets_connection import GSheetsConnection
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from my_pkg.transform.metrics import load_metrics
from my_pkg.transform.schema import ALL_COLS, NUMERIC_COLS, BOOL_COLS, EDITABLE_COLS, REQUIRED_ON_NEW

# -------------------- Config --------------------
st.set_page_config(
    page_title="Propag - Monitoramento do Plano de Aplicação de Investimentos",
    page_icon="📊",
    layout="wide",
)

# -------------------- Utils --------------------
def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def load_rbac_from_secrets() -> dict[str, list]:
    raw = st.secrets.get("rbac", {})
    out = {}
    for user, lst in raw.items():
        if isinstance(lst, list) and len(lst) == 1 and lst[0] == "*":
            out[user] = ["*"]
        else:
            out[user] = list(map(int, lst))
    return out

def load_access_yaml(path: str = "security/access_control.yaml") -> dict[str, list]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=SafeLoader) or {}
        users = data.get("users", {})
        return {u: v.get("allowed_uos", []) for u, v in users.items()}
    except FileNotFoundError:
        return {}

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    for c in ALL_COLS:
        if c not in data.columns:
            data[c] = None
    for col in NUMERIC_COLS:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)
    for col in BOOL_COLS:
        if data[col].dtype != bool:
            data[col] = data[col].astype(str).str.upper().isin(["TRUE", "1", "SIM"])
    return data[ALL_COLS]

def validate_new_rows(df_before: pd.DataFrame, df_after: pd.DataFrame,
                      allowed_uos: list[int] | None, is_admin: bool,
                      working_uo: int | None) -> tuple[bool, str]:
    # Detecta novas linhas por chave composta
    before_idx = set(map(tuple, df_before[["uo_cod","acao_cod","intervencao_cod","marcos_principais"]].astype(str).values))
    after_idx  = set(map(tuple, df_after[["uo_cod","acao_cod","intervencao_cod","marcos_principais"]].astype(str).values))
    new_keys = after_idx - before_idx

    is_new = df_after.apply(
        lambda r: (str(r["uo_cod"]), str(r["acao_cod"]), str(r["intervencao_cod"]), str(r["marcos_principais"])) in new_keys,
        axis=1
    )
    new_rows = df_after[is_new].copy()

    # Obrigatórios em novas linhas
    if not new_rows.empty:
        if new_rows[REQUIRED_ON_NEW].isnull().any(axis=1).any() or (new_rows[REQUIRED_ON_NEW] == "").any(axis=1).any():
            return False, "Necessário preencher todos os campos da linha nova."
        # marca novo_marco = 'Sim'
        df_after.loc[is_new, "novo_marco"] = "Sim"

    # Restrição por UO (não-admin)
    if not is_admin:
        if df_after["uo_cod"].isnull().any():
            return False, "Há linhas sem UO definida."
        uos = set(pd.to_numeric(df_after["uo_cod"], errors="coerce").fillna(-1).astype(int).tolist())
        if allowed_uos is None or not uos.issubset(set(allowed_uos)):
            return False, "Você só pode visualizar/editar sua(s) UO(s) autorizada(s)."
        if working_uo is not None and (uos - {working_uo}):
            return False, f"As linhas devem permanecer na UO {working_uo}."
    return True, ""

# -------------------- Autenticação --------------------
auth_cfg = st.secrets.get("auth", {})
credentials = st.secrets.get("auth", {}).get("credentials", {})

auth = stauth.Authenticate(
    credentials=credentials,
    cookie_name=auth_cfg.get("cookie_name", "propag_monitoramento"),
    key=auth_cfg.get("cookie_key", "chave-secreta"),
    cookie_expiry_days=int(auth_cfg.get("cookie_expiry_days", 3)),
)

st.sidebar.title("Acesso")
name, auth_status, username = auth.login("Entrar", "sidebar")
if not auth_status:
    if auth_status is False:
        st.sidebar.error("Usuário ou senha inválidos.")
    st.stop()

auth.logout("Sair", "sidebar")
st.sidebar.success(f"Olá, {name}!")

# RBAC
rbac_secrets = load_rbac_from_secrets()
rbac_yaml = load_access_yaml()  # opcional
allowed_uos_list = []
if username in rbac_secrets:
    allowed_uos_list = rbac_secrets[username]
if username in rbac_yaml and not allowed_uos_list:
    allowed_uos_list = rbac_yaml[username]

is_admin = ("*" in allowed_uos_list)
allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

# Para usuários com múltiplas UOs (ex.: DER), "UO de trabalho" na sidebar
working_uo = None
if is_admin:
    st.sidebar.info("Perfil: **Admin (acesso total)**")
else:
    if not allowed_uos:
        st.error("Sua conta não possui UO(s) autorizada(s). Contate o administrador.")
        st.stop()
    if len(allowed_uos) == 1:
        working_uo = list(allowed_uos)[0]
        st.sidebar.info(f"UO autorizada: {working_uo}")
    else:
        working_uo = st.sidebar.selectbox("UO de trabalho", sorted(allowed_uos))

# -------------------- Métricas --------------------
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

st.title("Propag - Monitoramento do Plano de Aplicação de Investimentos")
c1, c2, c3 = st.columns(3)
with c1: st.metric("Valor Total do Plano", brl(vlr_plano))
with c2: st.metric("Valor Total Liquidado", brl(vlr_liq))
with c3: st.metric("Saldo a Liquidar", brl(saldo))
st.divider()

# -------------------- Google Sheets --------------------
conn = st.connection("gsheets", type=GSheetsConnection)
ss = st.secrets.get("connections", {}).get("gsheets", {})
spreadsheet = ss.get("spreadsheet")
worksheet = ss.get("worksheet", "Página1")

with st.sidebar:
    st.header("Dados (Google Sheets)")
    spreadsheet = st.text_input("URL/ID da Planilha", value=str(spreadsheet or ""))
    worksheet = st.text_input("Aba (worksheet)", value=str(worksheet or "Página1"))
    st.caption("A planilha deve estar compartilhada com a Service Account (Editor).")

if not spreadsheet:
    st.error("❌ Configure a URL/ID da planilha em .streamlit/secrets.toml ou na sidebar.")
    st.stop()

try:
    data_raw = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=5)
except Exception as e:
    st.error(f"Erro ao conectar no Google Sheets: {e}")
    st.stop()

data = normalize_dataframe(data_raw)

# -------------------- RLS por UO --------------------
if not is_admin:
    data = data[pd.to_numeric(data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(working_uo)].copy()

# -------------------- Filtros visuais --------------------
st.subheader("Filtros")
col_uo, col_acao, col_interv = st.columns([1, 1, 1])

with col_uo:
    if is_admin:
        uos = sorted(data["uo_sigla"].dropna().unique().tolist())
        uo_sel = st.selectbox("Unidade Orçamentária (UO)", ["Todas"] + uos)
    else:
        uo_sel = "Filtrado pela sua credencial"

df_f = data.copy()
if is_admin and uo_sel != "Todas":
    df_f = df_f[df_f["uo_sigla"] == uo_sel]

with col_acao:
    acoes = sorted(df_f["acao_desc"].dropna().unique().tolist())
    acao_sel = st.selectbox("Ação Orçamentária", ["Todas"] + acoes)

with col_interv:
    intervs = sorted(df_f["intervencao_desc"].dropna().unique().tolist())
    interv_sel = st.selectbox("Intervenção", ["Todas"] + intervs)

if acao_sel == "Todas" and interv_sel == "Todas":
    st.info("🧭 Selecione **a Intervenção** OU **a Ação Orçamentária** para continuar.")
    st.stop()

if interv_sel != "Todas":
    st.markdown(f"### Intervenção Selecionada: **{interv_sel}**")

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

# Editor: apenas replanejado/realizado editável; trava UO para não-admin
disabled_cols = [c for c in ALL_COLS if (c not in EDITABLE_COLS and c != "novo_marco")]
column_config = {
    "valor_previsto_total": st.column_config.TextColumn(disabled=True),
    "1_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "2_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "3_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "4_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "5_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "6_bimestre_planejado": st.column_config.CheckboxColumn(disabled=True),
    "novo_marco": st.column_config.SelectboxColumn(
        "Novo Marco?", options=["Sim", "Não"], default="Sim", required=True
    ),
    "acao_cod": st.column_config.NumberColumn(disabled=False),
    "acao_desc": st.column_config.TextColumn(disabled=False),
    "intervencao_cod": st.column_config.NumberColumn(disabled=False),
    "intervencao_desc": st.column_config.TextColumn(disabled=False),
    "marcos_principais": st.column_config.TextColumn(disabled=False),
}

if not is_admin:
    column_config["uo_cod"] = st.column_config.NumberColumn(disabled=True)
    column_config["uo_sigla"] = st.column_config.TextColumn(disabled=True)
else:
    column_config["uo_cod"] = st.column_config.NumberColumn(disabled=False)
    column_config["uo_sigla"] = st.column_config.TextColumn(disabled=False)

# Para novos registros do usuário comum, garanta uo_cod fixo
if not is_admin and "uo_cod" in df_f.columns:
    df_f["uo_cod"] = int(working_uo)

df_f["novo_marco"] = df_f["novo_marco"].fillna("Não").astype(str)

edited_df = st.data_editor(
    df_f,
    num_rows="dynamic",
    use_container_width=True,
    column_config=column_config,
    disabled=disabled_cols,
    key="editor_principal",
)

# -------------------- Salvar --------------------
if st.button("💾 Salvar alterações no Google Sheets", type="primary"):
    is_valid, msg = validate_new_rows(
        df_before=df_f,
        df_after=edited_df,
        allowed_uos=list(allowed_uos) if allowed_uos else None,
        is_admin=is_admin,
        working_uo=None if is_admin else int(working_uo),
    )
    if not is_valid:
        st.error(f"❌ {msg}")
        st.stop()

    # Mescla preservando tudo que não está no subconjunto filtrado atual
    mask_to_drop = data_raw.index.isin(df_f.index)
    data_sem = data_raw.drop(index=data_raw.index[mask_to_drop])
    final_df = pd.concat([data_sem, edited_df], ignore_index=True)[ALL_COLS]

    try:
        conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=final_df)
        st.success("✅ Dados atualizados com sucesso!")
        st.balloons()
        time.sleep(1.2)
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")