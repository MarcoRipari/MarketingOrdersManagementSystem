import streamlit as st
import pandas as pd
from sqlalchemy import text

# Configurazione Desktop per il banco imballo
#st.set_page_config(page_title="SGLM - Banco Imballo & Spedizione", layout="wide")

# Inizializzazione della connessione SQL
conn = st.connection("postgresql", type="sql")

st.title("📦 Modulo D — Banco Imballo e Spedizione")

# ----------------------------------------------------
# 1. RECUPERO ORDINI PRONTI PER L'IMBALLO
# ----------------------------------------------------
try:
    query_pronti = """
        SELECT t.id, t.numero_ordine, t.cliente_id, c.nome as cliente_nome, 
               COALESCE(c.codice_cliente, '0000000') as codice_cliente, 
               COALESCE(c.codice_destinazione, '000') as codice_destinazione,
               c.indirizzo, c.citta, c.cap, c.nazione,
               t.note, t.evaso_parziale, t.data_aggiornamento as data_picking,
               t.numero_colli  -- Agganciato il dato inserito al picking
        FROM ordini_testata t
        JOIN clienti c ON t.cliente_id = c.id
        WHERE t.stato = 'Pronto Spedizione'
        ORDER BY t.data_aggiornamento ASC;
    """
    df_pronti = conn.query(query_pronti, ttl="0")
except Exception as e:
    st.error(f"Errore nel recupero degli ordini pronti per la spedizione: {e}")
    st.stop()

# ----------------------------------------------------
# LOGICA DI SELEZIONE DELL'ORDINE AL BANCO
# ----------------------------------------------------
if df_pronti.empty:
    st.info("📦 Nessun ordine in attesa di imballo al banco in questo momento. Ottimo lavoro!")
