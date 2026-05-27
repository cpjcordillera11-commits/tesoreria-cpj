import streamlit as st
import cv2
import numpy as np
import gspread
import os
import io
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. CONFIGURACIÓN E IDs ---
ROOT_FOLDER_ID = '1EXOjyMxXAL85E4l1zRM1wL-YLymMcrhU'
SPREADSHEET_ID = '1VlInzmxUY2YhkCLrM9Dc8K5coxWUCiQiYDkz5maQfns'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# --- 2. ESTILO Y ANIMACIÓN (CSS ACTUALIZADO) ---
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

        /* --- CONTENEDOR DEL COHETE (FIX: Z-INDEX ALTO) --- */
        .launch-container {
            position: fixed; /* Cambiado a fixed para que flote sobre todo */
            top: 40%;
            left: 50%;
            transform: translate(-50%, -50%);
            height: 200px;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: flex-end;
            z-index: 9999 !important; /* Trae el cohete al frente de todo */
            pointer-events: none; /* Evita que bloquee clics */
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

# --- 3. LÓGICA DE NEGOCIO ---
def get_gspread_client():
    # Intenta leer desde los secretos de Streamlit (Modo Nube)
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception as e:
        # Si no encuentra secretos, usa los archivos locales (Modo Desarrollo en tu PC)
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
    return gspread.authorize(creds), build('drive', 'v3', credentials=creds)

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

def upload_to_drive(name, image_np, folder_id, drive_service):
    _, buffer = cv2.imencode(".jpg", image_np)
    media = MediaIoBaseUpload(io.BytesIO(buffer), mimetype='image/jpeg', resumable=True)
    file = drive_service.files().create(body={'name': name, 'parents': [folder_id]}, media_body=media, fields='id, webViewLink').execute()
    return file.get('webViewLink')

def get_or_create_folder(parent_id, name, drive_service):
    q = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = drive_service.files().list(q=q).execute().get('files', [])
    if res: return res[0]['id']
    return drive_service.files().create(body={'name': name, 'parents': [parent_id], 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute().get('id')

# --- 4. EJECUCIÓN APP ---
apply_custom_style()
st.markdown("<h1>⛪ Tesorería CPJ 💸</h1><div class='title-underline'></div>", unsafe_allow_html=True)

try:
    client, drive_service = get_gspread_client()
except:
    st.info("Autoriza la app en la pestaña abierta.")
    st.stop()

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
        # --- ANIMACIÓN DE DESPEGUE (AL FRENTE) ---
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
            id_mes = get_or_create_folder(get_or_create_folder(ROOT_FOLDER_ID, nombre_hoja, drive_service), MESES[hoy.month-1], drive_service)
            
            b_name = f"{titulo}_{hoy.strftime('%d-%m-%Y_%H%M')}"
            l_crop = upload_to_drive(f"CROP_{b_name}.jpg", crop_np, id_mes, drive_service)
            l_orig = upload_to_drive(f"ORIG__{b_name}.jpg", orig_np, id_mes, drive_service)
            
            row = [hoy.strftime("%d/%m/%Y %H:%M"), titulo, detalle, cifra, origen, tarjeta, resp, "SI" if transf else "NO", f'=HYPERLINK("{l_crop}";"BOLETA")', f'=HYPERLINK("{l_orig}";"ORIGINAL")']
            client.open_by_key(SPREADSHEET_ID).worksheet(nombre_hoja).append_row(row, value_input_option='USER_ENTERED')
            
            launch_placeholder.empty()
            st.balloons()
            st.success("¡Gasto registrado! 🚀")
            st.image(crop_np, use_container_width=True)
