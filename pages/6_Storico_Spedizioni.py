import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text

# Configurazione della pagina (Layout Wide per analisi dati e storico)
st.set_page_config(page_title="SGLM - Storico Spedizioni & Tracking", layout="wide")

# Connessione al database
conn = st.connection("postgresql", type="sql")

st.title("📜 Modulo E — Storico Spedizioni & Tracking")
st.write("Visualizzazione degli ordini evasi, filtri avanzati per cliente/data e tracciamento in tempo reale della consegna.")

# -------------------------------------------------------------------------
# FUNZIONE DI SIMULAZIONE TRACKING EVOLUTO (LOGISTICA SMART)
# -------------------------------------------------------------------------
def calcola_stato_consegna(data_spedizione):
    """
    Simula in modo realistico gli step del corriere in base al tempo trascorso.
    In produzione, questa funzione leggerà una colonna 'stato_consegna' aggiornata da API/Webhook.
    """
    adesso = datetime.now()
    # Rimuoviamo il fuso orario se presente per il calcolo delle ore passate
    dt_sped = data_spedizione.replace(tzinfo=None)
    ore_trascorse = (adesso - dt_sped).total_seconds() / 3600

    if ore_trascorse < 4:
        return "📦 Preso in carico", "In preparazione presso l'hub del corriere", "info", 20
    elif ore_trascorse < 24:
        return "🚚 In transito", "Il carico è in viaggio verso la filiale di destinazione", "info", 50
    elif ore_trascorse < 48:
        return "🛵 In consegna", "In consegna oggi con l'autista della filiale locale", "warning", 80
    else:
        return "✅ Consegnato", f"Consegnato con successo il {(dt_sped + timedelta(days=2)).strftime('%d/%m/%Y alle %H:%M')}", "success", 100

# -------------------------------------------------------------------------
# FILTRI DI RICERCA (SIDEBAR O PANNELLO SUPERIORE)
# -------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 Filtri di Ricerca")
    
    # 1. Recupero lista clienti storici per il filtro
    try:
        df_clienti = conn.query("SELECT DISTINCT c.id, c.nome FROM clienti c JOIN ordini_testata o ON o.cliente_id = c.id WHERE o.stato = 'Spedito' ORDER BY c.nome;", ttl="60")
        opzioni_clienti = {"Tutti i clienti": None}
        for _, r in df_clienti.iterrows():
            opzioni_clienti[r['nome']] = r['id']
        cliente_selezionato = st.selectbox("Filtra per Cliente:", list(opzioni_clienti.keys()))
        id_cliente_filtro = opzioni_clienti[cliente_selezionato]
    except Exception:
        id_cliente_filtro = None
        st.caption("Nessun filtro cliente disponibile.")

    # 2. Filtro per Range di Date
    st.subheader("Data di Spedizione")
    data_inizio = st.date_input("Dal:", datetime.now() - timedelta(days=30))
    data_fine = st.date_input("Al:", datetime.now())

    # 3. Limite record rapido
    limite_record = st.slider("Numero ordini recenti in lista:", min_value=5, max_value=50, value=10, step=5)

# -------------------------------------------------------------------------
# QUERY DI ESTRAZIONE CON FILTRI DINAMICI
# -------------------------------------------------------------------------
query_base = """
    SELECT t.id, t.numero_ordine, c.nome as cliente_nome, t.corriere, 
           t.tracking_number, t.numero_colli, t.data_aggiornamento as data_spedizione, 
           t.evaso_parziale
    FROM ordini_testata t
    JOIN clienti c ON t.cliente_id = c.id
    WHERE t.stato = 'Spedito'
"""
params = {}

if id_cliente_filtro:
    query_base += " AND t.cliente_id = :cliente_id"
    params["cliente_id"] = id_cliente_filtro

# Filtro date (trasformate in timestamp per inclusione corretta delle ore)
query_base += " AND t.data_aggiornamento >= :data_inizio AND t.data_aggiornamento <= :data_fine"
params["data_inizio"] = datetime.combine(data_inizio, datetime.min.time())
params["data_fine"] = datetime.combine(data_fine, datetime.max.time())

query_base += f" ORDER BY t.data_aggiornamento DESC LIMIT {limite_record};"

try:
    df_storico = conn.query(query_base, params=params, ttl="0")
