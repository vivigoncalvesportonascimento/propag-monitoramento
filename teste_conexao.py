# teste_conexao.py
import streamlit as st
from streamlit_gsheets import GSheetsConnection

print("\n--- Iniciando Teste de Conexão ---")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)

    ss = st.secrets.get("connections", {}).get("gsheets", {})
    spreadsheet = ss.get("spreadsheet")
    worksheet = ss.get("worksheet", "Página1")

    print(f"spreadsheet (secrets): {spreadsheet}")
    print(f"worksheet  (secrets): {worksheet}")

    if not spreadsheet:
        raise ValueError(
            "Spreadsheet não encontrado nos secrets. "
            "Coloque a URL completa em .streamlit/secrets.toml [connections.gsheets]."
        )

    print("Tentando ler a planilha...")
    df = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=0)
    print("SUCESSO! Conexão realizada.")
    print(df.head())

except Exception as e:
    print("\nXXX ERRO ENCONTRADO XXX")
    print(e)
    print("\nDicas:")
    print("1) Salve o secrets em ./.streamlit/secrets.toml")
    print("2) Use a URL completa em [connections.gsheets].spreadsheet")
    print("3) Compartilhe a planilha com o e-mail do service account (Editor)")
    print("4) Ative as APIs Google Sheets e Drive no projeto do service account")