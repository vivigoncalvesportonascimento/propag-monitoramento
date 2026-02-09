# app.py
# -*- coding: utf-8 -*-
"""
Propag - Monitoramento do Plano de Aplicação de Investimentos

Este app:
- Autentica usuários (streamlit-authenticator) e aplica RBAC por UO.
- Lê/atualiza dados de planejamento via Google Sheets.
- Mostra métricas do topo (limite do plano / liquidado / saldo).
- Tabela de cronograma (editável).
- Seção "Execução do exercício": Tabela dinâmica completa.

Regra global SEMPRE aplicada na Execução: (fonte = 89 OU ipu = 0) e uo_cod != 1261.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader

from streamlit_gsheets import GSheetsConnection
import streamlit_authenticator as stauth

# -- Imports do pacote local --
from my_pkg.transform.metrics import load_metrics
from my_pkg.transform.execucao_view import load_execucao_view
from my_pkg.transform.schema import (
    ALL_COLS, NUMERIC_COLS, BOOL_COLS, EDITABLE_COLS, REQUIRED_ON_NEW
)

# =============================================================================
# Config da página
# =============================================================================
st.set_page_config(
    page_title="Propag - Monitoramento",
    page_icon="📊",
    layout="wide",
)

# =============================================================================
# Utils
# =============================================================================
def brl(value: float) -> str:
    """Formata número como moeda pt-BR."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _to_plain_dict(obj):
    if isinstance(obj, Mapping):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(x) for x in obj]
    return obj

def load_rbac_from_secrets() -> dict[str, list]:
    raw = st.secrets.get("rbac", {})
    out: dict[str, list] = {}
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

