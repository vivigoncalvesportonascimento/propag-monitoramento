# security/make_password_hash.py
import streamlit_authenticator as stauth

# Substitua pelas senhas em claro apenas LOCALMENTE para gerar os hashes
senhas = {
    "admin":   "SENHA_DO_ADMIN",
    "pmmg":    "SENHA_DA_PMMG",
    "cbmmg":   "SENHA_DA_CBMMG",
    "der":     "SENHA_DO_DER",
    "seinfra": "SENHA_DA_SEINFRA",
    "pcmg":    "SENHA_DA_PCMG",
    "sejusp":  "SENHA_DA_SEJUSP",
}

hashes = stauth.Hasher(list(senhas.values())).generate()

for (user, plain), h in zip(senhas.items(), hashes):
    print(f"[{user}] senha: {plain} -> hash: {h}")