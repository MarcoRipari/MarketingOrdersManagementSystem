# utils_scanner.py
import os
import streamlit as st
import streamlit.components.v1 as components

# Punta alla nuova cartella rinominata per rompere la cache del browser
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPONENT_PATH = os.path.join(CURRENT_DIR, "scanner_v2")

# Registra il componente con un ID univoco aggiornato
live_barcode_scanner = components.declare_component(
    "live_barcode_scanner_v3", 
    path=COMPONENT_PATH
)

# --- 2. LOGICA DI ORDINAMENTO DEL PERCORSO DI PICKING ---
def chiave_percorso_picking(ubicazione):
    """
    Assegna un peso logistico all'ubicazione per ordinare correttamente il percorso.
    Scompatta stringhe come 'SOTTO3' in ('SOTTO', 3) e '12' in ('STANDARD', 12).
    """
    if not ubicazione:
        return (99, 999)  # Ubicazioni vuote in fondo
    
    ubicazione_str = str(ubicazione).strip().upper()
    
    # Priorità delle zone del magazzino
    priorita_zone = {
        "STANDARD": 0,
        "SOTTO": 1,
    }
    
    # Regex per separare la parte testuale da quella numerica
    match = re.match(r"^([A-Z]+)?(\d+)$", ubicazione_str)
    
    if match:
        zona = match.group(1) if match.group(1) else "STANDARD"
        numero = int(match.group(2))
    else:
        zona = "STANDARD"
        numero = 999
        
    peso_zona = priorita_zone.get(zona, 80)
    return (peso_zona, numero)