<<<<<<< HEAD
def validate_new_rows(df_before, df_after, allowed_uos, is_admin, working_uo):
=======
def validate_new_rows(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    allowed_uos: list[int] | None,
    is_admin: bool,
    working_uo: int | None,
) -> tuple[bool, str, pd.DataFrame]:
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    before_idx = set(map(tuple, df_before[["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]].astype(str).values))
    after_idx = set(map(tuple, df_after[["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]].astype(str).values))
    new_keys = after_idx - before_idx

    is_new = df_after.apply(lambda r: (str(r["uo_cod"]), str(r["acao_cod"]), str(r["intervencao_cod"]), str(r["marcos_principais"])) in new_keys, axis=1)
    new_rows = df_after[is_new].copy()

    if not new_rows.empty:
        if (new_rows[REQUIRED_ON_NEW].isnull().any(axis=1).any() or (new_rows[REQUIRED_ON_NEW] == "").any(axis=1).any()):
            return False, "Necessário preencher todos os campos da linha nova.", df_after
        df_after.loc[is_new, "novo_marco"] = "Sim"

    if not is_admin:
        if df_after["uo_cod"].isnull().any():
            return False, "Há linhas sem UO definida.", df_after
        uos = set(pd.to_numeric(df_after["uo_cod"], errors="coerce").fillna(-1).astype(int).tolist())
        if allowed_uos is None or not uos.issubset(set(allowed_uos)):
            return False, "Você só pode visualizar/editar sua(s) UO(s) autorizada(s).", df_after
        if working_uo is not None and (uos - {working_uo}):
            return False, f"As linhas devem permanecer na UO {working_uo}.", df_after

    return True, "", df_after

# =============================================================================
# Autenticação
# =============================================================================
auth_cfg = _to_plain_dict(st.secrets.get("auth", {}))
credentials = _to_plain_dict(auth_cfg.get("credentials", {}))

if "usernames" not in credentials:
    st.error("Configuração de credenciais inválida.")
    st.stop()

auth = stauth.Authenticate(
    credentials=credentials,
    cookie_name=auth_cfg.get("cookie_name", "propag_monitoramento"),
    cookie_key=auth_cfg.get("cookie_key", "chave-secreta"),
    cookie_expiry_days=int(auth_cfg.get("cookie_expiry_days", 1)),
)

st.sidebar.title("Acesso")
login_result = auth.login(location="sidebar", fields={"Form name": "Entrar"})

if isinstance(login_result, tuple):
    name, auth_status, username = login_result
else:
    name = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

if not auth_status:
    if auth_status is False:
        st.sidebar.error("Credenciais inválidas.")
    st.stop()

auth.logout(button_name="Sair", location="sidebar", key="logout_sidebar")
st.sidebar.success(f"Olá, {name}!")

# RBAC
rbac_secrets = load_rbac_from_secrets()
rbac_yaml = load_access_yaml()
allowed_uos_list = rbac_secrets.get(username, [])
if not allowed_uos_list:
    allowed_uos_list = rbac_yaml.get(username, [])

is_admin = ("*" in allowed_uos_list)
allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

working_uo = None
if is_admin:
    st.sidebar.info("Perfil: **Admin**")
else:
    if not allowed_uos:
<<<<<<< HEAD
        st.error("Sem UO autorizada.")
        st.stop()
    working_uo = list(allowed_uos)[0] if len(allowed_uos) == 1 else st.sidebar.selectbox("UO de trabalho", sorted(allowed_uos))
    if len(allowed_uos) == 1: st.sidebar.info(f"UO: {working_uo}")
=======
        st.error("Conta sem UO autorizada.")
        st.stop()
    if len(allowed_uos) == 1:
        working_uo = list(allowed_uos)[0]
        st.sidebar.info(f"UO: {working_uo}")
    else:
        working_uo = st.sidebar.selectbox("UO de trabalho", sorted(allowed_uos))
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122

# =============================================================================
# Métricas do topo
# =============================================================================
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

st.title("Propag - Monitoramento de Investimentos")
c1, c2, c3 = st.columns(3)
<<<<<<< HEAD
with c1: st.metric("Total Plano", brl(vlr_plano))
with c2: st.metric("Total Liquidado", brl(vlr_liq))
=======
with c1: st.metric("Valor Total do Plano", brl(vlr_plano))
with c2: st.metric("Valor Total Liquidado", brl(vlr_liq))
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
with c3: st.metric("Saldo a Liquidar", brl(saldo))
st.divider()

# =============================================================================
# Google Sheets (Cronograma)
# =============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)
ss = st.secrets.get("connections", {}).get("gsheets", {})
<<<<<<< HEAD
spreadsheet = str(ss.get("spreadsheet", "") or st.sidebar.text_input("ID Planilha"))
worksheet = str(ss.get("worksheet", "Página1") or st.sidebar.text_input("Aba"))

if not spreadsheet:
    st.warning("Configure a planilha.")
else:
    try:
        data_raw = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=5)
        data = normalize_dataframe(data_raw)
        
        if not is_admin:
             data = data[pd.to_numeric(data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(working_uo)].copy()

        st.subheader("Filtros do cronograma")
        col_uo, col_acao, col_interv = st.columns([1, 1, 1])
        
        # Filtros
        with col_uo:
            uo_sel = st.selectbox("UO", ["Todas"] + sorted(data["uo_sigla"].dropna().unique().tolist())) if is_admin else "Sua UO"
        
        df_f = data.copy()
        if is_admin and uo_sel != "Todas":
            df_f = df_f[df_f["uo_sigla"] == uo_sel]

        with col_acao:
            acao_sel = st.selectbox("Ação", ["Todas"] + sorted(df_f["acao_desc"].dropna().unique().tolist()))
        with col_interv:
            interv_sel = st.selectbox("Intervenção", ["Todas"] + sorted(df_f["intervencao_desc"].dropna().unique().tolist()))

        if acao_sel == "Todas" and interv_sel == "Todas":
            st.info("Selecione Intervenção ou Ação para editar.")
        else:
            df_edit = df_f.copy()
            if acao_sel != "Todas": df_edit = df_edit[df_edit["acao_desc"] == acao_sel]
            if interv_sel != "Todas": df_edit = df_edit[df_edit["intervencao_desc"] == interv_sel]
            
            st.divider()
            
            # Configuração do Editor
            column_config = {
                "valor_previsto_total": st.column_config.TextColumn(disabled=True),
                "novo_marco": st.column_config.SelectboxColumn("Novo Marco?", options=["Sim", "Não"], default="Sim", required=True),
                "acao_cod": st.column_config.NumberColumn(disabled=False),
                "uo_cod": st.column_config.NumberColumn(disabled=not is_admin),
            }
            if not is_admin and "uo_cod" in df_edit.columns:
                df_edit["uo_cod"] = int(working_uo)

            edited_df = st.data_editor(
                df_edit, num_rows="dynamic", use_container_width=True,
                column_config=column_config, 
                disabled=[c for c in ALL_COLS if (c not in EDITABLE_COLS and c != "novo_marco")],
                key="editor_cronograma"
            )

            if st.button("💾 Salvar no Google Sheets", type="primary"):
                is_valid, msg, edited_df = validate_new_rows(df_edit, edited_df, list(allowed_uos) if allowed_uos else None, is_admin, working_uo)
                if not is_valid:
                    st.error(msg)
                else:
                    try:
                        mask_drop = data_raw.index.isin(df_edit.index)
                        final_df = pd.concat([data_raw[~mask_drop], edited_df], ignore_index=True)[ALL_COLS]
                        conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=final_df)
                        st.success("Salvo!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
    except Exception as e:
        st.error(f"Erro Sheets: {e}")

# =============================================================================
# Execução Orçamentária (Tabela Dinâmica)
# =============================================================================
st.divider()
st.subheader("Execução Orçamentária (Tabela Dinâmica)")

restrict_uo_exec = None if is_admin else int(working_uo)
with st.spinner("Carregando e cruzando dados de execução..."):
    df_base = load_execucao_view(restrict_uo=restrict_uo_exec)

st.caption("Filtro global: (fonte=89 ou ipu=0) e uo_cod!=1261")

# Opções incluindo as descrições que agora funcionam
=======
spreadsheet = ss.get("spreadsheet")
worksheet = ss.get("worksheet", "Página1")

with st.sidebar:
    st.header("Dados (Google Sheets)")
    spreadsheet = st.text_input("URL/ID da Planilha", value=str(spreadsheet or ""))
    worksheet = st.text_input("Aba (worksheet)", value=str(worksheet or "Página1"))

if not spreadsheet:
    st.error("❌ Configure a URL da planilha.")
    st.stop()

try:
    data_raw = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=5)
except Exception as e:
    st.error(f"Erro no Google Sheets: {e}")
    st.stop()

data = normalize_dataframe(data_raw)
if not is_admin:
    data = data[pd.to_numeric(data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(working_uo)].copy()

# Filtros do Cronograma
st.subheader("Filtros do cronograma")
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

show_editor = not (acao_sel == "Todas" and interv_sel == "Todas")

if not show_editor:
    st.info("🧭 Selecione **Intervenção** OU **Ação Orçamentária** para editar o cronograma.")
else:
    if interv_sel != "Todas":
        st.markdown(f"### Intervenção Selecionada: **{interv_sel}**")
    
    df_edit = df_f.copy()
    if acao_sel != "Todas": df_edit = df_edit[df_edit["acao_desc"] == acao_sel]
    if interv_sel != "Todas": df_edit = df_edit[df_edit["intervencao_desc"] == interv_sel]

    st.divider()
    st.subheader("Dados para Preenchimento")
    
    disabled_cols = [c for c in ALL_COLS if (c not in EDITABLE_COLS and c != "novo_marco")]
    column_config = {
        "valor_previsto_total": st.column_config.TextColumn(disabled=True),
        "novo_marco": st.column_config.SelectboxColumn("Novo Marco?", options=["Sim", "Não"], default="Sim", required=True),
        "acao_cod": st.column_config.NumberColumn(disabled=False),
        "uo_cod": st.column_config.NumberColumn(disabled=False) if is_admin else st.column_config.NumberColumn(disabled=True),
    }

    if not is_admin and "uo_cod" in df_edit.columns:
        df_edit["uo_cod"] = int(working_uo)

    df_edit["novo_marco"] = df_edit["novo_marco"].fillna("Não").astype(str)

    edited_df = st.data_editor(
        df_edit, num_rows="dynamic", use_container_width=True,
        column_config=column_config, disabled=disabled_cols, key="editor_principal",
    )

    if st.button("💾 Salvar alterações no Google Sheets", type="primary"):
        is_valid, msg, edited_df = validate_new_rows(df_edit, edited_df, list(allowed_uos) if allowed_uos else None, is_admin, None if is_admin else int(working_uo))
        if not is_valid:
            st.error(f"❌ {msg}")
        else:
            mask_to_drop = data_raw.index.isin(df_edit.index)
            data_sem = data_raw.drop(index=data_raw.index[mask_to_drop])
            final_df = pd.concat([data_sem, edited_df], ignore_index=True)[ALL_COLS]
            try:
                conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=final_df)
                st.success("✅ Atualizado com sucesso!")
                time.sleep(1.2)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# =============================================================================
# Execução Orçamentária (Tabela Dinâmica Completa)
# =============================================================================
st.divider()
st.subheader("Execução orçamentária do exercício (Tabela Dinâmica)")

# 1. Carrega os dados "Wide" (todas as colunas disponíveis, já filtradas e com joins)
restrict_uo_exec = None if is_admin else int(working_uo)
with st.spinner("Carregando base de execução..."):
    df_base = load_execucao_view(restrict_uo=restrict_uo_exec)

st.caption(
    "Filtro global aplicado: **(fonte = 89 OU ipu = 0) e uo_cod ≠ 1261** · "
    + ("Visão Admin" if is_admin else f"UO: {working_uo}")
)

# 2. Definição do Menu Dinâmico (Mapeamento Nome -> Coluna)
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
DIM_OPTIONS = {
    "Ano": "ano",
    "UO (cód.)": "uo_cod",
    "UO (sigla)": "uo_sigla",             # <--- Agora deve vir preenchido
    "Ação (cód.)": "acao_cod",
<<<<<<< HEAD
    "Ação (descrição)": "acao_desc",      # <--- Agora deve vir preenchido
    "Elemento (cód.)": "elemento_item_cod",
    "Elemento (descr.)": "elemento_item_desc", # <--- Agora deve vir preenchido
    "Grupo Despesa": "grupo_cod",
    "Fonte": "fonte_cod",
    "IPU": "ipu_cod",
    "Credor": "cnpj_cpf_formatado",
    "Nº Contrato": "num_contrato_saida",
=======
    "Ação (descrição)": "acao_desc",
    "Grupo de Despesa (cód.)": "grupo_cod",
    "Fonte (cód.)": "fonte_cod",
    "IPU (cód.)": "ipu_cod",
    "Elemento de Item (cód.)": "elemento_item_cod",
    "Elemento de Item (descrição)": "elemento_item_desc",
    "CNPJ/CPF Credor": "cnpj_cpf_formatado",
    "Nº Contrato Saída": "num_contrato_saida",
    "Nº Obra": "num_obra",
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
    "Nº Empenho": "num_empenho"
}

MEASURE_OPTIONS = {
<<<<<<< HEAD
    "Empenhado": "vlr_empenhado",
    "Liquidado": "vlr_liquidado",
    "Pago": "vlr_pago_orcamentario"
}

with st.expander("Montar Tabela", expanded=True):
    c_dim, c_mea = st.columns(2)
    with c_dim:
        dims_labels = st.multiselect("Agrupar por:", options=list(DIM_OPTIONS.keys()), default=["Ano", "UO (sigla)"])
    with c_mea:
        meas_labels = st.multiselect("Somar métricas:", options=list(MEASURE_OPTIONS.keys()), default=["Liquidado"])
    
    c_opt1, c_opt2 = st.columns(2)
    with c_opt1: use_brl = st.toggle("Moeda (R$)", value=True)
    with c_opt2: remove_zero = st.toggle("Ocultar zerados", value=False)

if not meas_labels:
    st.warning("Selecione uma métrica.")
=======
    "Valor Empenhado": "vlr_empenhado",
    "Valor Liquidado": "vlr_liquidado",
    "Valor Pago Orçamentário": "vlr_pago_orcamentario"
}

# 3. Interface de Seleção
with st.expander("Montar Tabela (Selecione Variáveis)", expanded=True):
    c_dim, c_mea = st.columns(2)
    with c_dim:
        st.markdown("##### 1. Agrupar por (Linhas):")
        dims_labels = st.multiselect(
            "Selecione as dimensões:",
            options=list(DIM_OPTIONS.keys()),
            default=["Ano", "UO (sigla)"],
            placeholder="Ex: Ano, Ação, Fonte..."
        )
    with c_mea:
        st.markdown("##### 2. Somar os valores (Métricas):")
        meas_labels = st.multiselect(
            "Selecione os valores:",
            options=list(MEASURE_OPTIONS.keys()),
            default=["Valor Liquidado"],
            placeholder="Ex: Valor Liquidado"
        )
    
    c_opt1, c_opt2 = st.columns(2)
    with c_opt1: use_brl = st.toggle("Formatar R$", value=True)
    with c_opt2: remove_zero = st.toggle("Ocultar zerados", value=False) # <--- Alterado para False

# 4. Lógica de Processamento (Pivot/Groupby)
if not meas_labels:
    st.warning("⚠️ Selecione pelo menos uma métrica.")
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
else:
    sel_dims = [DIM_OPTIONS[l] for l in dims_labels]
    sel_meas = [MEASURE_OPTIONS[l] for l in meas_labels]

<<<<<<< HEAD
    if not sel_dims:
        agg_df = pd.DataFrame(df_base[sel_meas].sum()).T
    else:
        agg_df = df_base.groupby(sel_dims, dropna=False)[sel_meas].sum().reset_index()

    if remove_zero:
        agg_df = agg_df.loc[agg_df[sel_meas].sum(axis=1) != 0]

    if sel_dims:
        agg_df = agg_df.sort_values(by=sel_dims)

    display_df = agg_df.rename(columns={**{v: k for k, v in DIM_OPTIONS.items()}, **{v: k for k, v in MEASURE_OPTIONS.items()}})

    if use_brl:
        for lbl in meas_labels:
            if lbl in display_df.columns:
                display_df[lbl] = display_df[lbl].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={"Ano": st.column_config.NumberColumn(format="%d")})
    
    st.download_button("Baixar CSV", data=agg_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), file_name="tabela_dinamica.csv", mime="text/csv")
=======
    # Agrupa e soma
    if not sel_dims:
        # Total geral (sem dimensão)
        agg_df = pd.DataFrame(df_base[sel_meas].sum()).T
    else:
        # Agrupamento dinâmico
        agg_df = df_base.groupby(sel_dims, dropna=False)[sel_meas].sum().reset_index()

    # Filtro de linhas zeradas
    if remove_zero:
        agg_df = agg_df.loc[agg_df[sel_meas].sum(axis=1) != 0]

    # Ordenação
    if sel_dims:
        agg_df = agg_df.sort_values(by=sel_dims)

    # Preparação Visual (Renomear e Formatar)
    display_df = agg_df.copy()
    
    # Renomeia colunas técnicas para nomes amigáveis
    rev_dims = {v: k for k, v in DIM_OPTIONS.items()}
    rev_meas = {v: k for k, v in MEASURE_OPTIONS.items()}
    display_df = display_df.rename(columns={**rev_dims, **rev_meas})

    # Formatação (apenas visual)
    if use_brl:
        for lbl in meas_labels:
            if lbl in display_df.columns:
                display_df[lbl] = display_df[lbl].apply(
                    lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={"Ano": st.column_config.NumberColumn(format="%d")}
    )

    st.download_button(
        "⬇️ Baixar CSV",
        data=agg_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name="tabela_dinamica_execucao.csv",
        mime="text/csv"
    )
>>>>>>> 278114a4e8acbcf42424a16520405bcecc7d8122
