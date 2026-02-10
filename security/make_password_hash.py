# security/make_password_hash.py
import streamlit_authenticator as stauth

# Substitua pelas senhas em claro apenas LOCALMENTE para gerar os hashes
senhas = {
    "admin":   "propag_seplag,
    "pmmg":    "propag_pmmg",
    "cbmmg":   "propag_cbmmg",
    "der":     "propag_der",
    "seinfra": "propag_seinfra",
    "pcmg":    "propag_pcmg",
    "sejusp":  "propag_sejusp",
}

hashes = stauth.Hasher(list(senhas.values())).generate()

for (user, plain), h in zip(senhas.items(), hashes):
    print(f"[{user}] senha: {plain} -> hash: {h}")