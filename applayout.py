# app.py
# -*- coding: utf-8 -*-
"""
Propag - Monitoramento do Plano de Aplicação de Investimentos

Principais ajustes desta versão:
- Layout Compacto (CSS Turbo): Margens mínimas para subir o título.
- Multi-UO: Adicionada opção "Todas" no seletor da Sidebar para usuários com >1 UO (ex: DER).
- Rótulos e Visualização: Checkboxes para planejado, Formatação BRL para valores.
"""

from __future__ import annotations
import time
from collections.abc import Mapping
import numpy as np
import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader
from streamlit_gsheets import GSheetsConnection
import streamlit_authenticator as stauth

# ====== Módulos do projeto ======
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
# CSS PERSONALIZADO (Layout Turbo + Checkbox Azul)
# =============================================================================
st.markdown("""
    <style>
        /* Remove espaço em branco excessivo do topo */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            margin-top: 0rem !important;
        }
        
        /* Sobe o título e reduz margem inferior */
        h1 {
            font-size: 2.0rem !important; 
            margin-bottom: 0.2rem !important; 
            margin-top: -1.0rem !important; 
            padding-top: 0rem !important;
        }
        
        /* Ajusta divisores */
        hr {
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }

        /* Força Checkbox Azul */
        [data-testid="stDataFrame"] input[type="checkbox"]:checked {
            accent-color: #0000FF !important;
            filter: hue-rotate(240deg);
        }
    </style>
""", unsafe_allow_html=True)

# =============================================================================
# Rótulos de exibição
# =============================================================================
DISPLAY_LABELS = {
    "uo_cod": "UO",
    "uo_sigla": "UO Sigla",
    "acao_cod": "Ação",
    "acao_desc": "Ação Desc.",
    # "intervencao_cod": oculto
    "intervencao_desc": "Intervenção",
    "marcos_principais": "Marcos Principais",
    "novo_marco": "Novo Marco ?",
    "valor_previsto_total": "Valor Plano Total",
    "valor_replanejado_total": "Valor Plano Replanejado",
    "1_bimestre_planejado": "1ºb Plano",
    "1_bimestre_replanejado": "1ºb Replanejado",
    "1_bimestre_realizado": "1ºb Realizado",
    "2_bimestre_planejado": "2ºb Plano",
    "2_bimestre_replanejado": "2ºb Replanejado",
    "2_bimestre_realizado": "2ºb Realizado",
    "3_bimestre_planejado": "3ºb Plano",
    "3_bimestre_replanejado": "3ºb Replanejado",
    "3_bimestre_realizado": "3ºb Realizado",
    "4_bimestre_planejado": "4ºb Plano",
    "4_bimestre_replanejado": "4ºb Replanejado",
    "4_bimestre_realizado": "4ºb Realizado",
    "5_bimestre_planejado": "5ºb Plano",
    "5_bimestre_replanejado": "5ºb Replanejado",
    "5_bimestre_realizado": "5ºb Realizado",
    "6_bimestre_planejado": "6ºb Plano",
    "6_bimestre_replanejado": "6ºb Replanejado",
    "6_bimestre_realizado": "6ºb Realizado",
}
PLANEJADO_KEYS = [f"{i}_bimestre_planejado" for i in range(1, 7)]
PLANEJADO_LABELS = [DISPLAY_LABELS[k] for k in PLANEJADO_KEYS]

# =============================================================================
# Utilitários
# =============================================================================


def brl(value: float) -> str:
    """Formata para visualização (KPIs)"""
    if pd.isna(value):
        return "R$ 0,00"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"


def format_brl_edit(value) -> str:
    """Formata para o Editor (string)"""
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
    """Converte string BRL de volta para float"""
    if isinstance(value_str, (int, float)):
        return float(value_str)
    if pd.isna(value_str) or str(value_str).strip() == "":
        return 0.0
    clean = str(value_str).replace("R$", "").replace(
        " ", "").replace(".", "").replace(",", ".")
    try:
        return float(clean)
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