else:
    # Creazione delle opzioni per il selettore
    opzioni_imballo = {"-- Seleziona un ordine da elaborare --": None}
    for _, row in df_pronti.iterrows():
        label_parziale = " [⚠️ EVASO PARZIALE]" if row['evaso_parziale'] else ""
        label = f"Ordine N° {row['numero_ordine']} - Per: [{row['codice_cliente']} {row['codice_destinazione']}] {row['cliente_nome']}{label_parziale}"
        opzioni_imballo[label] = row['id']
        
    ordine_scelto = st.selectbox("📋 Seleziona la spedizione da preparare:", list(opzioni_imballo.keys()))
    id_ordine_target = opzioni_imballo[ordine_scelto]
    
    if id_ordine_target:
        # Estraiamo i dettagli dell'ordine selezionato
        ordine_dettaglio = df_pronti[df_pronti['id'] == id_ordine_target].iloc[0]
        
        # --- STRUTTURA STATO PER INTERCETTARE E VALIDARE I COLLI ---
        key_colli_confermati = f"colli_confermati_{id_ordine_target}"
        key_alert_attivo = f"alert_attivo_{id_ordine_target}"
        key_widget_colli = f"widget_colli_{id_ordine_target}"
        
        if key_colli_confermati not in st.session_state:
            db_val = ordine_dettaglio['numero_colli']
            valore_iniziale = int(db_val) if pd.notna(db_val) else st.session_state.get("colli_temporanei", 1)
            st.session_state[key_colli_confermati] = valore_iniziale
            st.session_state[key_alert_attivo] = False

        # Layout a due colonne: a sinistra il riepilogo merce, a destra i dati di spedizione
        col_sinistra, col_destra = st.columns([4, 3])
        
        with col_sinistra:
            st.markdown("### 📋 Verifica Contenuto Collo")
            
            if ordine_dettaglio['evaso_parziale']:
                st.warning("⚠️ **ATTENZIONE:** Questo ordine contiene prelievi parziali per mancanza di merce a scaffale. Controlla le quantità effettive prelevate.")
            
            try:
                query_righe_evase = """
                    SELECT p.barcode, p.brand, p.descrizione, r.quantita_richiesta, r.quantita_prelevata
                    FROM ordini_righe r
                    JOIN prodotti p ON r.prodotto_id = p.id
                    WHERE r.ordine_id = :ordine_id
                    ORDER BY p.brand, p.descrizione;
                """
                df_righe_evase = conn.query(query_righe_evase, params={"ordine_id": id_ordine_target}, ttl="0")
                
                st.dataframe(
                    df_righe_evase,
                    column_config={
                        "barcode": "Barcode",
                        "brand": "Brand",
                        "descrizione": "Descrizione Articolo",
                        "quantita_richiesta": st.column_config.NumberColumn("Q.tà Richiesta", format="%d"),
                        "quantita_prelevata": st.column_config.NumberColumn("Q.tà Effettiva da Inserire nel Collo", format="%d"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Errore nel recupero delle righe dell'ordine: {e}")
                
            if ordine_dettaglio['note']:
                st.info(f"📝 **Note Operative:** {ordine_dettaglio['note']}")
                
        with col_destra:
            st.markdown("### 🚚 Dati di Spedizione ERP e Lettera di Vettura")
            
            with st.container(border=True):
                st.markdown(f"`{ordine_dettaglio['codice_cliente']} {ordine_dettaglio['codice_destinazione']}`")
                st.markdown(f"**Destinatario:** {ordine_dettaglio['cliente_nome']}")
                st.markdown(f"**Indirizzo:** {ordine_dettaglio['indirizzo']}")
                st.markdown(f"**Località:** {ordine_dettaglio['cap']} - {ordine_dettaglio['citta']} ({ordine_dettaglio['nazione']})")
                st.caption(f"Picking ultimato il: {ordine_dettaglio['data_picking'].strftime('%d/%m/%Y %H:%M')}")

            # --- SEZIONE INPUT SENZA FORM PER GESTIRE I TRIGGER ---
            st.markdown("#### 📝 Inserimento Dati Logistici")
            with st.container(border=True):
                
                corriere_sel = st.selectbox(
                    "Corriere Spedizioniere *",
                    ["-- Seleziona un Corriere --", "BRT", "UPS", "DHL", "Altro"]
                )
                
                corriere_specifico = ""
                if corriere_sel == "Altro":
                    corriere_specifico = st.text_input("Specifica altro corriere/vettore:", placeholder="Es. Vettore locale...")
                
                col_colli, col_tracking = st.columns([1, 2])
                with col_colli:
                    def check_colli_trigger():
                        st.session_state[key_alert_attivo] = True

                    n_colli = st.number_input(
                        "Numero Colli *", 
                        min_value=1, 
                        value=st.session_state[key_colli_confermati], 
                        step=1,
                        on_change=check_colli_trigger,
                        key=key_widget_colli
                    )
                with col_tracking:
                    tracking_num = st.text_input("Tracking Number / N° Consegna *", placeholder="Scansiona tracking")
                
                # --- INTERCETTAZIONE E POPUP DI CONFERMA VARIAZIONE ---
                if st.session_state[key_alert_attivo]:
                    proposta_modifica = st.session_state[key_widget_colli]
                    if proposta_modifica != st.session_state[key_colli_confermati]:
                        st.warning(f"⚠️ **CONFERMA MODIFICA:** Vuoi variare i colli da **{st.session_state[key_colli_confermati]}** a **{proposta_modifica}**?")
                        c_yes, c_no = st.columns(2)
                        with c_yes:
                            if st.button("✅ Conferma", key=f"btn_yes_{id_ordine_target}", type="primary", use_container_width=True):
                                st.session_state[key_colli_confermati] = proposta_modifica
                                st.session_state[key_alert_attivo] = False
                                st.rerun()
                        with c_no:
                            if st.button("❌ Annulla", key=f"btn_no_{id_ordine_target}", use_container_width=True):
                                st.session_state[key_alert_attivo] = False
                                st.session_state[key_widget_colli] = st.session_state[key_colli_confermati]
                                st.rerun()

                st.write("")
                btn_spedisci = st.button("🚀 Conferma Spedizione e Chiudi Ordine", type="primary", use_container_width=True)
                
                if btn_spedisci:
                    vettore_finale = corriere_specifico if corriere_sel == "Altro" else corriere_sel
                    valore_colli_finale = st.session_state[key_colli_confermati]
                    
                    if corriere_sel == "-- Seleziona un Corriere --" or (corriere_sel == "Altro" and not corriere_specifico.strip()):
                        st.error("Scegli o specifica un corriere valido per procedere.")
                    elif not tracking_num.strip():
                        st.error("Il campo 'Tracking Number' è obbligatorio.")
                    elif valore_colli_finale <= 0:
                        st.error("Il numero di colli deve essere almeno pari a 1.")
                    elif st.session_state[key_alert_attivo]:
                        st.error("Conferma o annulla la modifica del numero di colli prima di chiudere la spedizione.")
                    else:
                        try:
                            with conn.session as session:
                                session.execute(
                                    text("""
                                        UPDATE ordini_testata
                                        SET stato = 'Spedito',
                                            corriere = :corriere,
                                            numero_colli = :colli,
                                            tracking_number = :tracking,
                                            data_aggiornamento = NOW()
                                        WHERE id = :id;
                                    """),
                                    params={
                                        "corriere": vettore_finale,
                                        "colli": int(valore_colli_finale),
                                        "tracking": tracking_num.strip(),
                                        "id": id_ordine_target
                                    }
                                )
                                session.commit()
                            
                            st.success(f"🎉 Ordine N° {ordine_dettaglio['numero_ordine']} chiuso con successo!")
                            st.balloons()
                            
                            del st.session_state[key_colli_confermati]
                            del st.session_state[key_alert_attivo]
                            if "colli_temporanei" in st.session_state:
                                del st.session_state.colli_temporanei
                                
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Errore transazionale durante la chiusura della spedizione: {e}")
