import streamlit as st
import pandas as pd
from sqlalchemy import text  # 👈 Importato text per compatibilità SQLAlchemy 2.0

st.set_page_config(page_title="SGLM - Nuovo Ordine Marketing", layout="wide")

# Inizializzazione della connessione SQL
conn = st.connection("postgresql", type="sql")

st.title("🛒 Modulo B — Gestione Richieste e Ordini")

# Utilizziamo i tab per dividere la creazione di un nuovo ordine dalla modifica di quelli esistenti
tab_crea, tab_modifica = st.tabs(["➕ Crea Nuovo Ordine", "✏️ Modifica Ordine Esistente ('Nuovo')"])

## ----------------------------------------------------
## INIZIALIZZAZIONE SESSION STATE PER IL CARRELLO TEMPORANEO
## ----------------------------------------------------
if "carrello" not in st.session_state:
    st.session_state.carrello = []  # Lista di dizionari

## ----------------------------------------------------
## TAB 1: CREAZIONE NUOVO ORDINE
## ----------------------------------------------------
with tab_crea:
    st.subheader("Fase 1 — Selezione o Creazione Cliente")
    
    try:
        df_clienti = conn.query("SELECT id, nome, indirizzo, citta FROM clienti ORDER BY nome;", ttl="0")
    except Exception as e:
        st.error("Errore nel caricamento dell'anagrafica clienti.")
        st.stop()
        
    opzioni_cliente = {"-- Seleziona un cliente esistente --": None}
    for _, row in df_clienti.iterrows():
        opzioni_cliente[f"{row['nome']} ({row['citta']} - {row['indirizzo']})"] = row['id']
        
    cliente_scelto = st.selectbox("Seleziona il Destinatario della spedizione", list(opzioni_cliente.keys()))
    cliente_id = opzioni_cliente[cliente_scelto]
    
    with st.expander("➕ Il cliente non esiste? Crealo ora al volo"):
        with st.form("form_rapido_cliente", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                c_nome = st.text_input("Ragione Sociale / Nome *")
                c_ind = st.text_input("Indirizzo di Spedizione *")
                c_citta = st.text_input("Città *")
            with col2:
                c_cap = st.text_input("CAP *")
                c_naz = st.text_input("Nazione *", value="Italia")
                c_mail = st.text_input("Email di contatto (Opzionale)")
            c_note = st.text_area("Note Destinatario (es. Orari di consegna)")
            
            submit_c = st.form_submit_button("Registra Cliente")
            if submit_c:
                if not c_nome or not c_ind or not c_citta or not c_cap:
                    st.error("Compila tutti i campi obbligatori del cliente (*)")
                else:
                    try:
                        with conn.session as session:
                            session.execute(
                                text("""
                                INSERT INTO clienti (nome, indirizzo, citta, cap, nazione, email, note)
                                VALUES (:nome, :ind, :citta, :cap, :naz, :email, :note);
                                """),
                                params={"nome": c_nome, "ind": c_ind, "citta": c_citta, "cap": c_cap, "naz": c_naz, "email": c_mail if c_mail else None, "note": c_note if c_note else None}
                            )
                            session.commit()
                        st.success(f"Cliente '{c_nome}' registrato con successo! Ora puoi selezionarlo nel menu sopra.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'inserimento del cliente: {e}")

    st.divider()
    st.subheader("Fase 2 — Composizione Carrello")
    
    try:
        df_prodotti = conn.query("SELECT id, barcode, descrizione, brand, quantita_disponibile, posizione FROM prodotti WHERE quantita_disponibile > 0 ORDER BY descrizione;", ttl="0")
    except Exception as e:
        st.error("Errore nel caricamento dei prodotti.")
        st.stop()
        
    if df_prodotti.empty:
        st.warning("Non ci sono prodotti con giacenza disponibile nel magazzino in questo momento.")
    else:
        col_p, col_q, col_b = st.columns([5, 2, 2])
        
        opzioni_prodotti = {}
        for _, row in df_prodotti.iterrows():
            opzioni_prodotti[f"[{row['barcode']}] {row['descrizione']} (Disponibili: {row['quantita_disponibile']} in {row['posizione']})"] = row
            
        prodotto_selezionato_testo = col_p.selectbox("Scegli l'articolo da aggiungere", list(opzioni_prodotti.keys()))
        prodotto_row = opzioni_prodotti[prodotto_selezionato_testo]
        
        qty_richiesta = col_q.number_input("Quantità", min_value=1, max_value=int(prodotto_row['quantita_disponibile']), value=1, step=1)
        
        if col_b.button("🛒 Aggiungi Riga", use_container_width=True):
            gia_presente = False
            for item in st.session_state.carrello:
                if item["prodotto_id"] == prodotto_row["id"]:
                    nuova_totale = item["quantita"] + qty_richiesta
                    if nuova_totale <= prodotto_row['quantita_disponibile']:
                        item["quantita"] = nuova_totale
                        gia_presente = True
                        st.toast("Quantità aggiornata nel carrello!")
                    else:
                        st.error(f"Impossibile aggiungere: il totale supererebbe la disponibilità di magazzino ({prodotto_row['quantita_disponibile']}).")
                        gia_presente = True
            
            if not gia_presente:
                st.session_state.carrello.append({
                    "prodotto_id": prodotto_row["id"],
                    "barcode": prodotto_row["barcode"],
                    "descrizione": prodotto_row["descrizione"],
                    "quantita": qty_richiesta
                })
                st.toast("Articolo aggiunto al carrello!")
                st.rerun()

    if st.session_state.carrello:
        st.write("### Righe incluse nella richiesta corrente:")
        df_carrello = pd.DataFrame(st.session_state.carrello)
        
        if st.button("❌ Svuota interamente il carrello"):
            st.session_state.carrello = []
            st.rerun()
            
        st.dataframe(df_carrello[["barcode", "descrizione", "quantita"]], use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("Fase 3 — Informazioni di Invio")
        note_ordine = st.text_area("Note aggiuntive per l'ordine (opzionali)", placeholder="Es. Consegnare tassativamente")
        
        if st.button("🚀 Invia Ordine Definitivo al Magazzino", type="primary"):
            if not cliente_id:
                st.error("Seleziona un cliente valido nella Fase 1.")
            else:
                try:
                    with conn.session as session:
                        # 1. Inserisce la testata dell'ordine (con text())
                        res = session.execute(
                            text("""
                            INSERT INTO ordini_testata (cliente_id, note, stato)
                            VALUES (:cliente_id, :note, 'Nuovo')
                            RETURNING id;
                            """),
                            params={"cliente_id": cliente_id
                                    , "note": note_ordine if note_ordine else None}
                        )
                        ordine_id_nuovo = res.fetchone()[0]
                        
                        # 2. Inserisce tutte le righe (con text())
                        for item in st.session_state.carrello:
                            session.execute(
                                text("""
                                INSERT INTO ordini_righe (ordine_id, prodotto_id, quantita_richiesta)
                                VALUES (:ordine_id, :prodotto_id, :qty);
                                """),
                                params={"ordine_id": ordine_id_nuovo, "prodotto_id": item["prodotto_id"], "qty": item["quantita"]}
                            )
                        session.commit()
                        
                    st.success("🎉 Ordine registrato con successo! Inviato al magazzino.")
                    st.session_state.carrello = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore transazionale nel salvataggio dell'ordine: {e}")
    else:
        st.info("Il carrello è vuoto. Seleziona un articolo sopra per iniziare la composizione.")


## ----------------------------------------------------
## TAB 2: MODIFICA ORDINE ESISTENTE (Solo se in stato 'Nuovo')
## ----------------------------------------------------
with tab_modifica:
    st.subheader("Gestione e Modifica Richieste Pendenti")
    
    try:
        query_ordini = """
            SELECT t.id, t.numero_ordine, c.nome as cliente_nome, t.data_creazione
            FROM ordini_testata t
            JOIN clienti c ON t.cliente_id = c.id
            WHERE t.stato = 'Nuovo'
            ORDER BY t.numero_ordine DESC;
        """
        df_ordini_nuovi = conn.query(query_ordini, ttl="0")
    except Exception as e:
        st.error("Errore nel recupero degli ordini modificabili.")
        st.stop()
        
    if df_ordini_nuovi.empty:
        st.info("Non ci sono ordini in stato 'Nuovo' modificabili al momento.")
    else:
        opzioni_ordini = {"-- Seleziona un ordine da modificare --": None}
        for _, row in df_ordini_nuovi.iterrows():
            opzioni_ordini[f"Ordine N° {row['numero_ordine']} - Per: {row['cliente_nome']}"] = row['id']
            
        ordine_selezionato_id = st.selectbox("Scegli l'ordine da visionare/modificare", list(opzioni_ordini.keys()))
        id_ordine_target = opzioni_ordini[ordine_selezionato_id]
        
        if id_ordine_target:
            query_righe = """
                SELECT r.id as riga_id, p.id as prodotto_id, p.barcode, p.descrizione, r.quantita_richiesta, p.quantita_disponibile
                FROM ordini_righe r
                JOIN prodotti p ON r.prodotto_id = p.id
                WHERE r.ordine_id = :ordine_id
            """
            df_righe_target = conn.query(query_righe, params={"ordine_id": id_ordine_target}, ttl="0")
            
            st.write("#### Righe dell'ordine:")
            
            with st.form("form_modifica_ordine"):
                cambiamenti = {}
                cancellazioni = []
                
                for _, riga in df_righe_target.iterrows():
                    col_b, col_d, col_q, col_del = st.columns([2, 4, 2, 1])
                    col_b.write(f"`{riga['barcode']}`")
                    col_d.write(riga['descrizione'])
                    
                    max_consentito = int(riga['quantita_disponibile'] + riga['quantita_richiesta'])
                    nuova_qty = col_q.number_input(
                        f"Q.tà (Max {max_consentito})",
                        min_value=1,
                        max_value=max_consentito,
                        value=int(riga['quantita_richiesta']),
                        key=f"qty_{riga['riga_id']}"
                    )
                    
                    elimina = col_del.checkbox("❌", key=f"del_{riga['riga_id']}")
                    
                    if elimina:
                        cancellazioni.append(riga['riga_id'])
                    elif nuova_qty != riga['quantita_richiesta']:
                        cambiamenti[riga['riga_id']] = nuova_qty
                        
                st.write("⚠️ *Nota: Se elimini tutte le righe, l'ordine rimarrà vuoto.*")
                
                btn_salva_modifiche = st.form_submit_button("Salva Modifiche Ordine", type="primary")
                
                if btn_salva_modifiche:
                    try:
                        with conn.session as session:
                            # 1. Cancellazioni (con text())
                            for riga_id in cancellazioni:
                                session.execute(text("DELETE FROM ordini_righe WHERE id = :id"), params={"id": riga_id})
                            # 2. Aggiornamenti (con text())
                            for riga_id, qta in cambiamenti.items():
                                session.execute(text("UPDATE ordini_righe SET quantita_richiesta = :qta WHERE id = :id"), params={"qta": qta, "id": riga_id})
                            session.commit()
                        st.success("Ordine aggiornato con successo!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'aggiornamento dell'ordine: {e}")
