"""
ai_parser.py — Interpretazione del testo libero dell'email tramite Gemini API
(livello gratuito di Google AI Studio: https://aistudio.google.com/apikey).

L'output è forzato in JSON tramite response_schema, così non serve fare
parsing fragile di testo libero restituito dal modello.
"""
import json
import requests

from config import Config

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)

SCHEMA_RISPOSTA = {
    "type": "object",
    "properties": {
        "cliente": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "nullable": True},
                "codice_cliente": {"type": "string", "nullable": True},
                "codice_destinazione": {"type": "string", "nullable": True},
                "indirizzo": {"type": "string", "nullable": True},
                "citta": {"type": "string", "nullable": True},
                "cap": {"type": "string", "nullable": True},
                "nazione": {"type": "string", "nullable": True},
            },
        },
        "articoli": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "descrizione_grezza": {"type": "string"},
                    "barcode": {"type": "string", "nullable": True},
                    "quantita": {"type": "integer"},
                },
                "required": ["descrizione_grezza", "quantita"],
            },
        },
        "note": {"type": "string", "nullable": True},
    },
    "required": ["cliente", "articoli"],
}

PROMPT_SISTEMA = """Sei un assistente che estrae dati strutturati da email di ordini
marketing per un'azienda calzaturiera italiana. Il testo puo' contenere commenti
del mittente, saluti, firme, thread di risposta precedenti: ignora tutto cio' che
non e' pertinente all'ordine (saluti, firme, disclaimer legali, email precedenti
nel thread) e concentrati solo sui dati dell'ordine.

Regole:
- codice_cliente: se presente, e' un numero di 7 cifre. codice_destinazione: 3 cifre.
  Se non espliciti nel testo, lasciali null (non inventare mai codici).
- Per ogni articolo estrai la descrizione COSI' COME SCRITTA dal mittente
  (descrizione_grezza) e la quantita' richiesta (se non specificata, usa 1).
  Se e' presente un barcode/codice articolo esplicito, riportalo.
- Il campo note deve contenere eventuali richieste speciali o commenti del mittente
  (es. priorita', data di consegna richiesta, ecc.), NON i saluti/firma.
- Se un dato non e' presente nel testo, usa null: non inventare mai informazioni.
"""


def interpreta_email(testo_email: str) -> dict:
    """Chiama Gemini e restituisce il dizionario con i dati strutturati estratti."""
    url = GEMINI_URL_TEMPLATE.format(model=Config.GEMINI_MODEL, key=Config.GEMINI_API_KEY)

    payload = {
        "system_instruction": {"parts": [{"text": PROMPT_SISTEMA}]},
        "contents": [{"parts": [{"text": testo_email}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": SCHEMA_RISPOSTA,
            "temperature": 0.1,
        },
    }

    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    dati = resp.json()

    testo_json = dati["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(testo_json)
