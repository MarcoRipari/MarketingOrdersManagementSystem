import streamlit as st
import pandas as pd
from sqlalchemy import text
import streamlit.components.v1 as components
import json
import os

from utils_scanner import live_barcode_scanner

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
            with st.container(border=True):
                st.write(f"📦 **Ordine N° {row['numero_ordine']}**")
                st.write(f"**Destinatario:** {row['cliente_nome']}")
                st.write(f"🔢 Articoli diversi da prelevare: {row['totale_righe']}")
                st.caption(f"Ricevuto il: {row['data_creazione'].strftime('%d/%m/%Y %H:%M')}")
                
                if st.button(f"⚡ Inizia Picking N° {row['numero_ordine']}", key=f"btn_take_{row['id']}", use_container_width=True):
                    try:
                        with conn.session as session:
                            res = session.execute(
                                text("""
                                    UPDATE ordini_testata
                                    SET stato = 'In Picking', data_aggiornamento = TIMEZONE('Europe/Rome', NOW())
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

    st.subheader(f"⚡ Picking in Corso: Ordine N° {ordine_info['numero_ordine']}")
    st.write(f"👤 **Destinatario:** {ordine_info['cliente_nome']}")
    if ordine_info['note']:
        st.info(f"📝 **Note Richiedente:** {ordine_info['note']}")
        
    if st.button("↩️ Rilascia Ordine (Torna indietro)", use_container_width=True):
        try:
            with conn.session as session:
                session.execute(
                    text("UPDATE ordini_testata SET stato = 'Nuovo', data_aggiornamento = TIMEZONE('Europe/Rome', NOW()) WHERE id = :id;"),
                    params={"id": id_ordine_attivo}
                )
                session.commit()
            st.session_state.ordine_in_picking_id = None
            st.session_state.righe_confermate_sessione = set()
            st.toast("Ordine rilasciato e tornato disponibile.")
            st.rerun()
        except Exception as e:
            st.error(f"Errore durante il rilascio dell'ordine: {e}")

    st.divider()

    try:
        query_righe = """
            SELECT r.id as riga_id, p.id as prodotto_id, p.barcode, p.brand, p.descrizione, p.posizione,
                   r.quantita_richiesta, r.quantita_prelevata
            FROM ordini_righe r
            JOIN prodotti p ON r.prodotto_id = p.id
            WHERE r.ordine_id = :ordine_id;
        """
        df_righe_picking = conn.query(query_righe, params={"ordine_id": id_ordine_attivo}, ttl="0")
        
        # --- IMPLEMENTAZIONE ORDINAMENTO NUMERICO PURO ---
        if not df_righe_picking.empty:
            df_righe_picking['posizione_num'] = pd.to_numeric(df_righe_picking['posizione'], errors='coerce').fillna(9999)
            df_righe_picking = df_righe_picking.sort_values(by='posizione_num').drop(columns=['posizione_num'])

    except Exception as e:
        st.error(f"Errore nel caricamento delle righe d'ordine: {e}")
        st.stop()

    st.write("##### 🗺️ Mappa del percorso di prelievo:")

    tutti_completati = True

    # --- Individua la riga attiva (la prima non ancora confermata) UNA SOLA VOLTA ---
    riga_attiva = None
    for _, riga in df_righe_picking.iterrows():
        gia_prelevato = riga['quantita_prelevata'] > 0 or riga['riga_id'] in st.session_state.righe_confermate_sessione
        if not gia_prelevato:
            tutti_completati = False
            if riga_attiva is None:
                riga_attiva = riga

    # =========================================================
    # FOTOCAMERA: istanziata UNA SOLA VOLTA, FUORI DAL CICLO SUI
    # PRODOTTI, sempre nella stessa posizione del layout e con key
    # fissa. In questo modo Streamlit riutilizza sempre lo stesso
    # iframe (niente richiesta permessi ad ogni articolo) e la
    # fotocamera resta accesa anche dopo una lettura errata
    # (il fix per lo schermo nero è nel componente scanner_v2).
    # =========================================================
    if riga_attiva is not None:
        r_id_attivo = riga_attiva['riga_id']

        # Se è cambiato l'articolo attivo, resetta l'eventuale messaggio d'errore residuo
        if st.session_state.get("riga_attiva_corrente") != r_id_attivo:
            st.session_state["riga_attiva_corrente"] = r_id_attivo
            st.session_state["err_msg_scanner"] = None

        res_scanner = live_barcode_scanner(key="live_scanner_active_item")

        if res_scanner:
            try:
                data_ricevuta = json.loads(res_scanner)
                codice_rilevato = data_ricevuta["barcode"].strip()
                timestamp_scan = data_ricevuta["ts"]

                if st.session_state.get("last_processed_ts_scanner") != timestamp_scan:
                    st.session_state["last_processed_ts_scanner"] = timestamp_scan

                    if codice_rilevato == riga_attiva['barcode'].strip():
                        st.session_state["err_msg_scanner"] = None
                        qty_effettiva = st.session_state.get(f"qty_p_{r_id_attivo}", int(riga_attiva['quantita_richiesta']))

                        with conn.session as session:
                            session.execute(
                                text("UPDATE ordini_righe SET quantita_prelevata = :q WHERE id = :id;"),
                                params={"q": qty_effettiva, "id": r_id_attivo}
                            )
                            session.execute(
                                text("UPDATE prodotti SET quantita_disponibile = GREATEST(0, quantita_disponibile - :q) WHERE id = :id;"),
                                params={"q": qty_effettiva, "id": riga_attiva['prodotto_id']}
                            )
                            session.commit()

                        st.session_state.righe_confermate_sessione.add(r_id_attivo)
                        st.toast(f"Ubicazione {riga_attiva['posizione']} prelevata correttamente!", icon="✅")
                        st.rerun()
                    else:
                        #st.session_state["err_msg_scanner"] = f"❌ Barcode errato ({codice_rilevato})! Controlla il prodotto a scaffale."
                        st.toast(f"❌ Barcode errato! Codice rilevato: ({codice_rilevato})")
                        st.rerun()
            except Exception:
                pass

    # --- Elenco righe: solo stato e input, la fotocamera NON è più qui dentro ---
    for _, riga in df_righe_picking.iterrows():
        r_id = riga['riga_id']
        gia_prelevato = riga['quantita_prelevata'] > 0 or r_id in st.session_state.righe_confermate_sessione

        with st.container(border=True):
            if gia_prelevato:
                st.write(f"🟢 **[{riga['posizione']}]** — {riga['descrizione']}")
                st.success(f"Confermato: **{int(riga['quantita_prelevata'] if riga['quantita_prelevata'] > 0 else riga['quantita_richiesta'])}** su {int(riga['quantita_richiesta'])} pz.")
            elif riga_attiva is not None and r_id == riga_attiva['riga_id']:
                st.error(f"📍 UBICAZIONE: {riga['posizione']}")
                st.write(f"**Articolo:** {riga['descrizione']} ({riga['brand'] if riga['brand'] else 'Generico'})")
                st.write(f"📋 Q.tà Richiesta: **{int(riga['quantita_richiesta'])}** pezzi")
                st.write(f"`Barcode atteso: {riga['barcode']}`")

                if st.session_state.get("err_msg_scanner"):
                    st.error(st.session_state["err_msg_scanner"])

                qty_prelevata = st.number_input(
                    "Quantità effettiva trovata a scaffale",
                    min_value=0,
                    max_value=int(riga['quantita_richiesta']),
                    value=int(riga['quantita_richiesta']),
                    step=1,
                    key=f"qty_p_{r_id}"
                )

                if qty_prelevata < riga['quantita_richiesta']:
                    st.warning("⚠️ Nota: Stai dichiarando un prelievo parziale. La quantità mancante verrà annullata.")

                bc_manuale = st.text_input("Fallback: Inserimento Manuale", key=f"manual_fallback_{r_id}", placeholder="Digita se la fotocamera ha difficoltà...")
                if bc_manuale.strip() == riga['barcode'].strip():
                    if st.button("💾 Forza Conferma Manuale", key=f"btn_manual_{r_id}", type="primary", use_container_width=True):
                        with conn.session as session:
                            session.execute(
                                text("UPDATE ordini_righe SET quantita_prelevata = :q WHERE id = :id;"),
                                params={"q": qty_prelevata, "id": r_id}
                            )
                            session.execute(
                                text("UPDATE prodotti SET quantita_disponibile = GREATEST(0, quantita_disponibile - :q) WHERE id = :id;"),
                                params={"q": qty_prelevata, "id": riga['prodotto_id']}
                            )
                            session.commit()
                        st.session_state.righe_confermate_sessione.add(r_id)
                        st.rerun()
            else:
                st.info("⏳ In attesa del completamento dell'articolo precedente nella mappa di percorso.")

    ## ====================================================
    ## FASE 3: CHIUSURA DEFINITIVA DEL PICKING + INSERIMENTO COLLI
    ## ====================================================
    st.divider()
    st.subheader("🏁 Fine Prelievo")
    
    if tutti_completati:
        st.success("👍 Tutte le righe di questo ordine sono state elaborate.")
    else:
        st.warning("⚠️ Attenzione: Ci sono ancora righe non verificate.")

    # --- INPUT NUMERO COLLI OBBLIGATORIO PRIMA DELLA CHIUSURA ---
    numero_colli = st.number_input(
        "📦 Specificare il numero di colli (scatole) totali:",
        min_value=1,
        max_value=100,
        value=1,
        step=1,
        key="picking_numero_colli"
    )

    if st.button("🏁 Chiudi Picking e Invia all'Imballo", type="primary", use_container_width=True):
        try:
            df_controllo_finale = conn.query(
                "SELECT quantita_richiesta, quantita_prelevata FROM ordini_righe WHERE ordine_id = :id", 
                params={"id": id_ordine_attivo}, 
                ttl="0"
            )
            
            ha_mancanti = any(df_controllo_finale['quantita_prelevata'] < df_controllo_finale['quantita_richiesta'])
            
            with conn.session as session:
                session.execute(
                    text("""
                        UPDATE ordini_testata
                        SET stato = 'Pronto Spedizione',
                            evaso_parziale = :evaso_parziale,
                            numero_colli = :numero_colli,
                            data_aggiornamento = TIMEZONE('Europe/Rome', NOW())
                        WHERE id = :id;
                    """),
                    params={
                        "evaso_parziale": ha_mancanti, 
                        "numero_colli": int(numero_colli), 
                        "id": id_ordine_attivo
                    }
                )
                session.commit()
            
            st.success(f"🎉 Ordine completato con successo! Registrati {numero_colli} colli.")
            st.session_state.ordine_in_picking_id = None
            st.session_state.righe_confermate_sessione = set()
            st.rerun()
            
        except Exception as e:
            st.error(f"Errore durante il salvataggio finale dell'ordine: {e}")
