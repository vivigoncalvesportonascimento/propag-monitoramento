# app.py
# -*- coding: utf-8 -*-
"""
Propag - Monitoramento do Plano de Aplicação de Investimentos

Este app:
1. Autentica usuários (streamlit-authenticator) e aplica regras de acesso (RBAC).
2. Exibe métricas gerais do plano no topo (Sempre visível).
3. Exibe e permite edição do Cronograma Físico/Google Sheets (Sempre visível).
4. Possui um seletor para alternar a visão inferior entre:
   - Execução Orçamentária do Exercício (2026)
   - Restos a Pagar (RP)
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

# -- Imports dos módulos locais --
from my_pkg.transform.metrics import load_metrics
from my_pkg.transform.execucao_view import load_execucao_view
from my_pkg.transform.rp_view import load_rp_view
from my_pkg.transform.schema import (
    ALL_COLS, NUMERIC_COLS, BOOL_COLS, EDITABLE_COLS, REQUIRED_ON_NEW
)

# =============================================================================
# Configuração da Página
# =============================================================================
st.set_page_config(
    page_title="Propag - Monitoramento",
    page_icon="📊",
    layout="wide",
)

# =============================================================================
# Funções Utilitárias
# =============================================================================
def brl(value: float) -> str:
    """Formata float para string de moeda BRL (R$ 1.000,00)."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _to_plain_dict(obj):
    """Converte estruturas aninhadas do st.secrets em dicts/lists padrões."""
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
    """Garante que todas as colunas do schema existam e tenham tipos corretos."""
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

