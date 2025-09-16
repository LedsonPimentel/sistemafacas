
import streamlit as st

import sqlite3

from pathlib import Path

import uuid

import os

import io

import datetime

from PIL import Image

import fitz # PyMuPDF



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

    c.execute("""

    CREATE TABLE IF NOT EXISTS facas (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        description TEXT,

        filename TEXT NOT NULL,

        original_name TEXT,

        filetype TEXT,

        thumb TEXT,

        uploaded_at TEXT

    )

    """)

    conn.commit()

    return conn



conn = init_db()



def add_faca_db(name, description, filename, original_name, filetype, thumb_path):

    uploaded_at = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    with conn:

        conn.execute(

            "INSERT INTO facas (name, description, filename, original_name, filetype, thumb, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",

            (name, description, filename, original_name, filetype, thumb_path, uploaded_at)

        )



def get_facas_db(search=""):

    cur = conn.cursor()

    if search:

        q = f"%{search}%"

        cur.execute("SELECT * FROM facas WHERE name LIKE ? OR description LIKE ? ORDER BY uploaded_at DESC", (q, q))

    else:

        cur.execute("SELECT * FROM facas ORDER BY uploaded_at DESC")

    rows = cur.fetchall()

    # return as dicts

    keys = ["id","name","description","filename","original_name","filetype","thumb","uploaded_at"]

    return [dict(zip(keys, r)) for r in rows]



def update_faca_db(faca_id, name, description, filename=None, original_name=None, filetype=None, thumb=None):

    if filename:

        with conn:

            conn.execute("""UPDATE facas SET name=?, description=?, filename=?, original_name=?, filetype=?, thumb=? WHERE id=?""",

                            (name, description, filename, original_name, filetype, thumb, faca_id))

    else:

        with conn:

            conn.execute("UPDATE facas SET name=?, description=? WHERE id=?", (name, description, faca_id))



def delete_faca_db(faca_id):

    # fetch filenames to delete files

    cur = conn.cursor()

    cur.execute("SELECT filename, thumb FROM facas WHERE id=?", (faca_id,))

    row = cur.fetchone()

    if row:

        filename, thumb = row

        try:

            p = UPLOAD_DIR / filename

            if p.exists(): p.unlink()

        except Exception:

            pass

        try:

            t = THUMB_DIR / thumb

            if t and t.exists(): t.unlink()

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

    filetype = ext.lstrip(".")

    return stored_name, uploaded_file.name, filetype



