import streamlit as st
import pandas as pd
from sqlalchemy import text
import json

from utils_scanner import live_barcode_scanner

st.set_page_config(page_title="SGLM - Picking Mobile", layout="centered")
conn = st.connection("postgresql", type="sql")

st.title("📱 Modulo C — Picking Mobile")

if "ordine_in_picking_id" not in st.session_state:
    st.session_state.ordine_in_picking_id = None

if "righe_confermate_sessione" not in st.session_state:
    st.session_state.righe_confermate_sessione = set()

# --- FASE 1: SELEZIONE ORDINE ---
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
        st.error(f"Errore: {e}")
        st.stop()

    if df_nuovi.empty:
        st.info("🎉 Ottimo! Non ci sono ordini in attesa.")
    else:
        for _, row in df_nuovi.iterrows():
            with st.container(border=True):
                st.write(f"📦 **Ordine N° {row['numero_ordine']}**")
                st.write(f"**Destinatario:** {row['cliente_nome']}")
                if st.button(f"⚡ Inizia Picking N° {row['numero_ordine']}", key=f"btn_take_{row['id']}", use_container_width=True):
                    with conn.session as session:
                        res = session.execute(
                            text("UPDATE ordini_testata SET stato = 'In Picking', data_aggiornamento = NOW() WHERE id = :id AND stato = 'Nuovo' RETURNING id;"),
                            params={"id": row['id']}
                        )
                        if res.fetchall():
                            st.session_state.ordine_in_picking_id = row['id']
                            st.session_state.righe_confermate_sessione = set()
                            # Inizializziamo il dato dei colli nello stato globale per la pagina successiva
                            st.session_state.colli_temporanei = 1 
                            session.commit()
                            st.rerun()

# --- FASE 2: PICKING ATTIVO ---
else:
    id_ordine_attivo = st.session_state.ordine_in_picking_id
    try:
        ordine_info = conn.query("SELECT t.numero_ordine, c.nome as cliente_nome, t.note FROM ordini_testata t JOIN clienti c ON t.cliente_id = c.id WHERE t.id = :id;", params={"id": id_ordine_attivo}, ttl="0").iloc[0]
    except:
        st.session_state.ordine_in_picking_id = None
        st.stop()

    st.subheader(f"⚡ Picking: N° {ordine_info['numero_ordine']}")
    
    if st.button("↩️ Rilascia Ordine", use_container_width=True):
        with conn.session as session:
            session.execute(text("UPDATE ordini_testata SET stato = 'Nuovo' WHERE id = :id;"), params={"id": id_ordine_attivo})
            session.commit()
        st.session_state.ordine_in_picking_id = None
        st.rerun()

    try:
        df_righe_picking = conn.query("SELECT r.id as riga_id, p.id as prodotto_id, p.barcode, p.brand, p.descrizione, p.posizione, r.quantita_richiesta, r.quantita_prelevata FROM ordini_righe r JOIN prodotti p ON r.prodotto_id = p.id WHERE r.ordine_id = :ordine_id;", params={"ordine_id": id_ordine_attivo}, ttl="0")
        if not df_righe_picking.empty:
            df_righe_picking['pos_num'] = pd.to_numeric(df_righe_picking['posizione'], errors='coerce').fillna(9999)
            df_righe_picking = df_righe_picking.sort_values(by='pos_num').drop(columns=['pos_num'])
    except Exception as e:
        st.error(f"Errore righe: {e}")
        st.stop()

    tutti_completati = True
    active_item_found = False
    
    # RENDERIZZIAMO LO SCANNER FUORI DAL LOOP MA SOLO SE C'E' UN ARTICOLO ATTIVO
    # Questo garantisce KEY FISSA (niente richieste permessi continue) e POSIZIONE FISSA (niente schermo nero)
    for _, riga in df_righe_picking.iterrows():
        if not (riga['quantita_prelevata'] > 0 or riga['riga_id'] in st.session_state.righe_confermate_sessione):
            tutti_completati = False

    for _, riga in df_righe_picking.iterrows():
        r_id = riga['riga_id']
        gia_prelevato = riga['quantita_prelevata'] > 0 or r_id in st.session_state.righe_confermate_sessione

        with st.container(border=True):
            if gia_prelevato:
                st.write(f"🟢 **[{riga['posizione']}]** — {riga['descrizione']}")
                st.caption(f"Prelevato!")
            else:
                st.error(f"📍 UBICAZIONE: {riga['posizione']}")
                st.write(f"**{riga['descrizione']}** — Q.tà: {int(riga['quantita_richiesta'])}")
                
                if not active_item_found:
                    active_item_found = True
                    
                    # SCANNER CON KEY STATICA FISSA
                    res_scanner = live_barcode_scanner(key="picking_scanner_mobile_unico")
                    
                    if res_scanner:
                        try:
                            data = json.loads(res_scanner)
                            if data["barcode"].strip() == riga['barcode'].strip():
                                with conn.session as session:
                                    session.execute(text("UPDATE ordini_righe SET quantita_prelevata = :q WHERE id = :id;"), params={"q": riga['quantita_richiesta'], "id": r_id})
                                    session.commit()
                                st.session_state.righe_confermate_sessione.add(r_id)
                                st.toast(f"✅ Ottimo! Preso {riga['descrizione']}", icon="👟")
                                st.rerun()
                            else:
                                # Usiamo st.toast invece di st.error per non resettare il DOM della fotocamera
                                st.toast(f"❌ Barcode Errato! Letto: {data['barcode']}", icon="⚠️")
                        except:
                            pass

                    # Fallback Manuale
                    bc_man = st.text_input("Inserimento Manuale", key=f"man_{r_id}")
                    if bc_man.strip() == riga['barcode'].strip():
                        if st.button("Conferma Manuale", key=f"btn_{r_id}", type="primary"):
                            with conn.session as session:
                                session.execute(text("UPDATE ordini_righe SET quantita_prelevata = :q WHERE id = :id;"), params={"q": riga['quantita_richiesta'], "id": r_id})
                                session.commit()
                            st.session_state.righe_confermate_sessione.add(r_id)
                            st.rerun()
                else:
                    st.info("⏳ Articolo successivo nel percorso.")

    # --- CHIUSURA PICKING ---
    st.divider()
    st.subheader("🏁 Fine Prelievo")
    
    # Aggiorna in tempo reale la variabile temporale dei colli
    numero_colli = st.number_input("📦 Quanti colli hai preparato?", min_value=1, max_value=50, value=int(st.session_state.get("colli_temporanei", 1)))
    st.session_state.colli_temporanei = numero_colli

    if st.button("🏁 Chiudi Picking e Invia all'Imballo", type="primary", use_container_width=True):
        with conn.session as session:
            session.execute(
                text("UPDATE ordini_testata SET stato = 'Pronto Spedizione', numero_colli = :nc, data_aggiornamento = NOW() WHERE id = :id;"),
                params={"nc": int(numero_colli), "id": id_ordine_attivo}
            )
            session.commit()
        
        # Salviamo l'ID dell'ordine appena chiuso per passarlo alla pagina 5 in session state
        st.session_state.ultimo_ordine_chiuso_id = id_ordine_attivo
        st.success("Picking salvato!")
        st.session_state.ordine_in_picking_id = None
        st.rerun()
