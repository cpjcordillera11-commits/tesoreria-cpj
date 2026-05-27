import streamlit as st
import cv2
import numpy as np
import gspread
import os
import io
import base64
from datetime import datetime
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN E IDs ---
SPREADSHEET_ID = '1VlInzmxUY2YhkCLrM9Dc8K5coxWUCiQiYDkz5maQfns'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# --- 2. ESTILO Y ANIMACIÓN (CSS) ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Alegreya:wght@700&family=Inter:wght@400;700&display=swap');
        
        .stApp { background-color: #eef2e6; }
        
        /* Reducción de espacios para celular */
        [data-testid="stVerticalBlock"] > div { gap: 0.3rem !important; padding: 0 !important; }

        h1 { font-family: 'Alegreya', serif !important; color: #3b4d1a !important; text-align: center; font-size: 2.2rem !important; margin-bottom: 0px !important; }
        .title-underline { width: 50px; height: 3px; background: #b76e4b; margin: 5px auto 1.2rem auto; border-radius: 2px; }

        .stForm { background-color: #ffffff; padding: 1.5rem !important; border-radius: 20px !important; border: 1px solid #d4d9c6 !important; box-shadow: 0 8px 20px rgba(74,93,35,0.05) !important; position: relative; z-index: 1; }

        label p { color: #6b8e23 !important; font-weight: 700 !important; text-transform: uppercase; font-size: 0.75rem !important; margin-bottom: -10px !important; }

        /* Estilo del Botón Nativo */
        div.stButton > button {
            width: 100% !important;
            background-color: #6b8e23 !important;
            color: white !important;
            border-radius: 12px !important;
            padding: 0.8rem !important;
            font-weight: 700 !important;
            border: none !important;
        }

        /* --- CONTENEDOR DEL COHETE --- */
        .launch-container {
            position: fixed;
            top: 40%;
            left: 50%;
            transform: translate(-50%, -50%);
            height: 200px;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: flex-end;
            z-index: 9999 !important;
            pointer-events: none;
        }

        .rocket-fly {
            font-size: 4rem;
            filter: drop-shadow(0 0 10px rgba(255,255,255,0.8));
            animation: takeoff 1.8s forwards cubic-bezier(0.42, 0, 0.58, 1);
        }

        .smoke {
            position: absolute;
            bottom: 20px;
            width: 30px;
            height: 30px;
            background: radial-gradient(circle, rgba(255,255,255,0.9) 0%, rgba(200,200,200,0) 70%);
            border-radius: 50%;
            animation: smoke-drift 1.2s forwards;
        }

        @keyframes takeoff {
            0% { transform: translate(0, 0) scale(1) rotate(0deg); opacity: 1; }
            100% { transform: translate(400px, -600px) scale(4) rotate(25deg); opacity: 0; }
        }

        @keyframes smoke-drift {
            0% { transform: scale(1); opacity: 0.8; }
            100% { transform: scale(6); opacity: 0; }
        }
        </style>
        """, unsafe_allow_html=True)

# --- 3. AUTENTICACIÓN GOOGLE SHEETS ---
def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"❌ Error con los Secrets: {e}")
            st.stop()
    st.error("Falta configurar gcp_service_account en los Secrets de Streamlit.")
    st.stop()

# --- 4. MOTOR DE ESCANEO Y COMPRESIÓN ---
def scan_receipt(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    orig = img.copy()
    ratio = img.shape[0] / 800.0
    work_img = cv2.resize(img, (int(img.shape[1] / ratio), 800))
    gray = cv2.cvtColor(work_img, cv2.COLOR_BGR2GRAY)
    edged = cv2.Canny(cv2.GaussianBlur(gray, (7, 7), 0), 50, 150)
    cnts, _ = cv2.findContours(cv2.dilate(edged, np.ones((9,9), np.uint8), iterations=2), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if cnts:
        x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
        m = 40
        return orig, orig[int(max(0,y-m)*ratio):int((y+h+m)*ratio), int(max(0,x-m)*ratio):int((x+w+m)*ratio)]
    return orig, orig

# Compresión optimizada para celdas de Sheets
def image_to_short_base64(image_np, max_width=350):
    h, w = image_np.shape[:2]
    if w > max_width:
        new_h = int(h * (max_width / w))
        resized = cv2.resize(image_np, (max_width, new_h), interpolation=cv2.INTER_AREA)
    else:
        resized = image_np

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 45]
    _, buffer = cv2.imencode(".jpg", resized, encode_param)
    
    b64_string = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_string}"

# --- 5. EJECUCIÓN APP ---
apply_custom_style()
st.markdown("<h1>⛪ Tesorería CPJ 💸</h1><div class='title-underline'></div>", unsafe_allow_html=True)

client = get_gspread_client()
hoy = datetime.now()
nombre_hoja = f"{hoy.year}-{1 if 2 <= hoy.month <= 7 else 2}"

with st.form("registro_gasto", clear_on_submit=True):
    titulo = st.text_input("📝 Título del Gasto", placeholder="Ej: Carbón para evento")
    detalle = st.text_area("📄 Detalle", placeholder="Opcional...", height=70)
    cifra = st.number_input("💰 Cifra ($)", min_value=0, step=1)
    origen = st.selectbox("📈 Origen", ["Presupuesto", "Fondos CPJ", "Fondos CPJ (Efectivo)"])
    tarjeta = st.selectbox("💳 ¿Tarjeta CPJ?", ["SI", "NO"])
    
    resp, transf = "CPJ", False
    if tarjeta == "NO":
        resp = st.text_input("👤 Responsable")
        transf = st.checkbox("💸 ¿Se transfirió?")
    
    archivo = st.file_uploader("📸 Escanear Boleta", type=["jpg", "jpeg", "png"])
    submit = st.form_submit_button("🚀 REGISTRAR GASTO")

if submit:
    if not titulo or not cifra or not archivo:
        st.error("⚠️ Completa los datos obligatorios.")
    else:
        # --- ANIMACIÓN DE DESPEGUE ---
        launch_placeholder = st.empty()
        launch_placeholder.markdown("""
            <div class="launch-container">
                <div class="smoke" style="left: 40%; animation-delay: 0s;"></div>
                <div class="smoke" style="left: 50%; animation-delay: 0.2s;"></div>
                <div class="smoke" style="left: 60%; animation-delay: 0.1s;"></div>
                <div class="rocket-fly">🚀</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.spinner("Enviando a la estratosfera..."):
            orig_np, crop_np = scan_receipt(archivo.read())
            img_crop_url = image_to_short_base64(crop_np)
            
            sh = client.open_by_key(SPREADSHEET_ID)
            try:
                ws = sh.worksheet(nombre_hoja)
            except:
                ws = sh.add_worksheet(title=nombre_hoja, rows="500", cols="10")
                ws.append_row(['FECHA', 'TÍTULO', 'DETALLE', 'CIFRA', 'ORIGEN', '¿TARJETA CPJ?', 'RESPONSABLE', '¿SE TRANSFIRIÓ?', 'BOLETA', 'ORIGEN FOTO'])

            # Formatear la celda usando la fórmula IMAGE nativa de Sheets
            formula_imagen = f'=IMAGE("{img_crop_url}"; 1)'
            
            # --- CORRECCIÓN EN EL ORDEN EXACTO DE TU PRIMER CÓDIGO ---
            row = [
                hoy.strftime("%d/%m/%Y %H:%M"), 
                titulo, 
                detalle, 
                cifra, 
                origen, 
                tarjeta, 
                resp, 
                "SI" if transf else "NO", 
                formula_imagen,             # Columna I: Boleta en miniatura
                "NUBE (Base64)"             # Columna J: Indicador de origen
            ]
            
            try:
                ws.append_row(row, value_input_option='USER_ENTERED')
                launch_placeholder.empty()
                st.balloons()
                st.success("¡Gasto registrado con éxito! 🚀")
                st.image(crop_np, use_container_width=True)
            except Exception as e_api:
                launch_placeholder.empty()
                st.error(f"💥 Error al escribir en Google Sheets: {e_api}")
