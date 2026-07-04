"""
config.py — Configurazione centralizzata per l'agente email -> ordini.

Tutte le credenziali arrivano da variabili d'ambiente, che in produzione
sono impostate come "Secrets" del repository GitHub Actions.
Non inserire MAI valori reali direttamente in questo file.
"""
import os


def _leggi_env_obbligatoria(nome: str) -> str:
    """Legge una variabile d'ambiente obbligatoria e segnala subito se manca o è vuota,
    con un messaggio chiaro invece di un errore criptico più avanti nel codice."""
    valore = os.environ.get(nome)
    if valore is None or valore.strip() == "":
        raise RuntimeError(
            f"Variabile d'ambiente '{nome}' mancante o vuota. "
            f"Controlla che il secret '{nome}' sia impostato su GitHub "
            f"(Settings > Secrets and variables > Actions) e che il nome "
            f"corrisponda ESATTAMENTE a quello usato nel workflow .yml."
        )
    return valore.strip()


def _normalizza_url_database(url_grezzo: str) -> str:
    """Ripulisce e normalizza la stringa di connessione al database.

    Gestisce gli errori più comuni:
    - spazi o virgolette accidentalmente incollate insieme al valore
    - schema 'postgres://' (alias storico) invece di 'postgresql://'
    - assenza dello schema del driver (forza psycopg2 esplicitamente)
    """
    url = url_grezzo.strip().strip('"').strip("'")

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    if not url.startswith("postgresql+psycopg2://"):
        raise RuntimeError(
            f"Il valore di SUPABASE_DB_URL non sembra una connection string valida "
            f"(deve iniziare con 'postgresql://' o 'postgres://'). "
            f"Valore ricevuto (primi 15 caratteri, per non esporre credenziali nei log): "
            f"'{url_grezzo.strip()[:15]}...'"
        )

    return url


class Config:
    # --- Gmail (lettura e invio email) ---
    GMAIL_USER = _leggi_env_obbligatoria("GMAIL_USER")                  # es. tuonome@gmail.com
    GMAIL_APP_PASSWORD = _leggi_env_obbligatoria("GMAIL_APP_PASSWORD")  # App Password a 16 caratteri

    # Etichetta Gmail da cui leggere le email da processare.
    # Crea un filtro Gmail che applica questa label automaticamente
    # (es. su tutte le email che arrivano con "ordine" nell'oggetto,
    # o su quelle che ti forwardi da solo).
    GMAIL_LABEL = os.environ.get("GMAIL_LABEL", "ordini-auto")

    # --- Gemini API (Google AI Studio - livello gratuito) ---
    GEMINI_API_KEY = _leggi_env_obbligatoria("GEMINI_API_KEY")
    # Verifica il nome del modello gratuito corrente su ai.google.dev/gemini-api/docs/models
    # prima del primo utilizzo: i nomi cambiano nel tempo.
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # --- Database Supabase (stesso usato da Streamlit) ---
    DATABASE_URL = _normalizza_url_database(_leggi_env_obbligatoria("SUPABASE_DB_URL"))
    # Formato atteso: postgresql://user:password@host:port/dbname

    # --- Soglie di matching fuzzy (0-100, rapidfuzz) ---
    SOGLIA_MATCH_CLIENTE = int(os.environ.get("SOGLIA_MATCH_CLIENTE", "82"))
    SOGLIA_MATCH_PRODOTTO = int(os.environ.get("SOGLIA_MATCH_PRODOTTO", "80"))

    # --- Destinatario delle email di riepilogo/alert (default: te stesso) ---
    NOTIFICA_EMAIL_TO = os.environ.get("NOTIFICA_EMAIL_TO", GMAIL_USER)