# =============================================================================
# Normalização
# =============================================================================


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza dados (Numéricos e Booleanos para Checkbox)."""
    data = df.copy()

    for c in ALL_COLS:
        if c not in data.columns:
            data[c] = None

    for col in NUMERIC_COLS:
        if col in data.columns:
            if data[col].dtype == object:
                data[col] = (
                    data[col].astype(str)
                    .str.replace(r"\[R$\.\s\]", "", regex=True)
                    .str.replace(",", ".")
                )
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

    # Códigos como inteiros (Int64)
    CODE_COLS = ["uo_cod", "acao_cod", "intervencao_cod"]
    for c in CODE_COLS:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce")
            data[c] = data[c].round(0).astype("Int64")

    # Tratamento Booleano Agressivo (Aceita X, SIM, TRUE)
    TRUE_TOKENS = {"TRUE", "TRUE()", "1", "SIM", "S", "YES",
                   "VERDADEIRO", "X", "OK", "V"}

    # Colunas de Planejado
    for col in PLANEJADO_KEYS:
        if col in data.columns:
            if data[col].dtype != bool:
                data[col] = data[col].astype(
                    str).str.strip().str.upper().isin(TRUE_TOKENS)
            data[col] = data[col].astype(bool)

    # Outros booleanos
    other_bool_cols = list(set(BOOL_COLS) - set(PLANEJADO_KEYS))
    for col in other_bool_cols:
        if col in data.columns:
            if data[col].dtype != bool:
                data[col] = data[col].astype(
                    str).str.strip().str.upper().isin(TRUE_TOKENS)
            data[col] = data[col].astype(bool)

    return data[ALL_COLS]


def validate_no_new_rows(df_before, df_after) -> tuple[bool, str, pd.DataFrame]:
    cols_key = ["uo_cod", "acao_cod", "intervencao_cod", "marcos_principais"]
    before_idx = set(map(tuple, df_before[cols_key].astype(str).values))
    after_idx = set(map(tuple, df_after[cols_key].astype(str).values))
    new_keys = after_idx - before_idx
    if new_keys:
        return False, "Inclusão de novas linhas desabilitada.", df_after
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

# Login Centralizado
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
# Sidebar (RBAC + Multi-UO)
# =============================================================================
with st.sidebar:
    st.header("Perfil")
    st.success(f"Logado como: **{name}**")
    auth.logout(button_name="Sair", location="sidebar", key="logout_sidebar")
    st.divider()

    rbac_secrets = load_rbac_from_secrets()
    rbac_yaml = load_access_yaml()
    allowed_uos_list = rbac_secrets.get(
        username, []) or rbac_yaml.get(username, [])

    is_admin = ("*" in allowed_uos_list)
    allowed_uos = None if is_admin else set(map(int, allowed_uos_list))

    # Seleção de UO com suporte a "Todas" para quem tem múltiplas
    uo_selection_str = None

    if is_admin:
        st.sidebar.info("Nível: **Administrador**")
    else:
        if not allowed_uos:
            st.error("Usuário sem UOs vinculadas.")
            st.stop()

        # Se tiver mais de uma UO (ex: DER tem 2301 e 4381), mostra opção "Todas"
        if len(allowed_uos) > 1:
            opts = ["Todas"] + [str(u) for u in sorted(allowed_uos)]
            uo_selection_str = st.sidebar.selectbox(
                "Selecionar UO de Trabalho", opts)
        else:
            uo_selection_str = str(list(allowed_uos)[0])
            st.sidebar.info(f"UO Vinculada: {uo_selection_str}")

# =============================================================================
# Cabeçalho e Métricas
# =============================================================================
st.title("Propag - Monitoramento de Investimentos")

# Carrega métricas (se necessário, filtre o df retornado por load_metrics se ele trouxer tudo)
try:
    vlr_plano, vlr_liq, saldo = load_metrics()
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")
    vlr_plano, vlr_liq, saldo = 0.0, 0.0, 0.0

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Valor Total do Plano", brl(vlr_plano))
with c2:
    st.metric("Valor Total Liquidado", brl(vlr_liq))
with c3:
    st.metric("Saldo a Liquidar", brl(saldo))
st.divider()

# =============================================================================
# Cronograma Físico
# =============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)
ss_cfg = st.secrets.get("connections", {}).get("gsheets", {})
spreadsheet = str(ss_cfg.get("spreadsheet", "")
                  or st.sidebar.text_input("ID Planilha Google"))
worksheet = str(ss_cfg.get("worksheet", "Página1"))


def style_view(df_labels: pd.DataFrame, planejado_labels: list[str], code_labels: list[str], colorir: bool = True) -> pd.io.formats.style.Styler:
    styles = pd.DataFrame("", index=df_labels.index, columns=df_labels.columns)
    if colorir:
        # Se estiver usando o modo de visualização onde convertemos bool para "X"
        for c in planejado_labels:
            if c in df_labels.columns:
                styles[c] = np.where(
                    df_labels[c].astype(str).str.strip(
                    ).str.upper().isin(["X", "TRUE"]),
                    "background-color: #DFF6DD", ""
                )
    styler = df_labels.style.apply(lambda _: styles, axis=None)

    def fmt_int(v):
        try:
            return f"{int(float(v))}" if pd.notna(v) and v != "" else ""
        except:
            return str(v)

    fmt_map = {lbl: fmt_int for lbl in code_labels if lbl in df_labels.columns}
    if fmt_map:
        styler = styler.format(fmt_map)
    return styler


if not spreadsheet:
    st.warning("⚠️ Planilha não configurada.")
else:
    try:
        data_raw = conn.read(spreadsheet=spreadsheet,
                             worksheet=worksheet, ttl=5)
        data = normalize_dataframe(data_raw)

        # Filtra dados conforme seleção da Sidebar (Single ou Multi/Todas)
        if not is_admin:
            if uo_selection_str == "Todas":
                # Filtra onde uo_cod está na lista permitida
                data = data[data["uo_cod"].isin(allowed_uos)].copy()
            else:
                # Filtra pela UO específica selecionada
                data = data[pd.to_numeric(
                    data["uo_cod"], errors="coerce").fillna(-1).astype(int) == int(uo_selection_str)].copy()

        st.subheader("Cronograma de Intervenções")

        # Filtros Internos da Tabela
        f1, f2, f3 = st.columns(3)
        with f1:
            lista_uos = ["Todas"] + \
                sorted(data["uo_sigla"].dropna().unique().tolist())
            uo_sel = st.selectbox("Filtrar UO", lista_uos)
        df_view = data.copy()
        if uo_sel != "Todas":
            df_view = df_view[df_view["uo_sigla"] == uo_sel]

        with f2:
            lista_acoes = ["Todas"] + \
                sorted(df_view["acao_desc"].dropna().unique().tolist())
            acao_sel = st.selectbox("Filtrar Ação", lista_acoes)
        with f3:
            lista_interv = [
                "Todas"] + sorted(df_view["intervencao_desc"].dropna().unique().tolist())
            interv_sel = st.selectbox("Filtrar Intervenção", lista_interv)

        # Formatação Monetária
        money_cols = ["valor_previsto_total", "valor_replanejado_total"]
        for i in range(1, 7):
            money_cols += [f"{i}_bimestre_replanejado",
                           f"{i}_bimestre_realizado"]

        df_display = df_view.copy()
        for col in money_cols:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(format_brl_edit)

        # Configuração de Colunas
        base_column_config = {
            "uo_cod": st.column_config.NumberColumn(DISPLAY_LABELS["uo_cod"], format="%d"),
            "uo_sigla": st.column_config.TextColumn(DISPLAY_LABELS["uo_sigla"]),
            "acao_cod": st.column_config.NumberColumn(DISPLAY_LABELS["acao_cod"], format="%d"),
            "acao_desc": st.column_config.TextColumn(DISPLAY_LABELS["acao_desc"]),
            "intervencao_cod": None,  # oculto
            "intervencao_desc": st.column_config.TextColumn(DISPLAY_LABELS["intervencao_desc"]),
            "marcos_principais": st.column_config.TextColumn(DISPLAY_LABELS["marcos_principais"]),
            "novo_marco": st.column_config.CheckboxColumn(DISPLAY_LABELS["novo_marco"], default=False),
            "valor_previsto_total": st.column_config.TextColumn(DISPLAY_LABELS["valor_previsto_total"], disabled=True),
            "valor_replanejado_total": st.column_config.TextColumn(DISPLAY_LABELS["valor_replanejado_total"]),
        }
        for i in range(1, 7):
            # Planejado = Checkbox
            base_column_config[f"{i}_bimestre_planejado"] = st.column_config.CheckboxColumn(
                DISPLAY_LABELS[f"{i}_bimestre_planejado"])
            base_column_config[f"{i}_bimestre_replanejado"] = st.column_config.TextColumn(
                DISPLAY_LABELS[f"{i}_bimestre_replanejado"])
            base_column_config[f"{i}_bimestre_realizado"] = st.column_config.TextColumn(
                DISPLAY_LABELS[f"{i}_bimestre_realizado"])

        # ===================== VISUALIZAÇÃO / EDIÇÃO =====================
        st.markdown("#### Exibição / Edição")
        editar = st.toggle(
            "Editar dados (apenas Replanejado/Realizado)", value=False)

        if not editar:
            # Modo Leitura: Convertemos Boolean para "X" para usar estilo visual se quiser,
            # ou mantemos Checkbox. O script anterior usava Styler com "X".
            # Vou manter a lógica visual pedida anteriormente: "X" com fundo verde.

            view_df = df_display.drop(
                columns=["intervencao_cod"], errors="ignore").copy()

            # Converte Bool para "X" apenas para visualização colorida
            for c in PLANEJADO_KEYS:
                if c in view_df.columns:
                    view_df[c] = view_df[c].apply(
                        lambda x: "X" if x is True else "")

            view_df = view_df.rename(columns=DISPLAY_LABELS)
            CODE_LABELS_VIEW = ["UO", "Ação"]

            # Aplica cor verde onde tem "X"
            styled = style_view(view_df, PLANEJADO_LABELS,
                                CODE_LABELS_VIEW, colorir=True)
            st.dataframe(styled, use_container_width=True, hide_index=True)

        else:
            # Modo Edição: Checkboxes Reais
            df_edit = df_display.copy()
            if "novo_marco" in df_edit.columns:
                df_edit = df_edit[df_edit["novo_marco"] == False].copy()

            st.caption("Edição: Planejado é fixo.")
            edit_cfg = base_column_config.copy()
            # UO desabilitada se não for admin
            edit_cfg["uo_cod"] = st.column_config.NumberColumn(
                DISPLAY_LABELS["uo_cod"], disabled=not is_admin, format="%d")

            cols_disabled = [c for c in ALL_COLS if (
                c not in EDITABLE_COLS and c != "novo_marco")]
            cols_disabled = sorted(set(cols_disabled).union(
                set(PLANEJADO_KEYS)).union({"novo_marco"}))

            edited_df = st.data_editor(
                df_edit,
                num_rows="fixed",
                use_container_width=True,
                column_config=edit_cfg,
                disabled=cols_disabled,
                key="editor_cronograma"
            )

            if st.button("💾 Salvar Alterações", type="primary"):
                df_to_save = edited_df.copy()
                # Texto BR -> Float
                for col in money_cols:
                    if col in df_to_save.columns:
                        df_to_save[col] = df_to_save[col].apply(parse_brl_edit)

                # Checkbox Bool -> Mantém Bool
                # (Não precisa converter para X aqui, salvamos como TRUE/FALSE no sheets)

                df_before_save = df_edit.copy()
                for col in money_cols:
                    if col in df_before_save.columns:
                        df_before_save[col] = df_before_save[col].apply(
                            parse_brl_edit)

                is_valid, msg, validated_df = validate_no_new_rows(
                    df_before_save, df_to_save)
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
                        st.error(f"Erro ao salvar: {e}")

    except Exception as e:
        st.error(f"Erro ao conectar no Google Sheets: {e}")

st.divider()

# =============================================================================
# 3. Detalhamento Financeiro (Multi-UO)
# =============================================================================
st.subheader("Execução da Despesa e Restos a Pagar")

view_option = st.radio(
    "Selecione a base de dados:",
    options=["Execução do Exercício (2026)", "Restos a Pagar (RP)"],
    horizontal=True
)

# Filtro do banco de dados baseado na seleção da Sidebar
restrict_uo_db = None
if not is_admin:
    if uo_selection_str == "Todas":
        # Se escolheu Todas, NÃO restringe na query (traz tudo) mas filtra depois
        # Nota: load_execucao_view(None) carrega tudo. Precisamos filtrar o DF retornado.
        restrict_uo_db = None
    else:
        restrict_uo_db = int(uo_selection_str)

if view_option == "Execução do Exercício (2026)":
    st.markdown("---")
    with st.spinner("Carregando dados..."):
        df_exec = load_execucao_view(restrict_uo=restrict_uo_db)

        # Filtro de Segurança Adicional (Caso tenha selecionado "Todas")
        if not is_admin and uo_selection_str == "Todas":
            df_exec = df_exec[df_exec["uo_cod"].isin(allowed_uos)]

    st.caption("Filtro aplicado: (Fonte 89 ou IPU 0) e UO ≠ 1261")

    DIM_OPTIONS_EXEC = {
        "Ano": "ano", "UO (cód.)": "uo_cod", "UO (sigla)": "uo_sigla",
        "Ação (cód.)": "acao_cod", "Ação (descrição)": "acao_desc",
        "Grupo Despesa": "grupo_cod", "Fonte": "fonte_cod", "IPU": "ipu_cod",
        "Credor": "cnpj_cpf_formatado", "Nº Contrato": "num_contrato_saida", "Nº Empenho": "num_empenho"
    }
    MEASURE_OPTIONS_EXEC = {
        "Empenhado": "vlr_empenhado", "Liquidado": "vlr_liquidado", "Pago": "vlr_pago_orcamentario"
    }

    with st.expander("Menu de Dimensões", expanded=True):
        c1, c2 = st.columns(2)
        sel_dims = c1.multiselect("Linhas:", list(
            DIM_OPTIONS_EXEC.keys()), default=["Ano", "UO (sigla)"])
        sel_meas = c2.multiselect("Colunas:", list(
            MEASURE_OPTIONS_EXEC.keys()), default=["Liquidado"])
        use_brl_toggle = st.toggle("Formatar Moeda (R$)", value=True)

    if sel_meas:
        dims = [DIM_OPTIONS_EXEC[L] for L in sel_dims]
        meas = [MEASURE_OPTIONS_EXEC[L] for L in sel_meas]

        if not dims:
            agg = pd.DataFrame(df_exec[meas].sum()).T
        else:
            agg = df_exec.groupby(dims, dropna=False)[
                meas].sum().reset_index().sort_values(by=dims)

        display = agg.rename(columns={**{v: k for k, v in DIM_OPTIONS_EXEC.items()}, **{
                             v: k for k, v in MEASURE_OPTIONS_EXEC.items()}})

        if use_brl_toggle:
            for c in sel_meas:
                display[c] = display[c].apply(brl)

        st.dataframe(display, use_container_width=True, hide_index=True, column_config={
                     "Ano": st.column_config.NumberColumn(format="%d")})
        st.download_button("⬇️ Baixar CSV", agg.to_csv(
            index=False, sep=";", decimal=",").encode("utf-8-sig"), "execucao.csv")

else:
    st.markdown("---")
    with st.spinner("Carregando RP..."):
        df_rp = load_rp_view(restrict_uo=restrict_uo_db)
        if not is_admin and uo_selection_str == "Todas":
            df_rp = df_rp[df_rp["uo_cod"].isin(allowed_uos)]

    # (Configuração similar para RP - simplificada aqui para caber)
    DIM_RP = {"Ano Exercício": "ano",
              "UO (sigla)": "uo_sigla", "Nº Contrato": "num_contrato_saida"}
    MEAS_RP = {"Pago (RPP)": "calc_pago_rpp", "Pago (RPNP)": "calc_pago_rpnp"}

    with st.expander("Menu de Dimensões", expanded=True):
        c1, c2 = st.columns(2)
        sel_dims_rp = c1.multiselect("Linhas:", list(
            DIM_RP.keys()), default=["UO (sigla)"])
        sel_meas_rp = c2.multiselect("Colunas:", list(
            MEAS_RP.keys()), default=["Pago (RPP)", "Pago (RPNP)"])
        use_brl_rp = st.toggle("Formatar Moeda (R$)", value=True, key="rp_brl")

    if sel_meas_rp:
        dims = [DIM_RP[L] for L in sel_dims_rp]
        meas = [MEAS_RP[L] for L in sel_meas_rp]
        if not dims:
            agg = pd.DataFrame(df_rp[meas].sum()).T
        else:
            agg = df_rp.groupby(dims, dropna=False)[
                meas].sum().reset_index().sort_values(by=dims)

        disp = agg.rename(columns={
                          **{v: k for k, v in DIM_RP.items()}, **{v: k for k, v in MEAS_RP.items()}})
        if use_brl_rp:
            for c in sel_meas_rp:
                disp[c] = disp[c].apply(brl)

        st.dataframe(disp, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Baixar CSV", agg.to_csv(
            index=False, sep=";", decimal=",").encode("utf-8-sig"), "rp.csv")
