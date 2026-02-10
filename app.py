# app.py
# -*- coding: utf-8 -*-
"""
Propag - Monitoramento do Plano de Aplicação de Investimentos

Este app:
1. Autentica usuários.
2. Layout ajustado (Sidebar retrátil, Login centralizado).
3. Correção Crítica:
   - Checkboxes funcionais nas colunas "_planejado".
   - Formatação BRL (R$ 1.000,00) nas colunas de valor.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
import re

import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader

from streamlit_gsheets import GSheetsConnection
import streamlit_authenticator as stauth

# -- Imports dos módulos locais --
# (Mantendo o try/except para segurança)
try:
    from my_pkg.transform.metrics import load_metrics
    from my_pkg.transform.execucao_view import load_execucao_view
    from my_pkg.transform.rp_view import load_rp_view
    from my_pkg.transform.schema import (
        ALL_COLS, NUMERIC_COLS, BOOL_COLS, EDITABLE_COLS, REQUIRED_ON_NEW
    )
except ImportError:
    st.error("Erro: Módulos locais não encontrados.")
    st.stop()

# =============================================================================
# Configuração da Página
# =============================================================================
st.set_page_config(
    page_title="Propag - Monitoramento",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# CSS PERSONALIZADO (Layout Limpo)
# =============================================================================
st.markdown("""
    <style>
        .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 1rem !important;
            margin-top: 0rem !important;
        }
        h1 {
            font-size: 2.0rem !important; 
            margin-bottom: 0.2rem !important; 
            margin-top: -1.5rem !important;
            padding-top: 0rem !important;
        }
        hr {
            margin-top: 0.2rem !important;
            margin-bottom: 0.2rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# =============================================================================
# Funções Utilitárias
# =============================================================================


def brl(value: float) -> str:
    """Formata float para string de moeda BRL."""
    if pd.isna(value):
        return "R$ 0,00"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"


def format_brl_edit(value) -> str:
    """Converte valor numérico para texto formato BR (R$ 1.000,00) para o Editor."""
    if pd.isna(value) or value == "":
        return ""
    try:
        val = float(value)
        if val == 0:
            return "R$ 0,00"
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(value)


def parse_brl_edit(value_str) -> float:
    """Converte string formato BR (R$ 1.000,00) de volta para float."""
    if isinstance(value_str, (int, float)):
        return float(value_str)
    if pd.isna(value_str) or str(value_str).strip() == "":
        return 0.0

    clean_str = str(value_str).replace("R$", "").replace(
        " ", "").replace(".", "").replace(",", ".")
    try:
        return float(clean_str)
    except ValueError:
        return 0.0


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
    """
    Normaliza dados brutos.
    AGRESSIVIDADE NOS BOOLEANOS: Garante que colunas de Checkbox sejam bool puro.
    """
    data = df.copy()

    # 1. Garante todas as colunas
    for c in ALL_COLS:
        if c not in data.columns:
            data[c] = None

    # 2. Tratamento Numérico
    for col in NUMERIC_COLS:
        if col in data.columns:
            if data[col].dtype == object:
                data[col] = data[col].astype(str).str.replace(
                    r"[R$\.\s]", "", regex=True).str.replace(",", ".")
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

    # 3. Tratamento Booleano (CRÍTICO PARA O CHECKBOX FUNCIONAR)
    planejado_cols = [f"{i}_bimestre_planejado" for i in range(1, 7)]
    target_bool_cols = set(BOOL_COLS) | set(planejado_cols)

    # Lista de valores que viram TRUE (ignorando maiúsculas/minúsculas)
    TRUE_VALUES = ["TRUE", "1", "SIM", "S",
                   "YES", "VERDADEIRO", "X", "OK", "V"]

    for col in target_bool_cols:
        if col in data.columns:
            # Converte tudo para string, limpa espaços, joga pra maiúsculo
            # e verifica se está na lista de 'Verdadeiros'
            data[col] = data[col].astype(
                str).str.strip().str.upper().isin(TRUE_VALUES)

            # Força o tipo 'bool' do Python/Pandas
            data[col] = data[col].astype(bool)

    return data[ALL_COLS]


def validate_new_rows(df_before, df_after, allowed_uos, is_admin, working_uo):
    cols_key = ["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]
    before_idx = set(map(tuple, df_before[cols_key].astype(str).values))
    after_idx = set(map(tuple, df_after[cols_key].astype(str).values))
    new_keys = after_idx - before_idx

    is_new = df_after.apply(lambda r: tuple(
        r[cols_key].astype(str)) in new_keys, axis=1)
    new_rows = df_after[is_new].copy()

    if not new_rows.empty:
        if (new_rows[REQUIRED_ON_NEW].isnull().any(axis=1).any() or (new_rows[REQUIRED_ON_NEW] == "").any(axis=1).any()):
            return False, "Preencha todos os campos obrigatórios na nova linha.", df_after
        # Nova linha já nasce marcada como Novo Marco (bool)
        df_after.loc[is_new, "novo_marco"] = True

    if not is_admin:
        if df_after["uo_cod"].isnull().any():
            return False, "Existem linhas sem UO definida.", df_after
        uos_present = set(pd.to_numeric(
            df_after["uo_cod"], errors="coerce").fillna(-1).astype(int).tolist())
        if allowed_uos is None or not uos_present.issubset(set(allowed_uos)):
            return False, "Você inseriu uma UO não autorizada.", df_after
        if working_uo is not None and (uos_present - {working_uo}):
            return False, f"As linhas devem pertencer à UO {working_uo}.", df_after

    return True, "", df_after


# =============================================================================
# Autenticação
# =============================================================================
auth_cfg = _to_plain_dict(st.secrets.get("auth", {}))
credentials = _to_plain_dict(auth_cfg.get("credentials", {}))

if "usernames" not in credentials:
    st.error("Erro na configuração de credenciais (secrets).")
    st.stop()

auth = stauth.Authenticate(
    credentials=credentials,
    cookie_name=auth_cfg.get("cookie_name", "propag_monitoramento"),
    cookie_key=auth_cfg.get("cookie_key", "chave_secreta_padrao"),
    cookie_expiry_days=int(auth_cfg.get("cookie_expiry_days", 1)),
)

# --- LOGIN ---
col_esq, col_centro, col_dir = st.columns([3, 2, 3])
with col_centro:
    login_result = auth.login(location="main", fields={"Form name": "Login"})

if isinstance(login_result, tuple):
    name, auth_status, username = login_result
else:
    name = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

if not auth_status:
    if auth_status is False:
        with col_centro:
            st.error("Usuário ou senha incorretos.")
    st.stop()

# =============================================================================
# LOGADO - Principal
# =============================================================================

with st.sidebar:
    st.header("Perfil")
    st.success(f"Olá, **{name}**")
    auth.logout(button_name="Sair", location="sidebar", key="logout_sidebar")
    st.divider()

rbac_secrets = load_rbac_from_secrets()
rbac_yaml = load_access_yaml()
allowed_uos_list = rbac_secrets.get(username, [])
if not allowed_uos_list:
    allowed_uos_list = rbac_yaml.get(username, [])

is_admin = ("*" in allowed_uos_list)
allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

working_uo = None
if is_admin:
    st.sidebar.info("Nível: **Administrador**")
else:
    if not allowed_uos:
        st.error("Seu usuário não possui UOs vinculadas.")
        st.stop()
    if len(allowed_uos) > 1:
        working_uo = st.sidebar.selectbox(
            "Selecionar UO de Trabalho", sorted(allowed_uos))
    else:
        working_uo = list(allowed_uos)[0]
        st.sidebar.info(f"UO Vinculada: {working_uo}")

# =============================================================================
# 1. Métricas
# =============================================================================
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

st.title("Propag - Monitoramento de Investimentos")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Valor Total do Plano", brl(vlr_plano))
with col2:
    st.metric("Valor Total Liquidado", brl(vlr_liq))
with col3:
    st.metric("Saldo a Liquidar", brl(saldo))

st.divider()

# =============================================================================
# 2. Cronograma Físico
# =============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)
ss_cfg = st.secrets.get("connections", {}).get("gsheets", {})
spreadsheet = str(ss_cfg.get("spreadsheet", "")
                  or st.sidebar.text_input("ID Planilha Google"))
worksheet = str(ss_cfg.get("worksheet", "Página1"))

if not spreadsheet:
    st.warning("⚠️ Planilha não configurada nos secrets.")
else:
    try:
        data_raw = conn.read(spreadsheet=spreadsheet,
                             worksheet=worksheet, ttl=5)
        # Normalização rigorosa para Checkboxes
        data = normalize_dataframe(data_raw)

        if not is_admin:
            data = data[pd.to_numeric(
                data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(working_uo)].copy()

        st.subheader("Cronograma de Intervenções")

        # Filtros
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1:
            lista_uos = ["Todas"] + \
                sorted(data["uo_sigla"].dropna().unique().tolist())
            uo_sel = st.selectbox("Filtrar UO", lista_uos)

        df_view = data.copy()
        if uo_sel != "Todas":
            df_view = df_view[df_view["uo_sigla"] == uo_sel]

        with c_f2:
            lista_acoes = ["Todas"] + \
                sorted(df_view["acao_desc"].dropna().unique().tolist())
            acao_sel = st.selectbox("Filtrar Ação", lista_acoes)
        with c_f3:
            lista_interv = [
                "Todas"] + sorted(df_view["intervencao_desc"].dropna().unique().tolist())
            interv_sel = st.selectbox("Filtrar Intervenção", lista_interv)

        # Prepara colunas monetárias para edição (Float -> Texto BR)
        money_cols = ["valor_previsto_total", "valor_replanejado_total"]
        for i in range(1, 7):
            money_cols.append(f"{i}_bimestre_replanejado")
            money_cols.append(f"{i}_bimestre_realizado")

        df_display_edit = df_view.copy()
        for col in money_cols:
            if col in df_display_edit.columns:
                df_display_edit[col] = df_display_edit[col].apply(
                    format_brl_edit)

        # --- CONFIGURAÇÃO DE COLUNAS ---
        base_column_config = {
            "uo_cod": st.column_config.NumberColumn("UO", format="%d"),
            "uo_sigla": st.column_config.TextColumn("UO Sigla"),
            "acao_cod": st.column_config.NumberColumn("Ação", format="%d"),
            "acao_desc": st.column_config.TextColumn("Ação Desc."),
            "intervencao_cod": None,  # Oculto
            "intervencao_desc": st.column_config.TextColumn("Intervenção"),
            "marcos_principais": st.column_config.TextColumn("Marcos Principais"),
            "novo_marco": st.column_config.CheckboxColumn("Novo Marco?", default=False),
            "valor_previsto_total": st.column_config.TextColumn("Valor Plano Total", disabled=True),
            "valor_replanejado_total": st.column_config.TextColumn("Valor Plano Replanejado"),
        }

        for i in range(1, 7):
            # Planejado -> Checkbox
            base_column_config[f"{i}_bimestre_planejado"] = st.column_config.CheckboxColumn(
                f"{i}ºb Plano",
                default=False
            )
            # Replanejado/Realizado -> Texto BR
            base_column_config[f"{i}_bimestre_replanejado"] = st.column_config.TextColumn(
                f"{i}ºb Replanejado")
            base_column_config[f"{i}_bimestre_realizado"] = st.column_config.TextColumn(
                f"{i}ºb Realizado")

        # --- RENDERIZAÇÃO ---
        if acao_sel == "Todas" and interv_sel == "Todas":
            st.info("ℹ️ Selecione uma **Intervenção** ou **Ação** para editar.")
            st.dataframe(
                df_display_edit,
                use_container_width=True,
                hide_index=True,
                column_config=base_column_config
            )
        else:
            df_edit = df_display_edit.copy()
            if acao_sel != "Todas":
                df_edit = df_edit[df_edit["acao_desc"] == acao_sel]
            if interv_sel != "Todas":
                df_edit = df_edit[df_edit["intervencao_desc"] == interv_sel]

            st.caption("Modo de Edição Ativo")

            edit_column_config = base_column_config.copy()
            edit_column_config["uo_cod"] = st.column_config.NumberColumn(
                "UO", disabled=not is_admin, format="%d")

            if not is_admin and "uo_cod" in df_edit.columns:
                df_edit["uo_cod"] = int(working_uo)

            cols_disabled = [c for c in ALL_COLS if (
                c not in EDITABLE_COLS and c != "novo_marco")]

            edited_df = st.data_editor(
                df_edit,
                num_rows="dynamic",
                use_container_width=True,
                column_config=edit_column_config,
                disabled=cols_disabled,
                key="editor_cronograma"
            )

            if st.button("💾 Salvar Alterações", type="primary"):
                # Conversão inversa (Texto BR -> Float)
                df_to_save = edited_df.copy()
                for col in money_cols:
                    if col in df_to_save.columns:
                        df_to_save[col] = df_to_save[col].apply(parse_brl_edit)

                df_before_save = df_edit.copy()
                for col in money_cols:
                    if col in df_before_save.columns:
                        df_before_save[col] = df_before_save[col].apply(
                            parse_brl_edit)

                is_valid, msg, validated_df = validate_new_rows(
                    df_before_save, df_to_save, allowed_uos, is_admin, working_uo)

                if not is_valid:
                    st.error(f"Erro: {msg}")
                else:
                    try:
                        mask_drop = data_raw.index.isin(df_edit.index)
                        final_df = pd.concat([data_raw[~mask_drop], validated_df], ignore_index=True)[
                            ALL_COLS]
                        conn.update(spreadsheet=spreadsheet,
                                    worksheet=worksheet, data=final_df)
                        st.toast("✅ Salvo com sucesso!", icon="💾")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no Google Sheets: {e}")

    except Exception as e:
        st.error(f"Erro ao conectar no Google Sheets: {e}")

st.divider()

# =============================================================================
# 3. Detalhamento Financeiro
# =============================================================================
st.subheader("Detalhamento Financeiro")

view_option = st.radio(
    "Selecione a base de dados para análise:",
    options=["Execução do Exercício (2026)", "Restos a Pagar (RP)"],
    horizontal=True,
    label_visibility="visible"
)

restrict_uo_db = None if is_admin else int(working_uo)

if view_option == "Execução do Exercício (2026)":
    st.markdown("---")
    st.markdown("#### 🟢 Tabela Dinâmica: Execução 2026")

    with st.spinner("Carregando dados de execução..."):
        df_exec = load_execucao_view(restrict_uo=restrict_uo_db)

    st.caption("Filtro aplicado: (Fonte 89 ou IPU 0) e UO ≠ 1261")

    DIM_OPTIONS_EXEC = {
        "Ano": "ano",
        "UO (cód.)": "uo_cod",
        "UO (sigla)": "uo_sigla",
        "Ação (cód.)": "acao_cod",
        "Ação (descrição)": "acao_desc",
        "Elemento (cód.)": "elemento_item_cod",
        "Elemento (descr.)": "elemento_item_desc",
        "Grupo Despesa": "grupo_cod",
        "Fonte": "fonte_cod",
        "IPU": "ipu_cod",
        "Credor": "cnpj_cpf_formatado",
        "Nº Contrato": "num_contrato_saida",
        "Nº Empenho": "num_empenho"
    }

    MEASURE_OPTIONS_EXEC = {
        "Empenhado": "vlr_empenhado",
        "Liquidado": "vlr_liquidado",
        "Pago": "vlr_pago_orcamentario"
    }

    with st.expander("🛠️ Configurar Tabela (Execução)", expanded=True):
        col_d, col_m = st.columns(2)
        with col_d:
            sel_dims_labels = st.multiselect(
                "Agrupar por (Linhas):",
                options=list(DIM_OPTIONS_EXEC.keys()),
                default=["Ano", "UO (sigla)"],
                key="multi_dims_exec"
            )
        with col_m:
            sel_meas_labels = st.multiselect(
                "Somar métricas (Colunas):",
                options=list(MEASURE_OPTIONS_EXEC.keys()),
                default=["Liquidado"],
                key="multi_meas_exec"
            )

        c_o1, c_o2 = st.columns(2)
        with c_o1:
            use_brl = st.toggle("Formatar Moeda (R$)",
                                value=True, key="toggle_brl_exec")
        with c_o2:
            remove_zero = st.toggle(
                "Ocultar linhas zeradas", value=False, key="toggle_zero_exec")

    if not sel_meas_labels:
        st.warning("Selecione ao menos uma métrica para visualizar.")
    else:
        sel_dims = [DIM_OPTIONS_EXEC[L] for L in sel_dims_labels]
        sel_meas = [MEASURE_OPTIONS_EXEC[L] for L in sel_meas_labels]

        if not sel_dims:
            agg_df = pd.DataFrame(df_exec[sel_meas].sum()).T
        else:
            agg_df = df_exec.groupby(sel_dims, dropna=False)[
                sel_meas].sum().reset_index()

        if remove_zero:
            agg_df = agg_df.loc[agg_df[sel_meas].sum(axis=1) != 0]

        if sel_dims:
            agg_df = agg_df.sort_values(by=sel_dims)

        display_df = agg_df.rename(columns={
            **{v: k for k, v in DIM_OPTIONS_EXEC.items()},
            **{v: k for k, v in MEASURE_OPTIONS_EXEC.items()}
        })

        if use_brl:
            for lbl in sel_meas_labels:
                if lbl in display_df.columns:
                    display_df[lbl] = display_df[lbl].apply(brl)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={"Ano": st.column_config.NumberColumn(format="%d")}
        )

        st.download_button(
            "⬇️ Baixar CSV (Execução)",
            data=agg_df.to_csv(index=False, sep=";",
                               decimal=",").encode("utf-8-sig"),
            file_name="execucao_2026.csv",
            mime="text/csv"
        )

else:
    st.markdown("---")
    st.markdown("#### 🟠 Tabela Dinâmica: Restos a Pagar (RP)")

    with st.spinner("Carregando Restos a Pagar..."):
        df_rp = load_rp_view(restrict_uo=restrict_uo_db)

    DIM_OPTIONS_RP = {
        "Ano Exercício": "ano",
        "Ano RP (Origem)": "ano_rp",
        "UO (cód.)": "uo_cod",
        "UO (sigla)": "uo_sigla",
        "Ação (cód.)": "acao_cod",
        "Ação (descrição)": "acao_desc",
        "Elemento (cód.)": "elemento_item_cod",
        "Elemento (descr.)": "elemento_item_desc",
        "Grupo Despesa": "grupo_cod",
        "Fonte": "fonte_cod",
        "IPU": "ipu_cod",
        "Nº Empenho": "num_empenho",
        "Nº Contrato": "num_contrato_saida",
        "Nº Obra": "num_obra",
        "Credor (CPF/CNPJ)": "cnpj_cpf_formatado",
        "Razão Social Credor": "razao_social_credor"
    }

    MEASURE_OPTIONS_RP = {
        "Inscrito (RPP)": "calc_inscrito_rpp",
        "Cancelado (RPP)": "calc_cancelado_rpp",
        "Pago (RPP)": "calc_pago_rpp",
        "Saldo (RPP)": "calc_saldo_rpp",
        "Inscrito (RPNP)": "calc_inscrito_rpnp",
        "Cancelado (RPNP)": "calc_cancelado_rpnp",
        "Liquidado (RPNP)": "calc_liquidado_rpnp",
        "Saldo (RPNP)": "calc_saldo_rpnp",
        "Pago (RPNP)": "calc_pago_rpnp"
    }

    with st.expander("🛠️ Configurar Tabela (RP)", expanded=True):
        c_rp_d, c_rp_m = st.columns(2)
        with c_rp_d:
            sel_dims_rp_labels = st.multiselect(
                "Agrupar por (Linhas):",
                options=list(DIM_OPTIONS_RP.keys()),
                default=["Ano RP (Origem)", "UO (sigla)"],
                key="multi_dims_rp"
            )
        with c_rp_m:
            sel_meas_rp_labels = st.multiselect(
                "Somar métricas (Colunas):",
                options=list(MEASURE_OPTIONS_RP.keys()),
                default=["Pago (RPP)", "Pago (RPNP)"],
                key="multi_meas_rp"
            )

        c_rp_o1, c_rp_o2 = st.columns(2)
        with c_rp_o1:
            use_brl_rp = st.toggle("Formatar Moeda (R$)",
                                   value=True, key="toggle_brl_rp")
        with c_rp_o2:
            remove_zero_rp = st.toggle(
                "Ocultar linhas zeradas", value=False, key="toggle_zero_rp")

    if not sel_meas_rp_labels:
        st.warning("Selecione ao menos uma métrica para visualizar.")
    else:
        sel_dims_rp = [DIM_OPTIONS_RP[L] for L in sel_dims_rp_labels]
        sel_meas_rp = [MEASURE_OPTIONS_RP[L] for L in sel_meas_rp_labels]

        if not sel_dims_rp:
            agg_df_rp = pd.DataFrame(df_rp[sel_meas_rp].sum()).T
        else:
            agg_df_rp = df_rp.groupby(sel_dims_rp, dropna=False)[
                sel_meas_rp].sum().reset_index()

        if remove_zero_rp:
            agg_df_rp = agg_df_rp.loc[agg_df_rp[sel_meas_rp].sum(axis=1) != 0]

        if sel_dims_rp:
            agg_df_rp = agg_df_rp.sort_values(by=sel_dims_rp)

        display_df_rp = agg_df_rp.rename(columns={
            **{v: k for k, v in DIM_OPTIONS_RP.items()},
            **{v: k for k, v in MEASURE_OPTIONS_RP.items()}
        })

        if use_brl_rp:
            for lbl in sel_meas_rp_labels:
                if lbl in display_df_rp.columns:
                    display_df_rp[lbl] = display_df_rp[lbl].apply(brl)

        st.dataframe(
            display_df_rp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ano Exercício": st.column_config.NumberColumn(format="%d"),
                "Ano RP (Origem)": st.column_config.NumberColumn(format="%d")
            }
        )

        st.download_button(
            "⬇️ Baixar CSV (Restos a Pagar)",
            data=agg_df_rp.to_csv(index=False, sep=";",
                                  decimal=",").encode("utf-8-sig"),
            file_name="restos_a_pagar.csv",
            mime="text/csv"
        )
