# utils_scanner.py
import os
import streamlit as st
import streamlit.components.v1 as components

@st.cache_resource
def inizializza_componente_scanner():
    """Crea dinamicamente i file necessari per il componente bidirezionale"""
    cartella_componente = "scanner_ottico_local"
    if not os.path.exists(cartella_componente):
        os.makedirs(cartella_componente)
    
    html_custom = """<!DOCTYPE html>
    <html>
    <head>
        <script type="text/javascript" src="https://unpkg.com/@zxing/library@latest"></script>
        <style>
            body { margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; background-color: transparent; }
            .scanner-window { position: relative; width: 100%; max-width: 400px; border-radius: 12px; overflow: hidden; border: 3px solid #ff4b4b; background-color: #000; }
            video { width: 100%; height: auto; display: block; }
            .laser-line { position: absolute; top: 50%; left: 5%; width: 90%; height: 2px; background-color: #ff0000; box-shadow: 0 0 8px #ff0000; animation: target 2.5s infinite ease-in-out; }
            @keyframes target { 0% { top: 20%; } 50% { top: 80%; } 100% { top: 20%; } }
        </style>
    </head>
    <body>
        <div class="scanner-window">
            <video id="webcam_feed" autoplay playsinline muted></video>
            <div class="laser-line"></div>
        </div>
        <script>
            function inviaDatoAPython(valore) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: valore
                }, '*');
            }

            window.parent.postMessage({type: 'streamlit:componentReady', version: 1}, '*');

            window.addEventListener("message", (event) => {
                if (event.data.type === "streamlit:render") {
                    // Pronto
                }
            });

            const codeReader = new ZXing.BrowserMultiFormatReader();
            const constraints = { video: { facingMode: "environment" } };

            codeReader.decodeFromConstraints(constraints, 'webcam_feed', (result, err) => {
                if (result) {
                    inviaDatoAPython(JSON.stringify({ barcode: result.text, ts: Date.now() }));
                    codeReader.reset();
                }
            });
        </script>
    </body>
    </html>"""
    
    with open(os.path.join(cartella_componente, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_custom)
        
    return components.declare_component("live_barcode_scanner", path=cartella_componente)

# Questa istanza sarà accessibile in modo sicuro tramite import
live_barcode_scanner = inizializza_componente_scanner()
