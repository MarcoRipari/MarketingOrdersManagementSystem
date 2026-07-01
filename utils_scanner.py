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
)# utils_scanner.py
import os
import streamlit as st
import streamlit.components.v1 as components

# Recupera il percorso assoluto della cartella statica
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPONENT_PATH = os.path.join(CURRENT_DIR, "scanner_ottico_local")

# CAMBIATO IL NOME IN _v2 PER FORZARE IL RE-INDEXING SU STREAMLIT CLOUD
live_barcode_scanner = components.declare_component(
    "live_barcode_scanner_v2", 
    path=COMPONENT_PATH
)# utils_scanner.py
import os
import streamlit as st
import streamlit.components.v1 as components

# Recupera il percorso assoluto della cartella statica sincronizzata con Git
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPONENT_PATH = os.path.join(CURRENT_DIR, "scanner_ottico_local")

# Dichiara il componente puntando direttamente alla cartella statica esistente
live_barcode_scanner = components.declare_component(
    "live_barcode_scanner", 
    path=COMPONENT_PATH
)
