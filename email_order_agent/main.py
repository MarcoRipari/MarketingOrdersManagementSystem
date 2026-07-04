"""
main.py — Orchestratore dell'agente "email -> ordine marketing".

Flusso:
  1. Legge le email non processate dalla label Gmail dedicata
  2. Per ciascuna, chiama Gemini per estrarre i dati strutturati
  3. Risolve/crea il cliente e gli articoli sull'anagrafica esistente
  4. Crea l'ordine (ordini_testata + ordini_righe), flaggato se incerto
  5. Logga l'esito, invia un'email di riepilogo/alert, marca l'email come letta

Pensato per essere eseguito periodicamente da GitHub Actions
(vedi .github/workflows/email_order_agent.yml).
"""
import json
import traceback
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import Config
from email_reader import leggi_email_da_processare, segna_come_processata, invia_notifica
from ai_parser import interpreta_email
from matcher import risolvi_cliente, risolvi_articoli


def processa_una_email(session, email_ordine) -> dict:
    """Elabora una singola email. Ritorna un riepilogo per il log/la notifica."""
    dati = interpreta_email(email_ordine.testo)

    risultato_cliente = risolvi_cliente(session, dati.get("cliente", {}))
    righe_match = risolvi_articoli(session, dati.get("articoli", []))

    righe_ok = [r for r in righe_match if r.prodotto_id is not None]
    righe_da_verificare = [r for r in righe_match if r.prodotto_id is None]

    da_verificare = risultato_cliente.confidenza_bassa or bool(righe_da_verificare) or not righe_ok

    note_ordine_parti = []
    if dati.get("note"):
        note_ordine_parti.append(f"Note mittente: {dati['note']}")
    note_ordine_parti.append(f"[Origine: email automatica] {risultato_cliente.dettagli}")
    if righe_da_verificare:
        elenco = "; ".join(f"'{r.descrizione_originale}' (qta {r.quantita})" for r in righe_da_verificare)
        note_ordine_parti.append(f"ARTICOLI NON RICONOSCIUTI (da aggiungere a mano): {elenco}")

    note_ordine = " | ".join(note_ordine_parti)

    ordine_id = None
    if righe_ok:
        res = session.execute(
            text("""
                INSERT INTO ordini_testata (cliente_id, note, stato, origine, da_verificare)
                VALUES (:cliente_id, :note, 'Nuovo', 'email', :da_verificare)
                RETURNING id;
            """),
            {"cliente_id": risultato_cliente.cliente_id, "note": note_ordine, "da_verificare": da_verificare},
        )
        ordine_id = res.fetchone()[0]

        for riga in righe_ok:
            session.execute(
                text("""
                    INSERT INTO ordini_righe (ordine_id, prodotto_id, quantita_richiesta)
                    VALUES (:ordine_id, :prodotto_id, :qty);
                """),
                {"ordine_id": ordine_id, "prodotto_id": riga.prodotto_id, "qty": riga.quantita},
            )

    return {
        "ordine_id": ordine_id,
        "da_verificare": da_verificare,
        "cliente": risultato_cliente,
        "righe_ok": righe_ok,
        "righe_da_verificare": righe_da_verificare,
        "dati_grezzi": dati,
    }


