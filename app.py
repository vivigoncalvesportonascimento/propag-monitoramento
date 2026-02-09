# app.py
# -*- coding: utf-8 -*-
"""
Propag - Monitoramento do Plano de Aplicação de Investimentos

Este app:
- Autentica usuários (streamlit-authenticator) e aplica RBAC por UO.
- Lê/atualiza dados de planejamento via Google Sheets (st-gsheets-connection).
- Mostra métricas do topo (limite do plano / liquidado / saldo).
- Exibe e permite editar uma tabela (cronograma) com validações.
- Seção "Execução do exercício":
    (a) Filtros de linhas (opcionais) para recortar o dataset;
    (b) Tabela dinâmica (tipo pivot) em que você escolhe Dimensões e Medidas, e o app
        retorna exatamente as colunas selecionadas, somando as medidas por grupo.
  Regra global SEMPRE aplicada na Execução: (fonte = 89 OU ipu = 0) e uo_cod != 1261 (exclui SEE).

Requisitos:
- .streamlit/secrets.toml com blocos 'auth', 'rbac' e 'connections.gsheets'.
- A Service Account do Google precisa de permissão (Editor) na planilha.
"""

from __future__ import annotations

import time
from functools import lru_cache
from collections.abc import Mapping

import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader

from streamlit_gsheets import GSheetsConnection
import streamlit_authenticator as stauth

# Métricas (ajustadas para excluir SEE no arquivo do projeto)
from my_pkg.transform.metrics import load_metrics
# Esquema da tabela de planejamento (mantido do seu projeto)
from my_pkg.transform.schema import (
    ALL_COLS,
    NUMERIC_COLS,
    BOOL_COLS,
    EDITABLE_COLS,
    REQUIRED_ON_NEW,
)

# =============================================================================
# Configuração da página
# =============================================================================
st.set_page_config(
    page_title="Propag - Monitoramento do Plano de Aplicação de Investimentos",
    page_icon="📊",
    layout="wide",
)

