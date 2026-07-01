import streamlit as st

# 1. Configurazione globale (impostata una sola volta per tutta l'app)
st.set_page_config(page_title="SGLM - Gestione Logistica", layout="wide")

# 2. Definizione di tutte le pagine del workflow (percorso file, titolo e icona)
# 'default=True' assicura che l'utente atterri direttamente sulla Dashboard
dashboard_page           = st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True)
inventario_page          = st.Page("pages/2_Gestione_Inventario.py", title="Modulo A — Inventario & Stock", icon="📦")
inserimento_ordini_page   = st.Page("pages/3_Inserimento_Ordini.py", title="Modulo B — Inserimento Ordini", icon="🛒")
preparazione_ordini_page  = st.Page("pages/4_Preparazione_Ordini.py", title="Modulo C — Preparazione & Picking", icon="📋")
chiusura_ordini_page     = st.Page("pages/5_Chiusura_Ordini.py", title="Modulo D — Chiusura & Spedizione", icon="🚛")
storico_spedizioni_page   = st.Page("pages/6_Storico_Spedizioni.py", title="Modulo E — Storico Spedizioni", icon="📜")

# 3. Inizializzazione della navigazione centralizzata
# Inserendo tutte le pagine in questa lista, Streamlit genererà automaticamente
# il menu laterale pulito, escludendo il file 'main.py' dalla vista.
pg = st.navigation([
    dashboard_page,
    inventario_page,
    inserimento_ordini_page,
    preparazione_ordini_page,
    chiusura_ordini_page,
    storico_spedizioni_page
])

# 4. Avvio dell'applicazione
pg.run()
