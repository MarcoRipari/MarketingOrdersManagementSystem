import streamlit as st
import pandas as pd
from sqlalchemy import text

st.set_page_config(page_title="SGLM - Dashboard Direzionale", layout="wide")
conn = st.connection("postgresql", type="sql")

st.title("📊 Modulo F — Pannello di Controllo Direzionale")

# -------------------------------------------------------------------------
# RECUPERO DATI METRICHE (KPI)
# -------------------------------------------------------------------------
try:
    # 1. Ordini da fare (Tutti quelli non ancora spediti o annullati)
    query_da_fare = "SELECT COUNT(*) FROM ordini_testata WHERE stato IN ('Nuovo', 'In Picking', 'Pronto Spedizione');"
    ordini_da_fare = conn.query(query_da_fare, ttl="0").iloc[0, 0]

    # 2. Ordini spediti totali
    query_spediti_tot = "SELECT COUNT(*) FROM ordini_testata WHERE stato = 'Spedito';"
    spediti_totali = conn.query(query_spediti_tot, ttl="0").iloc[0, 0]

    # 3. Ordini spediti questo mese
    query_mese = """
        SELECT COUNT(*) FROM ordini_testata 
        WHERE stato = 'Spedito' 
        AND data_aggiornamento >= DATE_TRUNC('month', CURRENT_DATE);
    """
    spediti_mese = conn.query(query_mese, ttl="0").iloc[0, 0]

    # 4. Ordini spediti quest'anno
    query_anno = """
        SELECT COUNT(*) FROM ordini_testata 
        WHERE stato = 'Spedito' 
        AND data_aggiornamento >= DATE_TRUNC('year', CURRENT_DATE);
    """
    spediti_anno = conn.query(query_anno, ttl="0").iloc[0, 0]

except Exception as e:
    st.error(f"Errore nel calcolo delle metriche di controllo: {e}")
    st.stop()

# Layout metriche a 4 colonne simmetriche
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Evidenziato visivamente perché indicato come "Importante"
    st.metric(label="🚨 Ordini da Elaborare (Da Fare)", value=ordini_da_fare, delta=f"{ordini_da_fare} pendenti", delta_color="inverse")
with col2:
    st.metric(label="📦 Totale Ordini Spediti", value=spediti_totali)
with col3:
    st.metric(label="📅 Spediti Questo Mese", value=spediti_mese)
with col4:
    st.metric(label="🏢 Spediti Quest'Anno", value=spediti_anno)

st.divider()

# -------------------------------------------------------------------------
# AVVISO ELEMENTI SOTTOSCORTA (IN ROSSO)
# -------------------------------------------------------------------------
st.subheader("⚠️ Allerta Materiali in Sottoscorta")

try:
    # Estrazione prodotti con giacenza inferiore o uguale alla scorta minima ordinati per brand/descrizione
    query_sottoscorta = """
        SELECT barcode, brand, descrizione, posizione, quantita_disponibile, scorta_minima
        FROM prodotti
        WHERE quantita_disponibile <= scorta_minima
        ORDER BY brand ASC, descrizione ASC;
    """
    df_sottoscorta = conn.query(query_sottoscorta, ttl="0")
except Exception as e:
    st.error(f"Errore nel recupero dei dati di inventario: {e}")
    df_sottoscorta = pd.DataFrame()

if df_sottoscorta.empty:
    st.success("🎉 Ottimo! Nessun articolo in magazzino è attualmente sotto la scorta minima impostata.")
else:
    st.error(f"Attenzione: Ci sono {len(df_sottoscorta)} articoli in esaurimento o sotto la soglia di sicurezza minima!")
    
    # Visualizzazione tabellare pulita con evidenziazione
    st.dataframe(
        df_sottoscorta,
        column_config={
            "barcode": "Barcode",
            "brand": "Brand",
            "descrizione": "Descrizione Articolo",
            "posizione": "Ubicazione",
            "quantita_disponibile": st.column_config.NumberColumn("Giacenza Attuale", format="%d"),
            "scorta_minima": st.column_config.NumberColumn("Scorta Minima", format="%d"),
        },
        hide_index=True,
        use_container_width=True
    )
