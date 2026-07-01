import streamlit as st
import pandas as pd
from sqlalchemy import text

st.set_page_config(page_title="SGLM - Inventario & Stock", layout="wide")

# Connessione al Database
conn = st.connection("postgresql", type="sql")

st.title("📊 Modulo A — Dashboard & Inventario")

## ----------------------------------------------------
## GESTIONE RUOLO (Separazione solo a livello UI come da PRD)
## ----------------------------------------------------
st.sidebar.header("Impostazioni Vista")
ruolo_utente = st.sidebar.radio(
    "Seleziona il tuo Ruolo (Simulato):",
    ["Richiedente (Marketing)", "Operatore (Magazzino)"]
)

## ----------------------------------------------------
## 1. CARICAMENTO DATI & FILTRI
## ----------------------------------------------------
# Recuperiamo tutti i prodotti dalla vista riepilogativa
try:
    df_prodotti = conn.query("SELECT * FROM vista_prodotti_riepilogo;", ttl="0")
    
    # CORREZIONE: Ordinamento alfabetico predefinito per Brand e Descrizione
    if not df_prodotti.empty:
        df_prodotti = df_prodotti.sort_values(by=["brand", "descrizione"], ascending=[True, True]).reset_index(drop=True)
        
except Exception as e:
    st.error("Errore nel caricamento dei dati dal database.")
    st.exception(e)
    st.stop()

# Sezione Filtri nella barra laterale
st.sidebar.subheader("Filtri Ricerca Stock")

# Filtro Brand
lista_brand = ["Tutti"] + sorted([b for b in df_prodotti["brand"].dropna().unique() if b])
brand_selezionato = st.sidebar.selectbox("Filtra per Brand", lista_brand)

# Filtro Stagione
lista_stagioni = ["Tutte"] + sorted([s for s in df_prodotti["stagione_riferimento"].dropna().unique() if s])
stagione_selezionata = st.sidebar.selectbox("Filtra per Stagione", lista_stagioni)

# Applicazione Filtri al DataFrame
df_filtrato = df_prodotti.copy()
if brand_selezionato != "Tutti":
    df_filtrato = df_filtrato[df_filtrato["brand"] == brand_selezionato]
if stagione_selezionata != "Tutte":
    df_filtrato = df_filtrato[df_filtrato["stagione_riferimento"] == stagione_selezionata]


## ----------------------------------------------------
## 2. ALERT SOTTO SCORTA
## ----------------------------------------------------
df_sotto_scorta = df_filtrato[df_filtrato["sotto_scorta"] == True]

if not df_sotto_scorta.empty:
    st.error(f"⚠️ Attenzione: Ci sono {len(df_sotto_scorta)} articles in esaurimento (Sotto Scorta)!")
    # Mostriamo un mini-tabellone espandibile con gli elementi critici
    with st.expander("Visualizza articoli sotto scorta", expanded=True):
        st.dataframe(
            df_sotto_scorta[["barcode", "descrizione", "posizione", "quantita_disponibile", "scorta_minima"]],
            use_container_width=True,
            hide_index=True
        )
else:
    st.success("✅ Tutti i livelli di stock sono ottimali per i filtri selezionati.")


## ----------------------------------------------------
## 3. TABELLA PRINCIPALE STOCK
## ----------------------------------------------------
st.subheader("📦 Giacenze di Magazzino")

# Funzione per colorare le righe sotto scorta direttamente nella tabella globale
def colora_sotto_scorta(row):
    return ['background-color: #ffcccc' if row['sotto_scorta'] else '' for _ in row]