def validate_new_rows(df_before, df_after, allowed_uos, is_admin, working_uo):
    """Valida inserção de novas linhas no cronograma."""
    cols_key = ["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]
    before_idx = set(map(tuple, df_before[cols_key].astype(str).values))
    after_idx = set(map(tuple, df_after[cols_key].astype(str).values))
    new_keys = after_idx - before_idx

    is_new = df_after.apply(lambda r: tuple(r[cols_key].astype(str)) in new_keys, axis=1)
    new_rows = df_after[is_new].copy()

    if not new_rows.empty:
        # Verifica campos obrigatórios
        if (new_rows[REQUIRED_ON_NEW].isnull().any(axis=1).any() or (new_rows[REQUIRED_ON_NEW] == "").any(axis=1).any()):
            return False, "Preencha todos os campos obrigatórios na nova linha.", df_after
        df_after.loc[is_new, "novo_marco"] = "Sim"

    if not is_admin:
        if df_after["uo_cod"].isnull().any():
            return False, "Existem linhas sem UO definida.", df_after
        uos_present = set(pd.to_numeric(df_after["uo_cod"], errors="coerce").fillna(-1).astype(int).tolist())
        
        # Valida se a UO está na lista permitida do usuário
        if allowed_uos is None or not uos_present.issubset(set(allowed_uos)):
            return False, "Você inseriu uma UO não autorizada.", df_after
        
        # Valida se a UO é a de trabalho atual
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

st.sidebar.title("Acesso")
login_result = auth.login(location="sidebar", fields={"Form name": "Login"})

if isinstance(login_result, tuple):
    name, auth_status, username = login_result
else:
    name = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

if not auth_status:
    if auth_status is False:
        st.sidebar.error("Usuário ou senha incorretos.")
    st.stop()

auth.logout(button_name="Sair", location="sidebar", key="logout_sidebar")
st.sidebar.success(f"Logado como: {name}")

# Definição de permissões (RBAC)
rbac_secrets = load_rbac_from_secrets()
rbac_yaml = load_access_yaml()

allowed_uos_list = rbac_secrets.get(username, [])
if not allowed_uos_list:
    allowed_uos_list = rbac_yaml.get(username, [])

is_admin = ("*" in allowed_uos_list)
allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

working_uo = None
if is_admin:
    st.sidebar.info("Perfil: **Administrador**")
else:
    if not allowed_uos:
        st.error("Seu usuário não possui UOs vinculadas.")
        st.stop()
    # Se tiver mais de uma, permite escolher
    if len(allowed_uos) > 1:
        working_uo = st.sidebar.selectbox("Selecionar UO de Trabalho", sorted(allowed_uos))
    else:
        working_uo = list(allowed_uos)[0]
        st.sidebar.info(f"UO Vinculada: {working_uo}")

# =============================================================================
# 1. Métricas de Topo (Sempre Visíveis)
# =============================================================================
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

st.title("Propag - Monitoramento de Investimentos")

col1, col2, col3 = st.columns(3)
with col1: st.metric("Valor Total do Plano", brl(vlr_plano))
with col2: st.metric("Valor Total Liquidado", brl(vlr_liq))
with col3: st.metric("Saldo a Liquidar", brl(saldo))

st.divider()

# =============================================================================
# 2. Cronograma Físico - Google Sheets (Sempre Visível)
# =============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)
ss_cfg = st.secrets.get("connections", {}).get("gsheets", {})
spreadsheet = str(ss_cfg.get("spreadsheet", "") or st.sidebar.text_input("ID Planilha Google"))
worksheet = str(ss_cfg.get("worksheet", "Página1"))

if not spreadsheet:
    st.warning("⚠️ Planilha não configurada nos secrets.")
else:
    try:
        data_raw = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=5)
        data = normalize_dataframe(data_raw)
        
        # Filtra dados para usuários não-admin
        if not is_admin:
             data = data[pd.to_numeric(data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(working_uo)].copy()

        st.subheader("Cronograma de Intervenções")
        
        # Filtros Superiores da Tabela
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1:
            lista_uos = ["Todas"] + sorted(data["uo_sigla"].dropna().unique().tolist())
            uo_sel = st.selectbox("Filtrar UO", lista_uos) if is_admin else "Sua UO"
        
        df_view = data.copy()
        if is_admin and uo_sel != "Todas":
            df_view = df_view[df_view["uo_sigla"] == uo_sel]

        with c_f2:
            lista_acoes = ["Todas"] + sorted(df_view["acao_desc"].dropna().unique().tolist())
            acao_sel = st.selectbox("Filtrar Ação", lista_acoes)
        with c_f3:
            lista_interv = ["Todas"] + sorted(df_view["intervencao_desc"].dropna().unique().tolist())
            interv_sel = st.selectbox("Filtrar Intervenção", lista_interv)

        # Lógica de Edição: Só ativa se selecionar Ação ou Intervenção específica
        if acao_sel == "Todas" and interv_sel == "Todas":
            st.info("ℹ️ Selecione uma **Intervenção** ou **Ação** específica nos filtros acima para habilitar a edição.")
            # Mostra tabela estática para leitura
            st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            df_edit = df_view.copy()
            if acao_sel != "Todas": df_edit = df_edit[df_edit["acao_desc"] == acao_sel]
            if interv_sel != "Todas": df_edit = df_edit[df_edit["intervencao_desc"] == interv_sel]
            
            st.caption("Modo de Edição Ativo")
            
            # Configuração das Colunas do Editor
            col_cfg = {
                "valor_previsto_total": st.column_config.TextColumn(disabled=True),
                "novo_marco": st.column_config.SelectboxColumn("Novo Marco?", options=["Sim", "Não"], default="Sim", required=True),
                "acao_cod": st.column_config.NumberColumn(disabled=False, format="%d"),
                "uo_cod": st.column_config.NumberColumn(disabled=not is_admin, format="%d"),
            }
            # Se não for admin, força o UO_COD na edição visualmente (embora a validação ocorra no salvar)
            if not is_admin and "uo_cod" in df_edit.columns:
                df_edit["uo_cod"] = int(working_uo)

            # Colunas não editáveis
            cols_disabled = [c for c in ALL_COLS if (c not in EDITABLE_COLS and c != "novo_marco")]

            edited_df = st.data_editor(
                df_edit,
                num_rows="dynamic",
                use_container_width=True,
                column_config=col_cfg, 
                disabled=cols_disabled,
                key="editor_cronograma"
            )

            if st.button("💾 Salvar Alterações", type="primary"):
                is_valid, msg, validated_df = validate_new_rows(df_edit, edited_df, allowed_uos, is_admin, working_uo)
                if not is_valid:
                    st.error(f"Erro: {msg}")
                else:
                    try:
                        # Substitui as linhas editadas na base original
                        # Remove as antigas (baseado no index) e concatena as novas/editadas
                        mask_drop = data_raw.index.isin(df_edit.index)
                        # Mantém o que não foi tocado + o que foi editado/criado
                        final_df = pd.concat([data_raw[~mask_drop], validated_df], ignore_index=True)[ALL_COLS]
                        
                        conn.update(spreadsheet=spreadsheet, worksheet=worksheet, data=final_df)
                        st.toast("✅ Salvo com sucesso!", icon="💾")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no Google Sheets: {e}")

    except Exception as e:
        st.error(f"Erro ao conectar no Google Sheets: {e}")

st.divider()

# =============================================================================
# 3. Seletor de Visão (Execução vs Restos a Pagar)
# =============================================================================
st.subheader("Detalhamento Financeiro")

view_option = st.radio(
    "Selecione a base de dados para análise:",
    options=["Execução do Exercício (2026)", "Restos a Pagar (RP)"],
    horizontal=True,
    label_visibility="visible"
)

# Filtro de UO para as queries de banco de dados
restrict_uo_db = None if is_admin else int(working_uo)

# =============================================================================
# 3.A. Visão: Execução do Exercício
# =============================================================================
if view_option == "Execução do Exercício (2026)":
    st.markdown("---")
    st.markdown("#### 🟢 Tabela Dinâmica: Execução 2026")
    
    with st.spinner("Carregando dados de execução..."):
        df_exec = load_execucao_view(restrict_uo=restrict_uo_db)

    st.caption("Filtro aplicado: (Fonte 89 ou IPU 0) e UO ≠ 1261")

    # Opções do Menu Dinâmico
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
        with c_o1: use_brl = st.toggle("Formatar Moeda (R$)", value=True, key="toggle_brl_exec")
        with c_o2: remove_zero = st.toggle("Ocultar linhas zeradas", value=False, key="toggle_zero_exec")

    if not sel_meas_labels:
        st.warning("Selecione ao menos uma métrica para visualizar.")
    else:
        # Traduz labels para nomes de coluna
        sel_dims = [DIM_OPTIONS_EXEC[L] for L in sel_dims_labels]
        sel_meas = [MEASURE_OPTIONS_EXEC[L] for L in sel_meas_labels]

        # Agrupamento
        if not sel_dims:
            agg_df = pd.DataFrame(df_exec[sel_meas].sum()).T
        else:
            agg_df = df_exec.groupby(sel_dims, dropna=False)[sel_meas].sum().reset_index()

        # Filtragem de zeros
        if remove_zero:
            agg_df = agg_df.loc[agg_df[sel_meas].sum(axis=1) != 0]

        # Ordenação
        if sel_dims:
            agg_df = agg_df.sort_values(by=sel_dims)

        # Preparação para exibição
        display_df = agg_df.rename(columns={
            **{v: k for k, v in DIM_OPTIONS_EXEC.items()},
            **{v: k for k, v in MEASURE_OPTIONS_EXEC.items()}
        })

        if use_brl:
            for lbl in sel_meas_labels:
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
            "⬇️ Baixar CSV (Execução)",
            data=agg_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name="execucao_2026.csv",
            mime="text/csv"
        )

