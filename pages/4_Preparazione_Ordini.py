import streamlit as st
import pandas as pd
from sqlalchemy import text

# Configurazione ottimizzata per mobile/desktop di magazzino
st.set_page_config(page_title="SGLM - Picking Mobile", layout="centered")

# Inizializzazione della connessione SQL (Supabase Pooler via porta 6543)
conn = st.connection("postgresql", type="sql")

st.title("📱 Modulo C — Picking Mobile")

## ----------------------------------------------------
## INIZIALIZZAZIONE SESSION STATE PER L'ORDINE IN CORSO
## ----------------------------------------------------
if "ordine_in_picking_id" not in st.session_state:
    st.session_state.ordine_in_picking_id = None

if "righe_confermate_sessione" not in st.session_state:
    st.session_state.righe_confermate_sessione = set()


## ====================================================
## FASE 1: SELEZIONE DELL'ORDINE DA PRENDERE IN CARICO
## ====================================================
if st.session_state.ordine_in_picking_id is None:
    st.subheader("📋 Ordini Pendenti in attesa di Picking")
    
    try:
        # Recupera solo gli ordini in stato 'Nuovo'
        query_nuovi = """
            SELECT t.id, t.numero_ordine, c.nome as cliente_nome, t.data_creazione,
                   (SELECT COUNT(*) FROM ordini_righe WHERE ordine_id = t.id) as totale_righe
            FROM ordini_testata t
            JOIN clienti c ON t.cliente_id = c.id
            WHERE t.stato = 'Nuovo'
            ORDER BY t.data_creazione ASC;
        """
        df_nuovi = conn.query(query_nuovi, ttl="0")
    except Exception as e:
        st.error(f"Errore nel recupero degli ordini: {e}")
        st.stop()

    if df_nuovi.empty:
        st.info("🎉 Ottimo! Non ci sono ordini in attesa di picking in questo momento.")
    else:
        st.write("Seleziona un ordine per iniziare il percorso di prelievo guidato:")
        
        for _, row in df_nuovi.iterrows():
            # Card compatta per visualizzazione da smartphone
            with st.container(border=True):
                st.write(f"📦 **Ordine N° {row['numero_ordine']}**")
                st.write(f"**Destinatario:** {row['cliente_nome']}")
                st.write(f"🔢 Articoli diversi da prelevare: {row['totale_righe']}")
                st.caption(f"Ricevuto il: {row['data_creazione'].strftime('%d/%m/%Y %H:%M')}")
                
                # Bottone di presa in carico con gestione atomica della concorrenza
                if st.button(f"⚡ Inizia Picking N° {row['numero_ordine']}", key=f"btn_take_{row['id']}", use_container_width=True):
                    try:
                        with conn.session as session:
                            # QUERY ATOMICA (§5.3 PRD): Aggiorna solo se lo stato è ancora 'Nuovo'
                            res = session.execute(
                                text("""
                                    UPDATE ordini_testata
                                    SET stato = 'In Picking', data_aggiornamento = NOW()
                                    WHERE id = :ordine_id AND stato = 'Nuovo'
                                    RETURNING id;
                                """),
                                params={"ordine_id": row['id']}
                            )
                            righe_modificate = res.fetchall()
                            session.commit()
                        
                        if righe_modificate:
                            st.session_state.ordine_in_picking_id = row['id']
                            st.session_state.righe_confermate_sessione = set()
                            st.success("Ordine preso in carico!")
                            st.rerun()
                        else:
                            st.error("⚠️ Errore: Questo ordine è appena stato preso in carico da un altro operatore.")
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"Errore transazionale di assegnazione: {e}")

