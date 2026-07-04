"""
email_reader.py — Lettura email da Gmail via IMAP e invio notifiche via SMTP.

Usa una Gmail App Password (https://myaccount.google.com/apppasswords),
non la password normale dell'account: richiede la verifica in due passaggi
attiva, è gratuita e può essere revocata in qualsiasi momento senza
toccare la password principale.
"""
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header
from dataclasses import dataclass

from config import Config

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


@dataclass
class EmailOrdine:
    message_id: str
    mittente: str
    oggetto: str
    testo: str
    data_ricezione: str
    uid: bytes  # UID IMAP, serve per marcare l'email come processata


def _decodifica_header(valore):
    if not valore:
        return ""
    parti = decode_header(valore)
    testo = ""
    for frammento, encoding in parti:
        if isinstance(frammento, bytes):
            testo += frammento.decode(encoding or "utf-8", errors="ignore")
        else:
            testo += frammento
    return testo


def _estrai_testo_semplice(msg) -> str:
    """Estrae il corpo testuale semplice dell'email, ignorando allegati/HTML se c'è già plain text."""
    if msg.is_multipart():
        for parte in msg.walk():
            content_type = parte.get_content_type()
            disposizione = str(parte.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in disposizione:
                charset = parte.get_content_charset() or "utf-8"
                return parte.get_payload(decode=True).decode(charset, errors="ignore")
        # Fallback: nessun text/plain trovato, prova con text/html spogliato dei tag
        for parte in msg.walk():
            if parte.get_content_type() == "text/html":
                charset = parte.get_content_charset() or "utf-8"
                html = parte.get_payload(decode=True).decode(charset, errors="ignore")
                import re
                return re.sub("<[^<]+?>", " ", html)
        return ""
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="ignore")


def leggi_email_da_processare() -> list[EmailOrdine]:
    """
    Si collega a Gmail e recupera tutte le email NON LETTE presenti nella
    label configurata (Config.GMAIL_LABEL). Non le marca come lette qui:
    la marcatura avviene solo a fine elaborazione riuscita (vedi main.py),
    così un crash a metà non fa perdere email.
    """
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(Config.GMAIL_USER, Config.GMAIL_APP_PASSWORD)

    # Gmail espone le label come "cartelle" IMAP
    cartella = f'"{Config.GMAIL_LABEL}"'
    stato, _ = imap.select(cartella, readonly=False)
    if stato != "OK":
        raise RuntimeError(
            f"Impossibile aprire la label Gmail '{Config.GMAIL_LABEL}'. "
            f"Verifica che esista esattamente con questo nome (Gmail > Impostazioni > Etichette)."
        )

    stato, dati = imap.search(None, "UNSEEN")
    uids = dati[0].split()

    risultati = []
    for uid in uids:
        stato, msg_data = imap.fetch(uid, "(RFC822)")
        if stato != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])

        risultati.append(EmailOrdine(
            message_id=msg.get("Message-ID", f"<no-id-{uid.decode()}>"),
            mittente=_decodifica_header(msg.get("From", "")),
            oggetto=_decodifica_header(msg.get("Subject", "")),
            testo=_estrai_testo_semplice(msg),
            data_ricezione=msg.get("Date", ""),
            uid=uid,
        ))

    imap.logout()
    return risultati


def segna_come_processata(uid: bytes):
    """Marca l'email come letta e la sposta nella sotto-label '<label>/Processati'."""
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(Config.GMAIL_USER, Config.GMAIL_APP_PASSWORD)
    imap.select(f'"{Config.GMAIL_LABEL}"', readonly=False)

    imap.store(uid, "+FLAGS", "\\Seen")
    label_processati = f"{Config.GMAIL_LABEL}/Processati"
    imap.copy(uid, f'"{label_processati}"')

    imap.logout()


def invia_notifica(oggetto: str, corpo: str):
    """Invia un'email di riepilogo/alert al destinatario configurato."""
    msg = MIMEText(corpo, _charset="utf-8")
    msg["Subject"] = oggetto
    msg["From"] = Config.GMAIL_USER
    msg["To"] = Config.NOTIFICA_EMAIL_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(Config.GMAIL_USER, Config.GMAIL_APP_PASSWORD)
        server.sendmail(Config.GMAIL_USER, [Config.NOTIFICA_EMAIL_TO], msg.as_string())