except Exception as e:
    st.error(f"Errore nel caricamento dello storico: {e}")
    st.stop()

# -------------------------------------------------------------------------
# INTERFACCIA: LISTA ORDINI ED ESPANSIONE DETTAGLI
# -------------------------------------------------------------------------
st.subheader(f"📋 Ultimi {len(df_storico)} ordini spediti corrispondenti ai filtri")

if df_storico.empty:
    st.info("ℹ️ Nessuna spedizione trovata nel periodo selezionato o con i filtri impostati.")
else:
    # Mostriamo la lista interattiva
    for _, ordine in df_storico.iterrows():
        o_id = ordine['id']
        data_sped_formattata = ordine['data_spedizione'].strftime('%d/%m/%Y %H:%M')
        
        # Calcolo dinamico dello stato della consegna del corriere
        titolo_stato, descrizione_stato, colore_stato, progresso = calcola_stato_consegna(ordine['data_spedizione'])
        
        # Label integrativa per ordini evasi parzialmente
        tag_parziale = " ⚠️ Parziale" if ordine['evaso_parziale'] else ""
        
        # Stringa del titolo dell'expander (agisce come riga cliccabile di riepilogo)
        label_expander = f"📦 Ordine N° {ordine['numero_ordine']} — Destinatario: {ordine['cliente_nome']} — Spedito il: {data_sped_formattata} | [{titolo_stato}]{tag_parziale}"
        
        with st.expander(label_expander):
            # Layout interno al dettaglio dell'ordine cliccato
            col_info, col_tracking = st.columns([1, 1])
            
            with col_info:
                st.markdown("#### 🎫 Informazioni di Spedizione")
                st.markdown(f"**Vettore:** `{ordine['corriere']}`")
                st.markdown(f"**Lettera di Vettura / Tracking:** `{ordine['tracking_number']}`")
                st.markdown(f"**Totale Colli Inviati:** {ordine['numero_colli']}")
                if ordine['evaso_parziale']:
                    st.caption("🔴 *Nota: L'ordine è partito incompleto per mancanze stock segnalate in picking.*")
                
                # Bottone per simulare il link esterno di tracciamento del corriere
                if(ordine['corriere'] == "BRT"):
                    url_mock = f"https://www.mybrt.it/it/mybrt/my-parcels/incoming?parcelNumber={ordine['tracking_number']}"
                else:
                    url_mock = f"https://www.google.com/search?q=tracking+button+{ordine['corriere']}+{ordine['tracking_number']}"
                    
                st.link_button(f"🌐 Apri Portale {ordine['corriere']}", url_mock, use_container_width=True)

            with col_tracking:
                st.markdown("#### 📍 Stato Consegna in Tempo Reale")
                
                # Visualizzazione grafica avanzata dello stato di avanzamento della consegna
                if colore_stato == "success":
                    st.success(f"**{titolo_stato}**\n\n{descrizione_stato}")
                elif colore_stato == "warning":
                    st.warning(f"**{titolo_stato}**\n\n{descrizione_stato}")
                else:
                    st.info(f"**{titolo_stato}**\n\n{descrizione_stato}")
                
                st.progress(progresso)
                st.caption(f"Ultimo aggiornamento automatico dei sistemi: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

            # Sotto-Tabella: Dettaglio della merce effettivamente spedita contenuta nei colli
            st.markdown("---")
            st.markdown("**🔍 Contenuto del pacco spedito:**")
            try:
                query_merci = """
                    SELECT p.barcode, p.brand, p.descrizione, r.quantita_prelevata as quantita_spedita
                    FROM ordini_righe r
                    JOIN prodotti p ON r.prodotto_id = p.id
                    WHERE r.ordine_id = :ordine_id AND r.quantita_prelevata > 0
                    ORDER BY p.descrizione;
                """
                df_merci = conn.query(query_merci, params={"ordine_id": o_id}, ttl="0")
                
                st.dataframe(
                    df_merci,
                    column_config={
                        "barcode": "Barcode",
                        "brand": "Brand",
                        "descrizione": "Descrizione Materiale Marketing",
                        "quantita_spedita": st.column_config.NumberColumn("Pezzi Spediti", format="%d")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Impossibile caricare il dettaglio merci per questo ordine: {e}")
