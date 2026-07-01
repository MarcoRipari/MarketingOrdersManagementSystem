import streamlit as st

# Configurazione della pagina (deve essere la prima istruzione Streamlit)
st.set_page_config(
    page_title="SGLM - Logistica Marketing",
    page_icon="📦",
    layout="wide"
)

st.title("📦 SGLM — Sistema Gestione Logistica Marketing")
st.write("Benvenuto nel sistema integrato di gestione. Seleziona una pagina dalla sidebar per iniziare.")

st.divider()

## ----------------------------------------------------
## MODULO F — LOOKUP RAPIDO (Disponibile a tutti)
## ----------------------------------------------------
st.subheader("🔍 Lookup Rapido Articolo")
query_search = st.text_input("Scansiona Barcode o digita parte della descrizione", placeholder="Es. FW26, Gadget, 8034...")

if query_search:
    try:
        # Inizializza la connessione nativa SQL di Streamlit usando i secrets cloud
        conn = st.connection("postgresql", type="sql")
        
        # Query sulla vista del database (ricerca esatta su barcode o parziale su descrizione)
        query = """
            SELECT barcode, descrizione, brand, posizione, quantita_disponibile, totale_spedito_storico
            FROM vista_prodotti_riepilogo
            WHERE barcode = :search OR descrizione ILIKE :search_partial
        """
        
        df = conn.query(
            query, 
            params={"search": query_search, "search_partial": f"%{query_search}%"},
            ttl="0" # Nessuna cache per avere dati sempre aggiornati in tempo reale
        )
        
        if not df.empty:
            st.success(f"Trovati {len(df)} riscontri:")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("Nessun prodotto trovato con i criteri inseriti.")
            
    except Exception as e:
        st.error("Errore di connessione al database Supabase. Controlla i Secrets nel pannello di Streamlit Cloud.")
        st.exception(e)
