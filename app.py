# app.py
import streamlit as st
import sqlite3
from pathlib import Path
import uuid
import os
import io
import datetime
from PIL import Image
import fitz # PyMuPDF

# -------------------------
# Config
# -------------------------
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
THUMB_DIR = BASE_DIR / "thumbs"
DB_PATH = BASE_DIR / "facas.db"

UPLOAD_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Biblioteca de Facas", layout="wide")

# -------------------------
# DB helpers
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # Cria a tabela se ela não existir
    c.execute("""
    CREATE TABLE IF NOT EXISTS facas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        uploaded_at TEXT
    )
    """)
    
    # Adiciona as novas colunas se elas não existirem
    try:
        c.execute("ALTER TABLE facas ADD COLUMN pdf_filename TEXT")
    except sqlite3.OperationalError:
        pass 
    try:
        c.execute("ALTER TABLE facas ADD COLUMN pdf_original_name TEXT")
    except sqlite3.OperationalError:
        pass 
    try:
        c.execute("ALTER TABLE facas ADD COLUMN thumb TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE facas ADD COLUMN cdr_filename TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE facas ADD COLUMN cdr_original_name TEXT")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    return conn

conn = init_db()

def add_faca_db(name, description, pdf_info, cdr_info, thumb_path):
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
    # Verifica se as colunas existem antes de fazer a busca
    cur.execute("PRAGMA table_info(facas)")
    cols = [col[1] for col in cur.fetchall()]
    
    if "pdf_filename" not in cols or "cdr_filename" not in cols:
        st.error("O banco de dados não está atualizado. Por favor, reinicie o app.")
        return []

    if search:
        q = f"%{search}%"
        cur.execute("SELECT * FROM facas WHERE name LIKE ? OR description LIKE ? ORDER BY uploaded_at DESC", (q, q))
    else:
        cur.execute("SELECT * FROM facas ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
    
    keys = ["id", "name", "description", "pdf_filename", "pdf_original_name", "thumb", "cdr_filename", "cdr_original_name", "uploaded_at"]
    return [dict(zip(keys, r)) for r in rows]

def update_faca_db(faca_id, name, description, pdf_info=None, cdr_info=None, thumb_path=None):
    set_clauses = ["name=?", "description=?"]
    params = [name, description]

    if pdf_info:
        set_clauses.extend(["pdf_filename=?", "pdf_original_name=?", "thumb=?"])
        params.extend([pdf_info[0], pdf_info[1], thumb_path])
    
    if cdr_info:
        set_clauses.extend(["cdr_filename=?", "cdr_original_name=?"])
        params.extend([cdr_info[0], cdr_info[1]])

    params.append(faca_id)
    
    with conn:
        conn.execute(
            f"UPDATE facas SET {', '.join(set_clauses)} WHERE id=?",
            tuple(params)
        )

def delete_faca_db(faca_id):
    cur = conn.cursor()
    cur.execute("SELECT pdf_filename, thumb, cdr_filename FROM facas WHERE id=?", (faca_id,))
    row = cur.fetchone()
    if row:
        pdf_filename, thumb, cdr_filename = row
        for f in [pdf_filename, thumb, cdr_filename]:
            if f:
                try:
                    p = UPLOAD_DIR / f
                    if p.exists(): p.unlink()
                except Exception:
                    pass
    with conn:
        conn.execute("DELETE FROM facas WHERE id=?", (faca_id,))

# -------------------------
# File helpers
# -------------------------
def save_upload(uploaded_file):
    """Save uploaded file to uploads/ with unique name. Returns (stored_filename, original_name, filetype)."""
    ext = Path(uploaded_file.name).suffix.lower()
    uid = uuid.uuid4().hex
    stored_name = f"{uid}{ext}"
    saved_path = UPLOAD_DIR / stored_name
    with open(saved_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return stored_name, uploaded_file.name

def generate_pdf_thumbnail(file_path, page_number=0, zoom=2.0):
    """
    Generate thumbnail png for first page (or given page). Returns thumb filename (relative) or None on failure.
    """
    try:
        doc = fitz.open(str(file_path))
        if doc.page_count == 0:
            return None
        page = doc.load_page(page_number)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        thumb_bytes = pix.tobytes("png")
        thumb_name = f"{file_path.stem}_p{page_number}.png"
        thumb_path = THUMB_DIR / thumb_name
        with open(thumb_path, "wb") as f:
            f.write(thumb_bytes)
        return thumb_name
    except Exception:
        return None

def get_pdf_preview_images(file_path, max_pages=3, zoom=1.5):
    images = []
    try:
        doc = fitz.open(str(file_path))
        pages = min(max_pages, doc.page_count)
        for i in range(pages):
            page = doc.load_page(i)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes("png")
            images.append(png_bytes)
    except Exception:
        pass
    return images

# -------------------------
# UI
# -------------------------
st.title("📂 Biblioteca de Facas de Corte & Vinco")

# Gerenciamento de Exclusão com Session State
if 'delete_id' not in st.session_state:
    st.session_state.delete_id = None
if 'confirm_delete' not in st.session_state:
    st.session_state.confirm_delete = False

if st.session_state.confirm_delete and st.session_state.delete_id is not None:
    delete_faca_db(st.session_state.delete_id)
    st.success("✅ Registro excluído com sucesso!")
    st.session_state.delete_id = None
    st.session_state.confirm_delete = False
    st.rerun()

menu = st.sidebar.selectbox("Menu", ["Listar Facas", "Adicionar Faca", "Sobre"])

if menu == "Listar Facas":
    st.header("Listagem")
    search = st.text_input("🔍 Buscar por nome ou descrição")
    facas = get_facas_db(search)
    st.write(f"Encontradas: {len(facas)}")
    for f in facas:
        cols = st.columns([1,4,1])
        with cols[0]:
            if f["thumb"]:
                thumb_path = THUMB_DIR / f["thumb"]
                if thumb_path.exists():
                    st.image(str(thumb_path), use_container_width=True)
                else:
                    st.write("PDF")
            else:
                st.write("PDF")

        with cols[1]:
            st.subheader(f["name"])
            st.markdown(f"**Descrição:** {f['description'] or '_sem descrição_'}")
            st.caption(f"Enviado em {f['uploaded_at']}")

            exp = st.expander("Visualizar / Ações")
            with exp:
                # Botões de download para PDF e CDR
                download_cols = st.columns(2)
                
                with download_cols[0]:
                    if f["pdf_filename"] and (UPLOAD_DIR / f["pdf_filename"]).exists():
                        with open(UPLOAD_DIR / f["pdf_filename"], "rb") as fh:
                            st.download_button(
                                "⬇️ Baixar PDF", 
                                data=fh, 
                                file_name=f["pdf_original_name"] or f["pdf_filename"], 
                                key=f"{f['pdf_filename']}_pdf"
                            )
                
                with download_cols[1]:
                    if f["cdr_filename"] and (UPLOAD_DIR / f["cdr_filename"]).exists():
                        with open(UPLOAD_DIR / f["cdr_filename"], "rb") as fh:
                            st.download_button(
                                "⬇️ Baixar CDR", 
                                data=fh, 
                                file_name=f["cdr_original_name"] or f["cdr_filename"], 
                                key=f"{f['cdr_filename']}_cdr"
                            )

                # Preview do PDF
                if "pdf_filename" in f and f["pdf_filename"]:
                    file_path = UPLOAD_DIR / f["pdf_filename"]
                    if file_path.exists():
                        st.write("Preview do PDF (primeiras páginas):")
                        imgs = get_pdf_preview_images(file_path, max_pages=3)
                        if imgs:
                            for imgb in imgs:
                                st.image(imgb)
                        else:
                            st.info("Não foi possível gerar preview do PDF.")
                    else:
                        st.info("Arquivo PDF não encontrado. Recomendo exportar para PDF.")
                
                if st.button("✏️ Editar (nome/descrição)", key=f"edit_{f['id']}"):
                    with st.form(f"form_edit_{f['id']}"):
                        new_name = st.text_input("Novo Nome", value=f["name"])
                        new_desc = st.text_area("Nova Descrição", value=f["description"])
                        replace_pdf = st.file_uploader("Substituir arquivo PDF (opcional)", type=["pdf"])
                        replace_cdr = st.file_uploader("Substituir arquivo CDR (opcional)", type=None)
                        submitted = st.form_submit_button("Salvar alterações")
                        
                        if submitted:
                            pdf_info, cdr_info, thumb = None, None, f.get("thumb")
                            
                            if replace_pdf:
                                stored, orig = save_upload(replace_pdf)
                                pdf_info = (stored, orig)
                                thumb = generate_pdf_thumbnail(UPLOAD_DIR / stored)
                                try:
                                    old_p = UPLOAD_DIR / f["pdf_filename"]
                                    if old_p.exists(): old_p.unlink()
                                except: pass
                                try:
                                    old_t = THUMB_DIR / f["thumb"] if f["thumb"] else None
                                    if old_t and old_t.exists(): old_t.unlink()
                                except: pass
                            
                            if replace_cdr:
                                stored, orig = save_upload(replace_cdr)
                                cdr_info = (stored, orig)
                                try:
                                    old_c = UPLOAD_DIR / f["cdr_filename"]
                                    if old_c.exists(): old_c.unlink()
                                except: pass

                            update_faca_db(f["id"], new_name, new_desc, pdf_info, cdr_info, thumb)
                            st.success("✅ Atualizado!")
                            st.rerun()

        with cols[2]:
            st.write("") 
            if st.button("🗑️ Excluir", key=f"del_{f['id']}"):
                st.session_state.delete_id = f['id']
                st.session_state.confirm_delete = False
                st.rerun()

    if st.session_state.delete_id is not None:
        st.error(f"⚠️ **Confirma a exclusão do registro?**")
        st.markdown(f"**ID:** {st.session_state.delete_id}")
        st.markdown(f"**Nome:** {next((item['name'] for item in facas if item['id'] == st.session_state.delete_id), 'N/A')}")
        
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("Sim, quero excluir", key="confirm_yes"):
                st.session_state.confirm_delete = True
                st.rerun()
        with col_cancel:
            if st.button("Não, cancelar", key="confirm_no"):
                st.session_state.delete_id = None
                st.session_state.confirm_delete = False
                st.rerun()

elif menu == "Adicionar Faca":
    st.header("Adicionar nova faca")
    with st.form("form_add"):
        name = st.text_input("Nome da faca", help="Ex: 'Faca Cartão 295 - canto arredondado'")
        description = st.text_area("Descrição (opcional)")
        pdf_file = st.file_uploader("Arquivo PDF", type=["pdf"], help="Obrigatório para gerar o preview.")
        cdr_file = st.file_uploader("Arquivo CDR (ou similar)", type=None, help="Opcional. Pode ser .cdr, .ai, .svg, etc.")
        submitted = st.form_submit_button("Salvar")
        if submitted:
            if not name:
                st.error("É necessário informar um nome.")
            elif not pdf_file:
                st.error("É necessário enviar o arquivo PDF.")
            else:
                pdf_info = save_upload(pdf_file)
                thumb = generate_pdf_thumbnail(UPLOAD_DIR / pdf_info[0])
                
                cdr_info = None
                if cdr_file:
                    cdr_info = save_upload(cdr_file)
                    
                add_faca_db(name, description, pdf_info, cdr_info, thumb)
                st.success("✅ Faca adicionada!")
                st.rerun()

elif menu == "Sobre":
    st.header("Sobre este app")
    st.markdown("""
    - App simples para gerenciar suas facas de corte/vinco.
    - Upload salva arquivo em ./uploads e metadados em SQLite.
    - Preview automático para **PDF** (converte páginas em imagens usando PyMuPDF).
    - Para arquivos Corel (.cdr) e outros vetoriais, recomendo exportar para PDF/PNG antes de subir.
    """)
    st.markdown("Dúvidas ou quer que eu adapte algo (ex: login, tags, histórico de versões)? Me fala!")