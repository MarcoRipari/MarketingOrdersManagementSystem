"""
matcher.py — Riconciliazione tra i dati estratti dall'email e l'anagrafica
esistente su Postgres (clienti, prodotti), con fallback su fuzzy matching.

Usa rapidfuzz (libreria gratuita, open source) per il confronto testuale:
niente chiamate AI aggiuntive per questa parte, quindi costo zero.
"""
from dataclasses import dataclass
from rapidfuzz import fuzz, process
from sqlalchemy import text

from config import Config


@dataclass
class RisultatoCliente:
    cliente_id: str | None  # UUID come stringa
    creato_nuovo: bool
    confidenza_bassa: bool
    dettagli: str


@dataclass
class RigaMatch:
    prodotto_id: str | None  # UUID come stringa
    descrizione_originale: str
    quantita: int
    confidenza_bassa: bool
    dettagli: str


def risolvi_cliente(session, dati_cliente: dict) -> RisultatoCliente:
    cod_cli = (dati_cliente.get("codice_cliente") or "").strip()
    cod_dest = (dati_cliente.get("codice_destinazione") or "").strip()
    nome = (dati_cliente.get("nome") or "").strip()

    # 1. Match esatto per codice cliente + destinazione (massima affidabilità)
    if cod_cli and cod_dest:
        riga = session.execute(
            text("SELECT id FROM clienti WHERE codice_cliente = :c AND codice_destinazione = :d"),
            {"c": cod_cli, "d": cod_dest},
        ).fetchone()
        if riga:
            return RisultatoCliente(riga[0], False, False, f"Match esatto su codice {cod_cli}/{cod_dest}")

    # 2. Fuzzy match sul nome contro l'anagrafica esistente
    if nome:
        righe = session.execute(text("SELECT id, nome FROM clienti")).fetchall()
        mappa_nomi = {r[1]: r[0] for r in righe}
        if mappa_nomi:
            migliore = process.extractOne(nome, mappa_nomi.keys(), scorer=fuzz.token_sort_ratio)
            if migliore and migliore[1] >= Config.SOGLIA_MATCH_CLIENTE:
                return RisultatoCliente(
                    mappa_nomi[migliore[0]], False, False,
                    f"Fuzzy match nome '{nome}' -> '{migliore[0]}' (score {migliore[1]:.0f})"
                )

    # 3. Nessun match affidabile: crea un nuovo cliente con i dati disponibili,
    #    ma segnala bassa confidenza (potrebbe essere un duplicato mal scritto).
    #    NB: 'indirizzo', 'citta' e 'cap' sono NOT NULL su questa tabella e 'cap'
    #    è un varchar(10): usiamo un placeholder corto per essere compatibili
    #    con qualunque colonna, invece di un testo descrittivo lungo.
    PLACEHOLDER = "N/D"
    res = session.execute(
        text("""
        INSERT INTO clienti (nome, indirizzo, citta, cap, nazione, codice_cliente, codice_destinazione, note)
        VALUES (:nome, :ind, :citta, :cap, :naz, :cod_cli, :cod_dest, :note)
        RETURNING id;
        """),
        {
            "nome": (nome or "DA COMPLETARE (creato da email)")[:100],
            "ind": (dati_cliente.get("indirizzo") or PLACEHOLDER)[:100],
            "citta": (dati_cliente.get("citta") or PLACEHOLDER)[:50],
            "cap": (dati_cliente.get("cap") or PLACEHOLDER)[:10],
            "naz": (dati_cliente.get("nazione") or "Italia")[:50],
            "cod_cli": cod_cli or None,
            "cod_dest": cod_dest or None,
            "note": "Cliente creato automaticamente dall'agente email: verificare indirizzo/citta/cap.",
        },
    )
    nuovo_id = res.fetchone()[0]
    return RisultatoCliente(
        nuovo_id, True, True,
        f"Nessun cliente esistente trovato per '{nome or cod_cli}': creato nuovo cliente da verificare."
    )


def risolvi_articoli(session, articoli: list[dict]) -> list[RigaMatch]:
    righe_prodotti = session.execute(text("SELECT id, descrizione, barcode FROM prodotti")).fetchall()
    mappa_descrizioni = {r[1]: r[0] for r in righe_prodotti}
    mappa_barcode = {r[2]: r[0] for r in righe_prodotti if r[2]}

    risultati = []
    for art in articoli:
        descr = (art.get("descrizione_grezza") or "").strip()
        barcode = (art.get("barcode") or "").strip()
        quantita = int(art.get("quantita") or 1)

        # 1. Match esatto per barcode
        if barcode and barcode in mappa_barcode:
            risultati.append(RigaMatch(mappa_barcode[barcode], descr, quantita, False, "Match esatto su barcode"))
            continue

        # 2. Fuzzy match sulla descrizione
        if descr and mappa_descrizioni:
            migliore = process.extractOne(descr, mappa_descrizioni.keys(), scorer=fuzz.token_sort_ratio)
            if migliore and migliore[1] >= Config.SOGLIA_MATCH_PRODOTTO:
                risultati.append(RigaMatch(
                    mappa_descrizioni[migliore[0]], descr, quantita, False,
                    f"Fuzzy match '{descr}' -> '{migliore[0]}' (score {migliore[1]:.0f})"
                ))
                continue

        # 3. Nessun match affidabile: NON si inventa un prodotto_id (rischio di
        #    scaricare stock sbagliato). La riga viene segnalata per aggiunta manuale.
        risultati.append(RigaMatch(None, descr, quantita, True, f"Nessun articolo corrispondente a '{descr}'"))

    return risultati
