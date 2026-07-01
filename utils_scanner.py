# utils_scanner.py
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