def costruisci_email_riepilogo(email_ordine, esito: dict) -> tuple[str, str]:
    if esito["ordine_id"] is None:
        oggetto = f"❌ Email ordine NON elaborata — '{email_ordine.oggetto}'"
        corpo = (
            f"Non è stato possibile creare l'ordine dall'email '{email_ordine.oggetto}' "
            f"({email_ordine.mittente}): nessun articolo è stato riconosciuto.\n\n"
            f"Dati grezzi estratti:\n{json.dumps(esito['dati_grezzi'], indent=2, ensure_ascii=False)}\n\n"
            f"Crea l'ordine manualmente da Streamlit."
        )
        return oggetto, corpo

    prefisso = "⚠️ DA VERIFICARE" if esito["da_verificare"] else "✅"
    oggetto = f"{prefisso} Ordine #{esito['ordine_id']} creato da email — '{email_ordine.oggetto}'"

    righe_txt = "\n".join(
        f"  - {r.descrizione_originale} x{r.quantita}  [{r.dettagli}]" for r in esito["righe_ok"]
    )
    non_trovate_txt = "\n".join(
        f"  - {r.descrizione_originale} x{r.quantita}  (NON aggiunto: {r.dettagli})"
        for r in esito["righe_da_verificare"]
    )

    corpo = (
        f"Ordine #{esito['ordine_id']} creato in stato 'Nuovo'.\n\n"
        f"Cliente: {esito['cliente'].dettagli}"
        f"{' (NUOVO CLIENTE CREATO — verifica i dati anagrafici)' if esito['cliente'].creato_nuovo else ''}\n\n"
        f"Articoli inseriti:\n{righe_txt or '  (nessuno)'}\n"
    )
    if non_trovate_txt:
        corpo += f"\nArticoli NON riconosciuti (aggiungili a mano dalla pagina Inserimento Ordini):\n{non_trovate_txt}\n"
    if esito["dati_grezzi"].get("note"):
        corpo += f"\nNote del mittente: {esito['dati_grezzi']['note']}\n"

    return oggetto, corpo


def main():
    engine = create_engine(Config.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)

    email_da_processare = leggi_email_da_processare()
    print(f"Trovate {len(email_da_processare)} email da processare.")

    for email_ordine in email_da_processare:
        session = SessionLocal()
        try:
            # Dedup: se il message_id è già stato loggato, salta (evita doppioni)
            gia_processata = session.execute(
                text("SELECT 1 FROM email_ordini_log WHERE message_id = :mid"),
                {"mid": email_ordine.message_id},
            ).fetchone()
            if gia_processata:
                print(f"Email {email_ordine.message_id} già processata in precedenza, salto.")
                segna_come_processata(email_ordine.uid)
                session.close()
                continue

            esito = processa_una_email(session, email_ordine)
            session.commit()

            oggetto_notifica, corpo_notifica = costruisci_email_riepilogo(email_ordine, esito)
            invia_notifica(oggetto_notifica, corpo_notifica)

            session.execute(
                text("""
                    INSERT INTO email_ordini_log
                        (message_id, data_ricezione, mittente, oggetto, esito, ordine_id, dettagli_json)
                    VALUES (:mid, :data_ric, :mitt, :ogg, :esito, :ordine_id, :dettagli)
                """),
                {
                    "mid": email_ordine.message_id,
                    "data_ric": email_ordine.data_ricezione,
                    "mitt": email_ordine.mittente,
                    "ogg": email_ordine.oggetto,
                    "esito": "da_verificare" if esito["da_verificare"] else "ok" if esito["ordine_id"] else "errore",
                    "ordine_id": esito["ordine_id"],
                    "dettagli": json.dumps(esito["dati_grezzi"], ensure_ascii=False),
                },
            )
            session.commit()

            segna_come_processata(email_ordine.uid)
            print(f"Email {email_ordine.message_id} elaborata: ordine_id={esito['ordine_id']}")

        except Exception as e:
            session.rollback()
            traceback.print_exc()
            try:
                session.execute(
                    text("""
                        INSERT INTO email_ordini_log
                            (message_id, data_ricezione, mittente, oggetto, esito, messaggio_errore)
                        VALUES (:mid, :data_ric, :mitt, :ogg, 'errore', :err)
                        ON CONFLICT (message_id) DO NOTHING
                    """),
                    {
                        "mid": email_ordine.message_id,
                        "data_ric": email_ordine.data_ricezione,
                        "mitt": email_ordine.mittente,
                        "ogg": email_ordine.oggetto,
                        "err": str(e),
                    },
                )
                session.commit()
            except Exception:
                pass
            invia_notifica(
                f"❌ ERRORE elaborazione email ordine — '{email_ordine.oggetto}'",
                f"Errore durante l'elaborazione automatica:\n\n{e}\n\nL'email NON è stata marcata come letta, "
                f"verrà ritentata al prossimo giro. Se l'errore persiste, gestisci l'ordine manualmente.",
            )
        finally:
            session.close()


if __name__ == "__main__":
    main()
