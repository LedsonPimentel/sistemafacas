import streamlit as st
import sqlite3
import os
import datetime
from PIL import Image
import fitz  # PyMuPDF

# ---------------- CONFIGURAÇÕES ----------------
DB_PATH = "facas.db"
UPLOAD_DIR = "uploads"
THUMB_DIR = "thumbnails"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

# ---------------- BANCO DE DADOS ----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                pdf_filename TEXT,
                pdf_original_name TEXT,
                thumb TEXT,
                cdr_filename TEXT,
                cdr_original_name TEXT,
                uploaded_at TEXT
            )
        """)
init_db()

def faca_exists(name, pdf_filename):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM facas WHERE name = ? OR pdf_filename = ?", (name, pdf_filename))
    return cur.fetchone() is not None

def add_faca_db(name, description, pdf_info, cdr_info, thumb_path):
    if faca_exists(name, pdf_info[0] if pdf_info else None):
        raise ValueError("❌ Já existe uma faca com esse nome ou PDF!")

    uploaded_at = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    pdf_filename, pdf_original_name = pdf_info if pdf_info else (None, None)
    cdr_filename, cdr_original_name = cdr_info if cdr_info else (None, None)
    
    with conn:
        conn.execute(
            "INSERT INTO facas (name, description, pdf_filename, pdf_original_name, thumb, cdr_filename, cdr_original_name, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, description, pdf_filename, pdf_original_name, thumb_path, cdr_filename, cdr_original_name, uploaded_at)
        )

def get_facas_db(search=""):
    cur = conn.cursor()
    if search:
        cur.execute(
            "SELECT * FROM facas WHERE name LIKE ? OR description LIKE ? ORDER BY uploaded_at DESC",
            (f"%{search}%", f"%{search}%")
        )
    else:
        cur.execute("SELECT * FROM facas ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
    
    keys = ["id", "name", "description", "pdf_filename", "pdf_original_name", "thumb", "cdr_filename", "cdr_original_name", "uploaded_at"]
    return [dict(zip(keys, r)) for r in rows]

# ---------------- UTILIDADES ----------------
def save_file(uploaded_file, folder):
    if uploaded_file is None:
        return None, None
    filename = f"{datetime.datetime.now().timestamp()}_{uploaded_file.name}"
    filepath = os.path.join(folder, filename)
    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return filename, uploaded_file.name

def generate_thumbnail(pdf_path, thumb_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img.save(thumb_path, "PNG")
    return thumb_path

# ---------------- INTERFACE ----------------
st.set_page_config(page_title="Sistema de Facas", layout="wide")
st.title("🔪 Sistema de Facas")

menu = ["Adicionar Faca", "Listar Facas"]
choice = st.sidebar.radio("Menu", menu)

if choice == "Adicionar Faca":
    st.subheader("➕ Adicionar Nova Faca")

    with st.form("add_faca_form", clear_on_submit=True):
        name = st.text_input("Nome da faca")
        description = st.text_area("Descrição")
        pdf_file = st.file_uploader("Upload do PDF", type=["pdf"])
        cdr_file = st.file_uploader("Upload do Corel (CDR)", type=["cdr"])
        submit = st.form_submit_button("Salvar Faca")

        if submit:
            if not name:
                st.error("⚠️ O nome da faca é obrigatório!")
            elif not pdf_file:
                st.error("⚠️ É obrigatório enviar um arquivo PDF!")
            else:
                # Salvar arquivos
                pdf_filename, pdf_original_name = save_file(pdf_file, UPLOAD_DIR)
                cdr_filename, cdr_original_name = save_file(cdr_file, UPLOAD_DIR)

                pdf_info = (pdf_filename, pdf_original_name) if pdf_filename else None
                cdr_info = (cdr_filename, cdr_original_name) if cdr_filename else None

                # Criar thumbnail
                thumb_filename = f"{pdf_filename}.png"
                thumb_path = os.path.join(THUMB_DIR, thumb_filename)
                generate_thumbnail(os.path.join(UPLOAD_DIR, pdf_filename), thumb_path)

                try:
                    add_faca_db(name, description, pdf_info, cdr_info, thumb_path)
                    st.success("✅ Faca salva com sucesso!")
                except ValueError as e:
                    st.error(str(e))

elif choice == "Listar Facas":
    st.subheader("📂 Lista de Facas")

    search = st.text_input("🔍 Buscar faca")
    facas = get_facas_db(search)

    if facas:
        cols = st.columns(3)
        for i, faca in enumerate(facas):
            with cols[i % 3]:
                st.image(faca["thumb"], width=200)
                st.markdown(f"**{faca['name']}**")
                st.caption(faca["description"])
                if faca["pdf_filename"]:
                    st.download_button("📥 PDF", os.path.join(UPLOAD_DIR, faca["pdf_filename"]), file_name=faca["pdf_original_name"])
                if faca["cdr_filename"]:
                    st.download_button("📥 CDR", os.path.join(UPLOAD_DIR, faca["cdr_filename"]), file_name=faca["cdr_original_name"])
                st.write(f"🕒 {faca['uploaded_at']}")
    else:
        st.info("Nenhuma faca encontrada.")
