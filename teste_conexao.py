# teste_conexao.py
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import traceback

print("\n--- Iniciando Teste de Conexão ---")

try:
    ss = st.secrets.get("connections", {}).get("gsheets", {})
    spreadsheet_secret = ss.get("spreadsheet")
    worksheet_secret = ss.get("worksheet", "Página1")

    print(f"spreadsheet (secrets): {spreadsheet_secret}")
    print(f"worksheet  (secrets): {worksheet_secret}")

    conn = st.connection("gsheets", type=GSheetsConnection)

    def tenta_ler(rotulo, spreadsheet, worksheet):
        print(f"\n[{rotulo}] Tentando ler: spreadsheet={spreadsheet} | worksheet={worksheet}")
        df = conn.read(spreadsheet=spreadsheet, worksheet=worksheet, ttl=0)
        print(f"[{rotulo}] SUCESSO! shape={df.shape}")
        print(df.head())
        return True

    ok = False

    # 1) Tenta com os valores do secrets (URL ou ID)
    try:
        ok = tenta_ler("SECRETS", spreadsheet_secret, worksheet_secret)
    except Exception as e:
        print(f"[SECRETS] Falhou: {e}")
        traceback.print_exc()

    # 2) Se falhar, tenta com ID puro (extraído da sua URL)
    if not ok and spreadsheet_secret:
        ID_APENAS = "1tw3d8R2Pv8w771K7_zBkV_vKROQuXF-qKZVhQoXkIJY"
        try:
            ok = tenta_ler("ID_PURO", ID_APENAS, worksheet_secret)
        except Exception as e:
            print(f"[ID_PURO] Falhou: {e}")
            traceback.print_exc()

    # 3) Se ainda falhar, tenta um nome de worksheet alternativo comum (Sheet1)
    if not ok and spreadsheet_secret:
        try:
            ok = tenta_ler("ALT_SHEET", spreadsheet_secret, "Sheet1")
        except Exception as e:
            print(f"[ALT_SHEET] Falhou: {e}")
            traceback.print_exc()

    # 4) Teste de escrita (OPCIONAL) - descomente para verificar permissão de edição
    # if ok:
    #     import pandas as pd
    #     print("\n[WRITE_TEST] Tentando escrever uma linha de teste...")
    #     df_atual = conn.read(spreadsheet=spreadsheet_secret, worksheet=worksheet_secret, ttl=0)
    #     df_teste = pd.concat([df_atual, pd.DataFrame([{"_teste_conexao": "ok", "_ts": pd.Timestamp.utcnow()}])], ignore_index=True)
    #     conn.update(spreadsheet=spreadsheet_secret, worksheet=worksheet_secret, data=df_teste)
    #     print("[WRITE_TEST] Escrita OK.")

    if not ok:
        print("\nXXX ERRO ENCONTRADO XXX")
        print("Não foi possível ler a planilha em nenhum dos modos testados.")
        print("\nDicas finais:")
        print("1) Compartilhe a planilha com o service account (Editor)")
        print("2) Use apenas o ID da planilha no secrets")
        print("3) Confirme o nome EXATO da aba (Página1/Sheet1 etc.)")
        print("4) Habilite Google Sheets API e Drive API no mesmo projeto do service account")
        print("5) Verifique se a aba tem pelo menos cabeçalho na linha 1")

except Exception as e:
    print("\nXXX ERRO ENCONTRADO XXX")
    print(e)
    traceback.print_exc()