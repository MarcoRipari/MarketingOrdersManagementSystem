"""
config.py — Configurazione centralizzata per l'agente email -> ordini.

Tutte le credenziali arrivano da variabili d'ambiente, che in produzione
sono impostate come "Secrets" del repository GitHub Actions.
Non inserire MAI valori reali direttamente in questo file.
"""
import os


class Config:
    # --- Gmail (lettura e invio email) ---
    GMAIL_USER = os.environ["GMAIL_USER"]                  # es. tuonome@gmail.com
    GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]  # App Password a 16 caratteri

    # Etichetta Gmail da cui leggere le email da processare.
    # Crea un filtro Gmail che applica questa label automaticamente
    # (es. su tutte le email che arrivano con "ordine" nell'oggetto,
    # o su quelle che ti forwardi da solo).
    GMAIL_LABEL = os.environ.get("GMAIL_LABEL", "ordini-auto")

    # --- Gemini API (Google AI Studio - livello gratuito) ---
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    # Verifica il nome del modello gratuito corrente su ai.google.dev/gemini-api/docs/models
    # prima del primo utilizzo: i nomi cambiano nel tempo.
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # --- Database Supabase (stesso usato da Streamlit) ---
    DATABASE_URL = os.environ["SUPABASE_DB_URL"]
    # Formato atteso: postgresql://user:password@host:port/dbname

    # --- Soglie di matching fuzzy (0-100, rapidfuzz) ---
    SOGLIA_MATCH_CLIENTE = int(os.environ.get("SOGLIA_MATCH_CLIENTE", "82"))
    SOGLIA_MATCH_PRODOTTO = int(os.environ.get("SOGLIA_MATCH_PRODOTTO", "80"))

    # --- Destinatario delle email di riepilogo/alert (default: te stesso) ---
    NOTIFICA_EMAIL_TO = os.environ.get("NOTIFICA_EMAIL_TO", GMAIL_USER)