# =============================================================================
# 3.B. Visão: Restos a Pagar
# =============================================================================
else:
    st.markdown("---")
    st.markdown("#### 🟠 Tabela Dinâmica: Restos a Pagar (RP)")

    with st.spinner("Carregando Restos a Pagar..."):
        df_rp = load_rp_view(restrict_uo=restrict_uo_db)

    # Opções do Menu Dinâmico (RP)
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
        # Processados
        "Inscrito (RPP)": "calc_inscrito_rpp",
        "Cancelado (RPP)": "calc_cancelado_rpp",
        "Pago (RPP)": "calc_pago_rpp",
        "Saldo (RPP)": "calc_saldo_rpp",
        # Não Processados
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
        with c_rp_o1: use_brl_rp = st.toggle("Formatar Moeda (R$)", value=True, key="toggle_brl_rp")
        with c_rp_o2: remove_zero_rp = st.toggle("Ocultar linhas zeradas", value=False, key="toggle_zero_rp")

    if not sel_meas_rp_labels:
        st.warning("Selecione ao menos uma métrica para visualizar.")
    else:
        sel_dims_rp = [DIM_OPTIONS_RP[L] for L in sel_dims_rp_labels]
        sel_meas_rp = [MEASURE_OPTIONS_RP[L] for L in sel_meas_rp_labels]

        if not sel_dims_rp:
            agg_df_rp = pd.DataFrame(df_rp[sel_meas_rp].sum()).T
        else:
            agg_df_rp = df_rp.groupby(sel_dims_rp, dropna=False)[sel_meas_rp].sum().reset_index()

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
                    display_df_rp[lbl] = display_df_rp[lbl].apply(
                        lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    )

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
            data=agg_df_rp.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name="restos_a_pagar.csv",
            mime="text/csv"
        )