## ====================================================
## FASE 2: PERCORSO GUIDATO DI PRELIEVO (ORDINE ATTIVO)
## ====================================================
else:
    id_ordine_attivo = st.session_state.ordine_in_picking_id
    
    try:
        # Recupera i dati di testata dell'ordine corrente
        ordine_info = conn.query("""
            SELECT t.numero_ordine, c.nome as cliente_nome, t.note
            FROM ordini_testata t
            JOIN clienti c ON t.cliente_id = c.id
            WHERE t.id = :id;
        """, params={"id": id_ordine_attivo}, ttl="0").iloc[0]
    except Exception as e:
        st.error("Errore nel caricamento dell'ordine attivo. Rilascio in corso...")
        st.session_state.ordine_in_picking_id = None
        st.stop()

    # Intestazione fissa del Picking
    st.subheader(f"⚡ Picking in Corso: Ordine N° {ordine_info['numero_ordine']}")
    st.write(f"👤 **Destinatario:** {ordine_info['cliente_nome']}")
    if ordine_info['note']:
        st.info(f"📝 **Note Richiedente:** {ordine_info['note']}")
        
    # Bottone di rilascio d'emergenza
    if st.button("↩️ Rilascia Ordine (Torna indietro)", use_container_width=True):
        try:
            with conn.session as session:
                session.execute(
                    text("UPDATE ordini_testata SET stato = 'Nuovo', data_aggiornamento = NOW() WHERE id = :id;"),
                    params={"id": id_ordine_attivo}
                )
                session.commit()
            st.session_state.ordine_in_picking_id = None
            st.session_state.righe_confermate_sessione = set()
            st.toast("Ordine rilasciato e tornato disponibile per altri operatori.")
            st.rerun()
        except Exception as e:
            st.error(f"Errore durante il rilascio dell'ordine: {e}")

    st.divider()

    try:
        # RECUPERO RIGHE ORDINATE ALFABETICAMENTE PER POSIZIONE (§4 PRD)
        query_righe = """
            SELECT r.id as riga_id, p.id as prodotto_id, p.barcode, p.brand, p.descrizione, p.posizione,
                   r.quantita_richiesta, r.quantita_prelevata
            FROM ordini_righe r
            JOIN prodotti p ON r.prodotto_id = p.id
            WHERE r.ordine_id = :ordine_id
            ORDER BY p.posizione ASC;
        """
        df_righe_picking = conn.query(query_righe, params={"ordine_id": id_ordine_attivo}, ttl="0")
    except Exception as e:
        st.error(f"Errore nel caricamento delle righe d'ordine: {e}")
        st.stop()

    st.write("##### 🗺️ Mappa del percorso di prelievo:")
    
    tutti_completati = True
    
    for _, riga in df_righe_picking.iterrows():
        r_id = riga['riga_id']
        
        # Consideriamo completata la riga se salvata in questa sessione o se ha già un prelievo registrato a DB
        gia_prelevato = riga['quantita_prelevata'] > 0 or r_id in st.session_state.righe_confermate_sessione
        
        if not gia_prelevato:
            tutti_completati = False

        # Generazione UI condizionale basata sullo stato del prelievo della riga
        with st.container(border=True):
            if gia_prelevato:
                # Riga Evasa: Visualizzazione contratta/pulita per non intasare lo schermo mobile
                st.write(f"🟢 **[{riga['posizione']}]** — {riga['descrizione']}")
                st.success(f"Confermato: **{int(riga['quantita_prelevata'] if riga['quantita_prelevata'] > 0 else riga['quantita_richiesta'])}** su {int(riga['quantita_richiesta'])} pz.")
            else:
                # Riga da Evare: Evidenziazione forte dell'ubicazione fisica a scaffale
                st.error(f"📍 UBICAZIONE: {riga['posizione']}")
                st.write(f"**Articolo:** {riga['descrizione']} ({riga['brand'] if riga['brand'] else 'Generico'})")
                st.write(f"📋 Q.tà Richiesta: **{int(riga['quantita_richiesta'])}** pezzi")
                st.code(f"Barcode atteso: {riga['barcode']}", language="markdown")
                
                # --- FUNZIONE DI AUTO-SUBMIT AL CAMBIO DEL TESTO (OTTIMIZZAZIONE VELOCITÀ) ---
                # Questa funzione viene attivata IMMEDIATAMENTE quando la tastiera inserisce il codice e preme Invio
                def esegui_auto_picking(id_riga=r_id, id_prod=riga['prodotto_id'], bc_atteso=riga['barcode'], q_richiesta=riga['quantita_richiesta'], pos=riga['posizione']):
                    input_utente = st.session_state[f"scan_{id_riga}"].strip()
                    
                    if input_utente == bc_atteso.strip():
                        try:
                            # Se l'operatore ha modificato manualmente la quantità nel campo numerico prima di sparare, usiamo quella.
                            # Altrimenti, di default, consideriamo l'intero lotto richiesto prelevato con successo.
                            qty_effettiva = st.session_state.get(f"qty_p_{id_riga}", int(q_richiesta))
                            
                            with conn.session as session:
                                # 1. Aggiorna la riga dell'ordine
                                session.execute(
                                    text("UPDATE ordini_righe SET quantita_prelevata = :q WHERE id = :id;"),
                                    params={"q": qty_effettiva, "id": id_riga}
                                )
                                # 2. Decrementa lo stock
                                session.execute(
                                    text("UPDATE prodotti SET quantita_disponibile = GREATEST(0, quantita_disponibile - :q) WHERE id = :id;"),
                                    params={"q": qty_effettiva, "id": id_prod}
                                )
                                session.commit()
                            
                            st.session_state.righe_confermate_sessione.add(id_riga)
                            st.toast(f"🎯 UBICAZIONE {pos} EVASA CON SUCCESSO!", icon="✅")
                        except Exception as e:
                            st.error(f"Errore nel salvataggio automatico: {e}")
                    elif input_utente != "":
                        st.toast(f"❌ Barcode Errato per l'ubicazione {pos}!", icon="🚨")

                # Input Barcode con callback ad attivazione immediata
                bc_input = st.text_input(
                    "Scansiona Barcode per Sbloccare", 
                    key=f"scan_{r_id}", 
                    placeholder="Spara il codice qui...",
                    on_change=esegui_auto_picking,
                    help="Usa la tastiera-fotocamera. Se il codice è corretto, la riga si salva da sola!"
                )
                
                # Validazione formale visiva (se l'operatore scrive senza premere subito invio)
                barcode_valido = (bc_input.strip() == riga['barcode'].strip())
                
                if bc_input and not barcode_valido:
                    st.error("❌ Barcode errato! Controlla di aver preso l'articolo corretto.")
                
                # Input quantità: visibile come opzione/fallback o per gestire le anomalie (es. giacenza parziale)
                qty_prelevata = st.number_input(
                    "Quantità effettiva trovata a scaffale",
                    min_value=0,
                    max_value=int(riga['quantita_richiesta']),
                    value=int(riga['quantita_richiesta']),
                    step=1,
                    key=f"qty_p_{r_id}"
                )
                
                if barcode_valido and qty_prelevata < riga['quantita_richiesta']:
                    st.warning("⚠️ Nota: Stai dichiarando un prelievo parziale. La quantità mancante verrà annullata definitivamente.")

                # Il bottone manuale resta come paracadute di sicurezza se l'operatore non usa l'invio automatico
                if st.button("💾 Conferma Riga Manuale", key=f"btn_save_{r_id}", disabled=not barcode_valido, type="secondary", use_container_width=True):
                    esegui_auto_picking()
                    st.rerun()

    # ====================================================
    # FASE 3: CHIUSURA DEFINITIVA DEL PICKING
    # ====================================================
    st.divider()
    st.subheader("🏁 Fine Prelievo")
    
    if tutti_completati:
        st.success("👍 Tutte le righe di questo ordine sono state elaborate.")
    else:
        st.warning("⚠️ Attenzione: Ci sono ancora righe non verificate. Puoi comunque chiudere il picking, ma le righe non salvate verranno considerate a zero pezzi.")

    if st.button("🏁 Chiudi Picking e Invia all'Imballo", type="primary", use_container_width=True):
        try:
            # Recuperiamo lo stato aggiornato delle righe per calcolare se l'ordine è 'evaso_parziale'
            df_controllo_finale = conn.query(
                "SELECT quantita_richiesta, quantita_prelevata FROM ordini_righe WHERE ordine_id = :id", 
                params={"id": id_ordine_attivo}, 
                ttl="0"
            )
            
            # Controllo flag evasione parziale (§5.1 PRD)
            ha_mancanti = any(df_controllo_finale['quantita_prelevata'] < df_controllo_finale['quantita_richiesta'])
            
            with conn.session as session:
                session.execute(
                    text("""
                        UPDATE ordini_testata
                        SET stato = 'Pronto Spedizione',
                            evaso_parziale = :evaso_parziale,
                            data_aggiornamento = NOW()
                        WHERE id = :id;
                    """),
                    params={"evaso_parziale": ha_mancanti, "id": id_ordine_attivo}
                )
                session.commit()
            
            st.success("🎉 Ordine completato con successo e trasferito al Banco Imballo!")
            # Reset dello stato per il prossimo picking
            st.session_state.ordine_in_picking_id = None
            st.session_state.righe_confermate_sessione = set()
            st.rerun()
            
        except Exception as e:
            st.error(f"Errore durante il salvataggio finale dell'ordine: {e}")
