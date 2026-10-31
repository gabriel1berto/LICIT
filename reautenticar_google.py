"""
Reautentica o OAuth local (Sheets + Drive) quando token.json expira/é revogado.
Abre o navegador pra login — rodar manualmente (`! python reautenticar_google.py`).
Mesmo client (credentials.json) e escopos do setup original (09/jul/2026).
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
creds = flow.run_local_server(port=0, open_browser=False)

with open(TOKEN_FILE, "w", encoding="utf-8") as f:
    f.write(creds.to_json())

print(f"Token salvo em {TOKEN_FILE}")