if not df_filtrato.empty:
    # Mostriamo la tabella applicando lo stile di formattazione condizionale
    # CORREZIONE UI: Aggiunto column_config per formattare l'anno senza virgole (es. 2026 e non 2,026)
    st.dataframe(
        df_filtrato.style.apply(colora_sotto_scorta, axis=1),
        column_order=["barcode", "descrizione", "brand", "stagione_riferimento", "anno_riferimento", "posizione", "quantita_disponibile", "scorta_minima", "totale_spedito_storico"],
        column_config={
            "anno_riferimento": st.column_config.NumberColumn("Anno Rif.", format="%d"),
            "quantita_disponibile": st.column_config.NumberColumn("Q.tà Disponibile", format="%d"),
            "scorta_minima": st.column_config.NumberColumn("Scorta Minima", format="%d"),
            "totale_spedito_storico": st.column_config.NumberColumn("Totale Spedito", format="%d"),
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Nessun prodotto corrispondente ai filtri selezionati.")


## ----------------------------------------------------
## 4. INTERFACCIA OPERATORE (SOLO SE RUOLO = OPERATORE)
## ----------------------------------------------------
if ruolo_utente == "Operatore (Magazzino)":
    st.divider()
    st.header("🛠️ Area Gestionale (Solo Operatore)")
    
    tab1, tab2 = st.tabs(["🆕 Inserisci Nuovo Prodotto", "✏️ Rettifica Inventario / Sposta Posizione"])
    
    # TAB 1: NUOVO PRODOTTO
    with tab1:
        st.subheader("Anagrafica Nuovo Articolo Marketing")
        with st.form("form_nuovo_prodotto", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_barcode = st.text_input("Barcode (Codice a Barre) *")
                new_desc = st.text_input("Descrizione Prodotto *")
                new_brand = st.text_input("Brand (Opzionale)")
            with col2:
                new_stagione = st.selectbox("Stagione (Opzionale)", [None, "SS", "FW"])
                # CORREZIONE: value=None permette al campo numerico di essere svuotato/lasciato in bianco
                new_anno = st.number_input("Anno (Opzionale)", min_value=2020, max_value=2035, value=None, step=1)
                new_pos = st.text_input("Posizione a Scaffale (es. A-01-B) *")
            
            col3, col4 = st.columns(2)
            with col3:
                new_qty = st.number_input("Quantità Iniziale Disponibile", min_value=0, value=0, step=1)
            with col4:
                new_min = st.number_input("Soglia Scorta Minima", min_value=0, value=5, step=1)
                
            submit_new = st.form_submit_button("Salva Prodotto in Anagrafica")
            
            if submit_new:
                # CORREZIONE: L'anno NON è tra i campi obbligatori qui
                if not new_barcode or not new_desc or not new_pos:
                    st.error("I campi Barcode, Descrizione e Posizione sono obbligatori.")
                else:
                    try:
                        with conn.session as session:
                            # CORREZIONE BUG: Sintassi SQL corretta in INSERT INTO con i nomi reali delle tue colonne
                            session.execute(
                                text("""
                                INSERT INTO prodotti (barcode, descrizione, brand, stagione_riferimento, anno_riferimento, posizione, quantita_disponibile, scorta_minima)
                                VALUES (:barcode, :desc, :brand, :stagione, :anno, :posizione, :qty, :scorta);
                                """),
                                params={
                                    "barcode": new_barcode.strip(), 
                                    "desc": new_desc.strip(), 
                                    "brand": new_brand.strip() if new_brand.strip() else None,
                                    "stagione": new_stagione, 
                                    # CORREZIONE: Se l'utente non scrive l'anno, viene passato None (NULL nel DB) senza crash
                                    "anno": int(new_anno) if new_anno is not None else None, 
                                    "posizione": new_pos.strip().upper(), 
                                    "qty": new_qty, 
                                    "scorta": new_min
                                }
                            )
                            session.commit()
                        st.success(f"Prodotto '{new_desc}' inserito con successo!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")

    # TAB 2: RETTIFICA INVENTARIO
    with tab2:
        st.subheader("Correzione Rapida Giacenza o Spostamento")
        if not df_prodotti.empty:
            # Selezione del prodotto da modificare
            prodotto_scelto = st.selectbox(
                "Seleziona l'articolo da rettificare",
                df_prodotti["id"].tolist(),
                format_func=lambda x: f"{df_prodotti[df_prodotti['id'] == x]['barcode'].values[0]} - {df_prodotti[df_prodotti['id'] == x]['brand'].values[0]} - {df_prodotti[df_prodotti['id'] == x]['descrizione'].values[0]}"
            )
            
            # Recupero dati attuali della riga selezionata
            dati_attuali = df_prodotti[df_prodotti["id"] == prodotto_scelto].iloc[0]
            
            with st.form("form_rettifica"):
                st.write(f"**Posizione Attuale:** {dati_attuali['posizione']} | **Giacenza Attuale:** {dati_attuali['quantita_disponibile']}")
                
                edit_pos = st.text_input("Nuova Posizione", value=dati_attuali['posizione'])
                edit_qty = st.number_input("Nuova Quantità Esatta (Rilevata a scaffale)", min_value=0, value=int(dati_attuali['quantita_disponibile']), step=1)
                edit_min = st.number_input("Modifica Scorta Minima", min_value=0, value=int(dati_attuali['scorta_minima']), step=1)
                
                submit_edit = st.form_submit_button("Applica Rettifica Inventariale")
                
                if submit_edit:
                    try:
                        with conn.session as session:
                            session.execute(
                                text("""
                                UPDATE prodotti 
                                SET posizione = :pos, quantita_disponibile = :qty, scorta_minima = :min
                                WHERE id = :id;
                                """),
                                params={"pos": edit_pos.strip().upper(), "qty": edit_qty, "min": edit_min, "id": prodotto_scelto}
                            )
                            session.commit()
                        st.success("Rettifica inventariale registrata!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'aggiornamento: {e}")