# =============================================================================
# Utilidades
# =============================================================================
def brl(value: float) -> str:
    """Formata número como moeda pt-BR (uso rápido)."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _to_plain_dict(obj):
    """Converte SecretsMapping/listas aninhadas em dict/list 'puros' (mutáveis)."""
    if isinstance(obj, Mapping):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(x) for x in obj]
    return obj

def load_rbac_from_secrets() -> dict[str, list]:
    """
    Lê mapeamento de RBAC de st.secrets["rbac"].
    - Usuário com ["*"] é admin.
    - Demais usuários: lista de UOs (inteiros).
    """
    raw = st.secrets.get("rbac", {})
    out: dict[str, list] = {}
    for user, lst in raw.items():
        if isinstance(lst, list) and len(lst) == 1 and lst[0] == "*":
            out[user] = ["*"]
        else:
            out[user] = list(map(int, lst))
    return out

def load_access_yaml(path: str = "security/access_control.yaml") -> dict[str, list]:
    """
    Opcional: carrega YAML externo de controle de acesso.
    Estrutura esperada:
      users:
        usuario_x:
          allowed_uos: [1234, 5678]
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=SafeLoader) or {}
        users = data.get("users", {})
        return {u: v.get("allowed_uos", []) for u, v in users.items()}
    except FileNotFoundError:
        return {}

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante presença/ordem de colunas, normaliza tipos numéricos e booleanos,
    e retorna somente as colunas esperadas (schema do seu projeto).
    """
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

def validate_new_rows(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    allowed_uos: list[int] | None,
    is_admin: bool,
    working_uo: int | None,
) -> tuple[bool, str, pd.DataFrame]:
    """
    Valida novas linhas (campos obrigatórios) e marca 'novo_marco' = 'Sim'.
    Também reforça restrição por UO para usuários não-admin.

    Retorna: (is_valid, msg, df_after_possivelmente_ajustado)
    """
    before_idx = set(
        map(
            tuple,
            df_before[
                ["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]
            ]
            .astype(str)
            .values,
        )
    )
    after_idx = set(
        map(
            tuple,
            df_after[
                ["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]
            ]
            .astype(str)
            .values,
        )
    )
    new_keys = after_idx - before_idx

    is_new = df_after.apply(
        lambda r: (
            str(r["uo_cod"]),
            str(r["acao_cod"]),
            str(r["intervencao_cod"]),
            str(r["marcos_principais"]),
        ) in new_keys,
        axis=1,
    )
    new_rows = df_after[is_new].copy()

    # Obrigatórios em novas linhas
    if not new_rows.empty:
        if (
            new_rows[REQUIRED_ON_NEW].isnull().any(axis=1).any()
            or (new_rows[REQUIRED_ON_NEW] == "").any(axis=1).any()
        ):
            return False, "Necessário preencher todos os campos da linha nova.", df_after
        # Marca 'novo_marco' = 'Sim'
        df_after.loc[is_new, "novo_marco"] = "Sim"

    # Restrições por UO (não-admin)
    if not is_admin:
        if df_after["uo_cod"].isnull().any():
            return False, "Há linhas sem UO definida.", df_after
        uos = set(
            pd.to_numeric(df_after["uo_cod"], errors="coerce")
            .fillna(-1)
            .astype(int)
            .tolist()
        )
        if allowed_uos is None or not uos.issubset(set(allowed_uos)):
            return (
                False,
                "Você só pode visualizar/editar sua(s) UO(s) autorizada(s).",
                df_after,
            )
        if working_uo is not None and (uos - {working_uo}):
            return False, f"As linhas devem permanecer na UO {working_uo}.", df_after

    return True, "", df_after

# =============================================================================
# Autenticação (deep copy dos segredos + nova assinatura login/logout)
# =============================================================================
auth_cfg_raw = st.secrets.get("auth", {})
credentials_raw = auth_cfg_raw.get("credentials", {})

auth_cfg = _to_plain_dict(auth_cfg_raw)       # dict mutável
credentials = _to_plain_dict(credentials_raw) # dict mutável

if "usernames" not in credentials or not isinstance(credentials["usernames"], dict):
    st.error(
        "Configuração de credenciais inválida em st.secrets['auth']['credentials']. "
        "Esperado: {'usernames': {...}}."
    )
    st.stop()

auth = stauth.Authenticate(
    credentials=credentials,
    cookie_name=auth_cfg.get("cookie_name", "propag_monitoramento"),
    cookie_key=auth_cfg.get("cookie_key", "chave-secreta"),
    cookie_expiry_days=int(auth_cfg.get("cookie_expiry_days", 1)),
)

st.sidebar.title("Acesso")

# Nova assinatura: 1º parâmetro = location; título do form via fields
login_result = auth.login(location="sidebar", fields={"Form name": "Entrar"})
# Em algumas versões a função retorna a tupla; em outras popula st.session_state
if isinstance(login_result, tuple):
    name, auth_status, username = login_result
else:
    name = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

if not auth_status:
    if auth_status is False:
        st.sidebar.error("Usuário ou senha inválidos.")
    st.stop()

# Logout com key única para evitar colisão
auth.logout(button_name="Sair", location="sidebar", key="logout_sidebar")
st.sidebar.success(f"Olá, {name}!")

# RBAC (secrets + opcional YAML)
rbac_secrets = load_rbac_from_secrets()
rbac_yaml = load_access_yaml()  # opcional
allowed_uos_list = []
if username in rbac_secrets:
    allowed_uos_list = rbac_secrets[username]
if username in rbac_yaml and not allowed_uos_list:
    allowed_uos_list = rbac_yaml[username]

is_admin = ("*" in allowed_uos_list)
allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

# Usuário com múltiplas UOs escolhe 'UO de trabalho'
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

# =============================================================================
# Métricas do topo
# =============================================================================
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")
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

# =============================================================================
# Google Sheets - leitura (tabela editável do planejamento)
# =============================================================================
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

# RLS por UO (não-admin)
if not is_admin:
    data = data[
        pd.to_numeric(data["uo_cod"], errors="coerce").fillna(-1).astype(int)
        == int(working_uo)
    ].copy()

# -----------------------------------------------------------------------------
# Filtros (para a tabela editável)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Salvar no Google Sheets
# -----------------------------------------------------------------------------
if st.button("💾 Salvar alterações no Google Sheets", type="primary"):
    is_valid, msg, edited_df = validate_new_rows(
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

# =============================================================================
# Seção: Execução orçamentária do exercício (detalhe)
# =============================================================================
st.divider()
st.subheader("Execução orçamentária do exercício (detalhe)")

# ---- Caminhos das bases (dpm install coloca aqui) ---------------------------
PATH_EXEC = "datapackages/siafi-2026/data/execucao.csv.gz"
PATH_UO = "datapackages/aux-classificadores/data/uo.csv"
PATH_ACAO = "datapackages/aux-classificadores/data/acao.csv"
PATH_ELI = "datapackages/aux-classificadores/data/elemento_item.csv"

# ---- Colunas finais disponíveis --------------------------------------------
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

# ---- Carregamento com cache -------------------------------------------------
@lru_cache(maxsize=2)
def _load_execucao_raw() -> pd.DataFrame:
    return pd.read_csv(PATH_EXEC, compression="gzip", low_memory=False)

@lru_cache(maxsize=4)
def _load_dim_uo() -> pd.DataFrame:
    uo = pd.read_csv(PATH_UO, low_memory=False)
    return uo[["ano", "uo_cod", "uo_sigla"]].drop_duplicates()

@lru_cache(maxsize=4)
def _load_dim_acao() -> pd.DataFrame:
    ac = pd.read_csv(PATH_ACAO, low_memory=False)
    return ac[["ano", "acao_cod", "acao_desc"]].drop_duplicates()

@lru_cache(maxsize=4)
def _load_dim_elemento_item() -> pd.DataFrame:
    eli = pd.read_csv(PATH_ELI, low_memory=False)
    return eli[["ano", "elemento_item_cod", "elemento_item_desc"]].drop_duplicates()

def _apply_global_filter(df: pd.DataFrame) -> pd.DataFrame:
    """(fonte = 89 OU ipu = 0) e uo_cod != 1261 (exclui SEE)."""
    for c in ("fonte_cod", "ipu_cod", "uo_cod"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.loc[
        ((df["fonte_cod"] == 89) | (df["ipu_cod"] == 0)) & (df["uo_cod"] != 1261)
    ].copy()

def load_execucao_view(restrict_uo: int | None = None) -> pd.DataFrame:
    """
    Retorna visão de execução com dimensões (UO, Ação, Elemento Item) e filtro global aplicado.
    Se `restrict_uo` informado, restringe também àquela UO (RLS de não-admin).
    """
    df = _load_execucao_raw()
    df = _apply_global_filter(df)

    # RLS adicional
    if restrict_uo is not None:
        df = df.loc[pd.to_numeric(df["uo_cod"], errors="coerce") == int(restrict_uo)].copy()

    # JOINs
    df = df.merge(_load_dim_uo(), on=["ano", "uo_cod"], how="left")
    df = df.merge(_load_dim_acao(), on=["ano", "acao_cod"], how="left")
    df = df.merge(_load_dim_elemento_item(), on=["ano", "elemento_item_cod"], how="left")

    keep = [c for c in EXEC_VIEW_COLS if c in df.columns]
    out = df[keep].copy()

    # Numéricos
    for col in ["vlr_empenhado", "vlr_liquidado", "vlr_liquidado_retido", "vlr_pago_orcamentario"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    # Inteiros que podem vir float
    int_cols = [
        "mes_cod", "uo_cod", "acao_cod", "grupo_cod", "fonte_cod",
        "ipu_cod", "elemento_item_cod", "num_contrato_saida", "num_obra", "num_empenho"
    ]
    for col in int_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")

    return out

# -----------------------------------------------------------------------------
# (1) Filtros de linhas (opcional) - recorte do dataset base
# -----------------------------------------------------------------------------
restrict_uo = None if is_admin else int(working_uo)
exec_df = load_execucao_view(restrict_uo=restrict_uo)

with st.expander("Filtros de linhas (opcional)"):
    col1, col2, col3 = st.columns(3)

    with col1:
        anos = sorted(exec_df["ano"].dropna().unique().tolist())
        ano_sel = st.multiselect("Ano", anos, default=anos)

        meses = sorted(exec_df["mes_cod"].dropna().unique().tolist())
        mes_sel = st.multiselect("Mês (cód.)", meses, default=meses)

        grupos = sorted(exec_df["grupo_cod"].dropna().unique().tolist())
        grupo_sel = st.multiselect("Grupo Despesa (cód.)", grupos, default=grupos)

    with col2:
        uo_cod_vals = sorted(exec_df["uo_cod"].dropna().unique().tolist())
        uo_cod_sel = st.multiselect("UO (cód.)", uo_cod_vals, default=uo_cod_vals)

        uos = sorted(exec_df["uo_sigla"].dropna().unique().tolist())
        uo_sigla_sel = st.multiselect("UO (sigla)", uos, default=uos)

        acoes = sorted(exec_df["acao_desc"].dropna().unique().tolist())
        acao_sel = st.multiselect("Ação (descrição)", acoes, default=acoes)

    with col3:
        fontes = sorted(exec_df["fonte_cod"].dropna().unique().tolist())
        fonte_sel = st.multiselect("Fonte (cód.)", fontes, default=fontes)

        ipus = sorted(exec_df["ipu_cod"].dropna().unique().tolist())
        ipu_sel = st.multiselect("IPU (cód.)", ipus, default=ipus)

        elis = sorted(exec_df["elemento_item_desc"].dropna().unique().tolist())
        eli_sel = st.multiselect("Elemento item (descrição)", elis, default=elis)

        cnpj_cpfs = st.text_input("CNPJ/CPF (contém)").strip()
        num_contrato = st.text_input("Nº contrato saída (contém)").strip()
        num_obra = st.text_input("Nº obra (contém)").strip()
        num_empenho = st.text_input("Nº empenho (contém)").strip()

# Aplica filtros de linhas (opcionais)
mask = (
    exec_df["ano"].isin(ano_sel)
    & exec_df["mes_cod"].isin(mes_sel)
    & exec_df["uo_cod"].isin(uo_cod_sel)
    & exec_df["uo_sigla"].isin(uo_sigla_sel)
    & exec_df["acao_desc"].isin(acao_sel)
    & exec_df["grupo_cod"].isin(grupo_sel)
    & exec_df["fonte_cod"].isin(fonte_sel)
    & exec_df["ipu_cod"].isin(ipu_sel)
    & exec_df["elemento_item_desc"].isin(eli_sel)
)
df_base = exec_df.loc[mask].copy()

def _contains(series: pd.Series, token: str) -> pd.Series:
    if not token:
        return pd.Series([True] * len(series), index=series.index)
    return series.astype(str).str.contains(token, case=False, na=False)

# Filtros textuais (opcionais)
if "cnpj_cpf_formatado" in df_base.columns:
    df_base = df_base[_contains(df_base["cnpj_cpf_formatado"], cnpj_cpfs)]
for col, token in [
    ("num_contrato_saida", num_contrato),
    ("num_obra", num_obra),
    ("num_empenho", num_empenho),
]:
    if col in df_base.columns:
        df_base = df_base[_contains(df_base[col], token)]

st.caption(
    "Filtro global aplicado: **(fonte = 89 OU ipu = 0) e uo_cod ≠ 1261 (exclui SEE)** · "
    + ("visão de todas as UOs" if is_admin else f"UO de trabalho: {working_uo}")
)

# -----------------------------------------------------------------------------
# (2) Tabela dinâmica - seleção de variáveis (Dimensões/Medidas)
# -----------------------------------------------------------------------------
st.subheader("Tabela dinâmica (seleção de variáveis)")

# Dicionários 'rótulo -> coluna' (dimensões e medidas)
# Dicionários 'rótulo -> coluna' (dimensões e medidas) — ATUALIZADOS
DIM_OPTIONS = {
    # Fato (execucao.csv.gz)
    "Ano": "ano",
    "Mês (cód.)": "mes_cod",
    "UO (cód.)": "uo_cod",
    "Ação (cód.)": "acao_cod",
    "Grupo Despesa (cód.)": "grupo_cod",
    "Fonte (cód.)": "fonte_cod",
    "IPU (cód.)": "ipu_cod",
    "Elemento item (cód.)": "elemento_item_cod",
    "CNPJ/CPF (formatado)": "cnpj_cpf_formatado",
    "Nº contrato saída": "num_contrato_saida",
    "Nº obra": "num_obra",
    "Nº empenho": "num_empenho",

    # Dimensões (aux-classificadores) já trazidas via JOIN
    "UO (sigla)": "uo_sigla",
    "Ação (descr.)": "acao_desc",
    "Elemento item (descr.)": "elemento_item_desc",
}

MEASURE_OPTIONS = {
    # Somatórios (medidas)
    "Empenhado": "vlr_empenhado",
    "Liquidado": "vlr_liquidado",
    "Pago Orçamentário": "vlr_pago_orcamentario",
}

with st.expander("Selecionar colunas da tabela"):
    c_dim, c_mea, c_opts = st.columns([1, 1, 1])

    with c_dim:
        dims_labels = st.multiselect(
            "Dimensões (colunas de agrupamento)",
            options=list(DIM_OPTIONS.keys()),
            default=["Ano", "UO (sigla)"],
        )

    with c_mea:
        meas_labels = st.multiselect(
            "Medidas (somatório)",
            options=list(MEASURE_OPTIONS.keys()),
            default=["Liquidado"],
            help="As medidas serão somadas dentro de cada combinação de dimensões.",
        )

    with c_opts:
        use_brl_format = st.checkbox(
            "Exibir medidas em BRL (R$ 1.234,56)", value=True
        )
        order_cols = dims_labels + meas_labels
        order_by = st.selectbox(
            "Ordenar por",
            options=["(nenhum)"] + order_cols,
            index=0,
        )
        order_asc = st.toggle("Ordem crescente", value=False)

# Monta a tabela dinâmica a partir do df_base (já filtrado)
sel_dims = [DIM_OPTIONS[lbl] for lbl in dims_labels]
sel_meas = [MEASURE_OPTIONS[lbl] for lbl in meas_labels]

if not sel_dims and not sel_meas:
    st.info("Selecione **pelo menos uma Dimensão** ou **uma Medida** para gerar a tabela.")
else:
    # Agrega conforme seleção
    if sel_dims and sel_meas:
        agg_df = (
            df_base.groupby(sel_dims, dropna=False)[sel_meas]
            .sum(numeric_only=True)
            .reset_index()
        )
    elif sel_dims and not sel_meas:
        # Só dimensões: combinações únicas
        agg_df = df_base[sel_dims].drop_duplicates().reset_index(drop=True)
    else:  # só medidas (sem dimensões): total geral
        tot = {m: float(pd.to_numeric(df_base[m], errors="coerce").sum()) for m in sel_meas}
        agg_df = pd.DataFrame([tot])

    # Renomeia para rótulos amigáveis
    rename_map = {**{v: k for k, v in DIM_OPTIONS.items()}, **{v: k for k, v in MEASURE_OPTIONS.items()}}
    agg_df = agg_df.rename(columns=rename_map)

    # Ordenação (se houver)
    if order_by and order_by != "(nenhum)" and order_by in agg_df.columns:
        agg_df = agg_df.sort_values(by=order_by, ascending=order_asc, kind="mergesort")

    # Formatação BRL (apenas na visualização)
    def _format_brl(x: float) -> str:
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    display_df = agg_df.copy()
    if use_brl_format:
        for lbl in meas_labels:
            if lbl in display_df.columns:
                display_df[lbl] = (
                    pd.to_numeric(display_df[lbl], errors="coerce")
                    .fillna(0.0)
                    .map(_format_brl)
                )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Baixar CSV (tabela dinâmica)",
        data=agg_df.to_csv(index=False).encode("utf-8"),
        file_name="tabela_dinamica_execucao.csv",
        mime="text/csv",
    )