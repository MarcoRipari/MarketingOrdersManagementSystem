import streamlit as st
import pandas as pd
from sqlalchemy import text

# Configurazione Desktop per il banco imballo
st.set_page_config(page_title="SGLM - Banco Imballo & Spedizione", layout="wide")

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
               t.note, t.evaso_parziale, t.data_aggiornamento as data_picking
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
        
        # Layout a due colonne: a sinistra il riepilogo merce, a destra i dati di spedizione
        col_sinistra, col_destra = st.columns([4, 3])
        
        with col_sinistra:
            st.markdown("### 📋 Verifica Contenuto Collo")
            
            # Visualizzazione alert se l'ordine è stato evaso parzialmente in corsia
            if ordine_dettaglio['evaso_parziale']:
                st.warning("⚠️ **ATTENZIONE:** Questo ordine contiene prelievi parziali per mancanza di merce a scaffale. Controlla le quantità effettive prelevate.")
            
            # Recupero delle righe per il controllo finale del contenuto
            try:
                query_righe_evase = """
                    SELECT p.barcode, p.brand, p.descrizione, r.quantita_richiesta, r.quantita_prelevata
                    FROM ordini_righe r
                    JOIN prodotti p ON r.prodotto_id = p.id
                    WHERE r.ordine_id = :ordine_id
                    ORDER BY p.brand, p.descrizione;
                """
                df_righe_evase = conn.query(query_righe_evase, params={"ordine_id": id_ordine_target}, ttl="0")
                
                # Tabella riepilogativa pulita per il banco di imballo
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
            
            # Box con anagrafica di spedizione per confronto visivo con etichettatrice
            with st.container(border=True):
                st.markdown(f"`{ordine_dettaglio['codice_cliente']} {ordine_dettaglio['codice_destinazione']}`")
                st.markdown(f"**Destinatario:** {ordine_dettaglio['cliente_nome']}")
                st.markdown(f"**Indirizzo:** {ordine_dettaglio['indirizzo']}")
                st.markdown(f"**Località:** {ordine_dettaglio['cap']} - {ordine_dettaglio['citta']} ({ordine_dettaglio['nazione']})")
                st.caption(f"Picking ultimato il: {ordine_dettaglio['data_picking'].strftime('%d/%m/%Y %H:%M')}")

            # --- FORM DI CHIUSURA SPEDIZIONE (CON VINCOLI DA PRD §7) ---
            st.markdown("#### 📝 Inserimento Dati Logistici")
            with st.form("form_chiusura_spedizione", clear_on_submit=False):
                
                # Selezione del vettore logistico
                corriere_sel = st.selectbox(
                    "Corriere Spedizioniere *",
                    ["-- Seleziona un Corriere --", "BRT", "UPS", "DHL", "Altro"]
                )
                
                # Se l'utente seleziona un corriere generico, può specificarlo sotto
                corriere_specifico = ""
                if corriere_sel == "Altro":
                    corriere_specifico = st.text_input("Specifica altro corriere/vettore:", placeholder="Es. Corriere locale, Consegnato a mano...")
                
                col_colli, col_tracking = st.columns([1, 2])
                with col_colli:
                    n_colli = st.number_input("Numero Colli *", min_value=1, value=1, step=1)
                with col_tracking:
                    tracking_num = st.text_input("Tracking Number / N° Consegna *", placeholder="Scansiona o digita il codice tracking")
                    
                st.write("")
                btn_spedisci = st.form_submit_button("🚀 Conferma Spedizione e Chiudi Ordine", type="primary", use_container_width=True)
                
                if btn_spedisci:
                    # Definizione del valore definitivo del corriere
                    vettore_finale = corriere_specifico if corriere_sel == "Ritiro Diretto / Altro" else corriere_sel
                    
                    # Validazione rigorosa dei vincoli del PRD
                    if corriere_sel == "-- Seleziona un Corriere --" or (corriere_sel == "Ritiro Diretto / Altro" and not corriere_specifico.strip()):
                        st.error("Scegli o specifica un corriere valido per procedere.")
                    elif not tracking_num.strip():
                        st.error("Il campo 'Tracking Number' è obbligatorio. Scansiona il codice a barre della lettera di vettura.")
                    elif n_colli <= 0:
                        st.error("Il numero di colli deve essere almeno pari a 1.")
                    else:
                        # Esecuzione transazionale del cambio stato
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
                                        "colli": n_colli,
                                        "tracking": tracking_num.strip(),
                                        "id": id_ordine_target
                                    }
                                )
                                session.commit()
                            
                            st.success(f"🎉 Ordine N° {ordine_dettaglio['numero_ordine']} chiuso con successo! Stato impostato su 'Spedito'.")
                            st.balloons()
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Errore transazionale durante la chiusura della spedizione: {e}")
