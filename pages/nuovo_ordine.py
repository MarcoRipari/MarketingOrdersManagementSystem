import streamlit as st
import pandas as pd
from sqlalchemy import text  # Importato text per compatibilità SQLAlchemy 2.0

st.set_page_config(page_title="SGLM - Nuovo Ordine Marketing", layout="wide")

# Inizializzazione della connessione SQL
conn = st.connection("postgresql", type="sql")

st.title("🛒 Modulo B — Gestione Richieste e Ordini")

# ----------------------------------------------------
# CARICAMENTO ANAGRAFICA CLIENTI (Globale con i nuovi codici)
# ----------------------------------------------------
try:
    df_clienti = conn.query("""
        SELECT id, nome, indirizzo, citta, nazione, 
               COALESCE(codice_cliente, '0000000') as codice_cliente, 
               COALESCE(codice_destinazione, '000') as codice_destinazione 
        FROM clienti 
        ORDER BY nome;
    """, ttl="0")
except Exception as e:
    st.error("Errore nel caricamento dell'anagrafica clienti.")
    st.stop()

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
    
    # --- BARRA DI FILTRO AVANZATA ---
    search_cli_t1 = st.text_input("🔍 Cerca Cliente (Filtra per Nome, Cod. Cliente o Nazione):", key="search_cli_t1", placeholder="Es. 1234567, Italia, Rossi...")
    
    if search_cli_t1:
        df_clienti_filtrati_t1 = df_clienti[
            df_clienti['nome'].str.contains(search_cli_t1, case=False, na=False) |
            df_clienti['codice_cliente'].str.contains(search_cli_t1, case=False, na=False) |
            df_clienti['nazione'].str.contains(search_cli_t1, case=False, na=False)
        ]
    else:
        df_clienti_filtrati_t1 = df_clienti

    opzioni_cliente = {"-- Seleziona un cliente esistente --": None}
    for _, row in df_clienti_filtrati_t1.iterrows():
        # Formato richiesto: [CLI DEST] Nome completo + dettagli spedizione
        label = f"[{row['codice_cliente']} {row['codice_destinazione']}] {row['nome']} ({row['citta']} - {row['indirizzo']})"
        opzioni_cliente[label] = row['id']
        
    cliente_scelto = st.selectbox("Seleziona il Destinatario della spedizione", list(opzioni_cliente.keys()))
    cliente_id = opzioni_cliente[cliente_scelto]
    
    with st.expander("➕ Il cliente non esiste? Crealo ora al volo"):
        with st.form("form_rapido_cliente", clear_on_submit=True):
            st.write("##### 🆔 Codici Gestionali Aziendali")
            col_cod1, col_cod2 = st.columns(2)
            with col_cod1:
                c_cod_cli = st.text_input("Cod. Cliente (7 cifre) *", max_chars=7, placeholder="Es. 1234567")
            with col_cod2:
                c_cod_dest = st.text_input("Cod. Destinazione (3 cifre) *", max_chars=3, placeholder="Es. 001")
                
            st.write("##### 📍 Dati Anagrafici e Spedizione")
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
                if not c_nome or not c_ind or not c_citta or not c_cap or not c_cod_cli or not c_cod_dest:
                    st.error("Compila tutti i campi obbligatori del cliente (*), inclusi i codici gestionali.")
                elif len(c_cod_cli) != 7 or not c_cod_cli.isdigit():
                    st.error("Il Codice Cliente deve essere composto esattamente da 7 cifre numeriche.")
                elif len(c_cod_dest) != 3 or not c_cod_dest.isdigit():
                    st.error("Il Codice Destinazione deve essere composto esattamente da 3 cifre numeriche.")
                else:
                    try:
                        with conn.session as session:
                            session.execute(
                                text("""
                                INSERT INTO clienti (nome, indirizzo, citta, cap, nazione, email, note, codice_cliente, codice_destinazione)
                                VALUES (:nome, :ind, :citta, :cap, :naz, :email, :note, :cod_cli, :cod_dest);
                                """),
                                params={
                                    "nome": c_nome, "ind": c_ind, "citta": c_citta, "cap": c_cap, "naz": c_naz, 
                                    "email": c_mail if c_mail else None, "note": c_note if c_note else None,
                                    "cod_cli": c_cod_cli, "cod_dest": c_cod_dest
                                }
                            )
                            session.commit()
                        st.success(f"Cliente '{c_nome}' registrato con successo con codice [{c_cod_cli} {c_cod_dest}]!")
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
            opzioni_prodotti[f"{row['brand']} - {row['descrizione']} (Disponibili: {row['quantita_disponibile']})"] = row
            
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
                        res = session.execute(
                            text("""
                            INSERT INTO ordini_testata (cliente_id, note, stato)
                            VALUES (:cliente_id, :note, 'Nuovo')
                            RETURNING id;
                            """),
                            params={"cliente_id": cliente_id, "note": note_ordine if note_ordine else None}
                        )
                        ordine_id_nuovo = res.fetchone()[0]
                        
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
        # Recuperiamo anche i codici cliente per formattare il selettore ordini
        query_ordini = """
            SELECT t.id, t.numero_ordine, t.cliente_id, c.nome as cliente_nome, 
                   COALESCE(c.codice_cliente, '0000000') as codice_cliente, 
                   COALESCE(c.codice_destinazione, '000') as codice_destinazione,
                   t.data_creazione
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
            opzioni_ordini[f"Ordine N° {row['numero_ordine']} - Per: [{row['codice_cliente']} {row['codice_destinazione']}] {row['cliente_nome']}"] = row['id']
            
        ordine_selezionato_id = st.selectbox("Scegli l'ordine da visionare/modificare", list(opzioni_ordini.keys()))
        id_ordine_target = opzioni_ordini[ordine_selezionato_id]
        
        if id_ordine_target:
            ordine_corrente_row = df_ordini_nuovi[df_ordini_nuovi['id'] == id_ordine_target].iloc[0]
            id_cliente_attuale = ordine_corrente_row['cliente_id']

            # 1. Recupera le righe dell'ordine
            query_righe = """
                SELECT r.id as riga_id, p.id as prodotto_id, p.barcode, p.descrizione, r.quantita_richiesta, p.quantita_disponibile
                FROM ordini_righe r
                JOIN prodotti p ON r.prodotto_id = p.id
                WHERE r.ordine_id = :ordine_id
            """
            df_righe_target = conn.query(query_righe, params={"ordine_id": id_ordine_target}, ttl="0")
            
            # 2. Recupera tutti i prodotti per l'aggiunta extra
            try:
                df_prodotti_all = conn.query("SELECT id, barcode, descrizione, brand, quantita_disponibile, posizione FROM prodotti WHERE quantita_disponibile > 0 ORDER BY descrizione;", ttl="0")
            except Exception as e:
                st.error("Errore nel caricamento del catalogo prodotti per l'aggiunta.")
                df_prodotti_all = pd.DataFrame()

            prodotti_gia_presenti = df_righe_target['prodotto_id'].tolist() if not df_righe_target.empty else []
            df_prodotti_filtrati = df_prodotti_all[~df_prodotti_all['id'].isin(prodotti_gia_presenti)] if not df_prodotti_all.empty else pd.DataFrame()
            
            # --- FORM DI MODIFICA COMPLESSIVO ---
            with st.form("form_modifica_ordine"):
                st.write("#### 👤 Anagrafica Destinatario Spedizione")
                
                # Barra filtro per il cambio cliente all'interno del form di modifica
                search_cli_t2 = st.text_input("🔍 Filtra la lista dei clienti sostitutivi (Nome, Codice, Nazione):", placeholder="Scrivi qui per accorciare la lista sotto...")
                
                if search_cli_t2:
                    df_clienti_filtrati_t2 = df_clienti[
                        df_clienti['nome'].str.contains(search_cli_t2, case=False, na=False) |
                        df_clienti['codice_cliente'].str.contains(search_cli_t2, case=False, na=False) |
                        df_clienti['nazione'].str.contains(search_cli_t2, case=False, na=False)
                    ]
                else:
                    df_clienti_filtrati_t2 = df_clienti
                
                lista_nomi_clienti = []
                mappa_clienti_mod = {}
                default_idx = 0
                
                for idx_c, r_c in df_clienti_filtrati_t2.iterrows():
                    testo_c = f"[{r_c['codice_cliente']} {r_c['codice_destinazione']}] {r_c['nome']} ({r_c['citta']})"
                    lista_nomi_clienti.append(testo_c)
                    mappa_clienti_mod[testo_c] = r_c['id']
                    if r_c['id'] == id_cliente_attuale:
                        default_idx = len(lista_nomi_clienti) - 1
                
                if not lista_nomi_clienti:
                    st.warning("Nessun cliente corrisponde al filtro inserito.")
                    id_nuovo_cliente = id_cliente_attuale
                else:
                    # Se il cliente attuale è stato escluso dai filtri di ricerca, impostiamo l'indice a 0
                    if default_idx >= len(lista_nomi_clienti) or default_idx < 0:
                        default_idx = 0
                    nuovo_cliente_scelto = st.selectbox("Assegna l'ordine a:", lista_nomi_clienti, index=default_idx, key=f"cli_mod_{id_ordine_target}")
                    id_nuovo_cliente = mappa_clienti_mod[nuovo_cliente_scelto]

                st.divider()
                st.write("#### 📦 Righe attuali dell'ordine:")
                
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
                
                # AGGIUNTA ARTICOLO EXTRA
                st.divider()
                st.write("➕ **Aggiungi un nuovo articolo a questo ordine:**")
                
                opzioni_nuovo_p = {"-- Seleziona un articolo da aggiungere (Opzionale) --": None}
                if not df_prodotti_filtrati.empty:
                    for _, row in df_prodotti_filtrati.iterrows():
                        opzioni_nuovo_p[f"[{row['barcode']}] {row['descrizione']} (Disponibili: {row['quantita_disponibile']} in {row['posizione']})"] = row
                
                col_np, col_nq = st.columns([6, 3])
                nuovo_p_testo = col_np.selectbox("Scegli l'articolo extra", list(opzioni_nuovo_p.keys()), key=f"new_p_{id_ordine_target}")
                nuovo_p_row = opzioni_nuovo_p[nuovo_p_testo]
                
                max_q_extra = int(nuovo_p_row['quantita_disponibile']) if nuovo_p_row is not None else 1
                nuova_p_qty = col_nq.number_input("Quantità extra", min_value=1, max_value=max_q_extra, value=1, step=1, key=f"new_q_{id_ordine_target}", disabled=(nuovo_p_row is None))
                
                st.write("")
                btn_salva_modifiche = st.form_submit_button("Salva Modifiche Ordine (Applica tutto)", type="primary")
                
                if btn_salva_modifiche:
                    try:
                        with conn.session as session:
                            if id_nuovo_cliente != id_cliente_attuale:
                                session.execute(
                                    text("UPDATE ordini_testata SET cliente_id = :cli_id WHERE id = :id;"),
                                    params={"cli_id": id_nuovo_cliente, "id": id_ordine_target}
                                )
                            for riga_id in cancellazioni:
                                session.execute(text("DELETE FROM ordini_righe WHERE id = :id"), params={"id": riga_id})
                            for riga_id, qta in cambiamenti.items():
                                session.execute(text("UPDATE ordini_righe SET quantita_richiesta = :qta WHERE id = :id"), params={"qta": qta, "id": riga_id})
                            if  nuovo_p_row is not None:
                                session.execute(
                                    text("""
                                    INSERT INTO ordini_righe (ordine_id, prodotto_id, quantita_richiesta)
                                    VALUES (:ordine_id, :prodotto_id, :qty);
                                    """),
                                    params={"ordine_id": id_ordine_target, "prodotto_id": nuovo_p_row["id"], "qty": nuova_p_qty}
                                )
                            session.commit()
                        st.success("Ordine aggiornato con successo!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'aggiornamento dell'ordine: {e}")

            # --- SEZIONE DISTRUTTIVA: CANCELLAZIONE TOTALE ORDINE ---
            st.write("")
            with st.expander("🚨 Zona Pericolo — Elimina Interamente l'Ordine"):
                st.warning("Attenzione! Questa azione è irreversibile.")
                conferma_cancellazione = st.checkbox("Confermo di voler eliminare ed eliminare del tutto questo ordine", key=f"conf_del_{id_ordine_target}")
                
                if st.button("🗑️ Elimina Ordine e Fallo Sparire", type="primary", disabled=not conferma_cancellazione, key=f"btn_del_{id_ordine_target}"):
                    try:
                        with conn.session as session:
                            session.execute(text("DELETE FROM ordini_righe WHERE ordine_id = :id;"), params={"id": id_ordine_target})
                            session.execute(text("DELETE FROM ordini_testata WHERE id = :id;"), params={"id": id_ordine_target})
                            session.commit()
                        st.success("Ordine eliminato con successo. È sparito dal sistema!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'eliminazione dell'ordine: {e}")