def generate_pdf_thumbnail(file_path, page_number=0, zoom=2.0):

    """

    Generate thumbnail png for first page (or given page). Returns thumb filename (relative) or None on failure.

    Uses PyMuPDF (fitz).

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

    except Exception as e:

        # thumbnail generation failed (maybe not a PDF)

        return None



def get_pdf_preview_images(file_path, max_pages=3, zoom=1.5):

    """

    Return a list of bytes objects (png) for previewing up to max_pages pages.

    We don't force saving; return bytes so Streamlit can show them directly.

    """

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

st.title("📂 Biblioteca de Facas de Corte")



# -------------------------

# Gerenciamento de Exclusão com Session State

# -------------------------

# Inicializa a sessão de estado para controlar a exclusão.

if 'delete_id' not in st.session_state:

    st.session_state.delete_id = None

if 'confirm_delete' not in st.session_state:

    st.session_state.confirm_delete = False



# Lógica para exclusão (processa o estado antes de renderizar a página)

if st.session_state.confirm_delete and st.session_state.delete_id is not None:

    delete_faca_db(st.session_state.delete_id)

    st.success("✅ Registro excluído com sucesso!")

    st.session_state.delete_id = None

    st.session_state.confirm_delete = False

    st.rerun()



menu = st.sidebar.selectbox("Menu", ["Listar Facas", "Adicionar Faca"])



if menu == "Listar Facas":

    st.header("Listagem")

    search = st.text_input("🔍 Buscar por nome ou descrição")

    facas = get_facas_db(search)

    st.write(f"Encontradas: {len(facas)}")

    for f in facas:

        cols = st.columns([1,4,1])

        with cols[0]:

            # thumbnail or icon

            if f["thumb"]:

                thumb_path = THUMB_DIR / f["thumb"]

                if thumb_path.exists():

                    st.image(str(thumb_path), use_container_width=True)

                else:

                    # try generate on the fly if it's a pdf

                    upath = UPLOAD_DIR / f["filename"]

                    if upath.exists() and f["filetype"]=="pdf":

                        thumb = generate_pdf_thumbnail(upath)

                        if thumb:

                            st.image(str(THUMB_DIR / thumb), use_container_width=True)

                        else:

                            st.write(f["filetype"].upper())

                    else:

                        st.write(f["filetype"].upper())

            else:

                st.write(f["filetype"].upper())



        with cols[1]:

            st.subheader(f["name"])

            st.markdown(f"**Descrição:** {f['description'] or '_sem descrição_'}")

            st.caption(f"Arquivo: {f['original_name'] or f['filename']} — enviado em {f['uploaded_at']}")



            exp = st.expander("Visualizar / Ações")

            with exp:

                file_path = UPLOAD_DIR / f["filename"]

                if f["filetype"] == "pdf" and file_path.exists():

                    st.write("Preview (primeiras páginas):")

                    imgs = get_pdf_preview_images(file_path, max_pages=3)

                    if imgs:

                        for imgb in imgs:

                            st.image(imgb)

                    else:

                        st.info("Não foi possível gerar preview do PDF.")

                else:

                    st.info("Preview não disponível para este tipo de arquivo. Recomendo exportar para PDF/PNG.")



                # Download button

                with open(file_path, "rb") as fh:

                    st.download_button("⬇️ Baixar arquivo", data=fh, file_name=f["original_name"] or f["filename"], key=f["filename"])



                # Edit / Replace

                if st.button("✏️ Editar (nome/descrição)", key=f"edit_{f['id']}"):

                    # show inline edit form

                    with st.form(f"form_edit_{f['id']}"):

                        new_name = st.text_input("Nome", value=f["name"])

                        new_desc = st.text_area("Descrição", value=f["description"])

                        replace_file = st.file_uploader("Substituir arquivo (opcional)", type=None)

                        submitted = st.form_submit_button("Salvar alterações")

                        if submitted:

                            if replace_file:

                                # save new file and generate thumb if pdf

                                stored, orig, ftype = save_upload(replace_file)

                                thumb = None

                                if ftype == "pdf":

                                    thumb = generate_pdf_thumbnail(UPLOAD_DIR / stored)

                                # delete old files

                                try:

                                    oldp = UPLOAD_DIR / f["filename"]

                                    if oldp.exists(): oldp.unlink()

                                except: pass

                                try:

                                    oldt = THUMB_DIR / f["thumb"] if f["thumb"] else None

                                    if oldt and oldt.exists(): oldt.unlink()

                                except: pass

                                update_faca_db(f["id"], new_name, new_desc, stored, orig, ftype, thumb)

                            else:

                                update_faca_db(f["id"], new_name, new_desc)

                            st.success("✅ Atualizado!")

                            st.rerun()

        

        with cols[2]:

            st.write("")  # spacer

            # Botão de exclusão - Inicia o processo de confirmação

            if st.button("🗑️ Excluir", key=f"del_{f['id']}"):

                st.session_state.delete_id = f['id']

                st.session_state.confirm_delete = False

                st.rerun()



    # Se um ID de exclusão está definido, exibe a confirmação

    if st.session_state.delete_id is not None:

        st.error(f"⚠️ **Confirma a exclusão do registro?**")

        st.markdown(f"**ID:** {st.session_state.delete_id}")

        st.markdown(f"**Nome:** {next((item['name'] for item in facas if item['id'] == st.session_state.delete_id), 'N/A')}")

        

        # Botões de confirmação

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

        uploaded_file = st.file_uploader("Arquivo (PDF, CDR, SVG, etc.)", type=None)

        submitted = st.form_submit_button("Salvar")

        if submitted:

            if not name:

                st.error("É necessário informar um nome.")

            elif not uploaded_file:

                st.error("Envie um arquivo.")

            else:

                stored_fname, orig_name, ftype = save_upload(uploaded_file)

                thumb = None

                if ftype == "pdf":

                    thumb = generate_pdf_thumbnail(UPLOAD_DIR / stored_fname)

                add_faca_db(name, description, stored_fname, orig_name, ftype, thumb)

                st.success("✅ Faca adicionada!")

                st.rerun()