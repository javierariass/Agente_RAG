import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import docx
import pptx
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".doc"}


def iter_document_paths(base_path):
    for root, _, files in os.walk(base_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                yield os.path.join(root, file)


def read_document(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return read_pdf(path)
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pptx":
        return read_pptx(path)
    if ext == ".txt":
        return read_txt(path)
    if ext == ".doc":
        return read_doc(path)
    return ""


def read_doc(path):
    """Lee un .doc antiguo (OLE2) convirtiendolo con LibreOffice/antiword si
    estan instalados. Si no hay convertidor disponible devuelve texto vacio y
    el documento simplemente se omite (no rompe el servicio)."""
    if shutil.which("antiword"):
        try:
            result = subprocess.run(
                ["antiword", path],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception:
            pass

    converter = shutil.which("soffice") or shutil.which("libreoffice")
    if not converter:
        return ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [converter, "--headless", "--convert-to", "txt:Text",
                 "--outdir", tmp, path],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 0:
                return ""
            txt_files = [f for f in os.listdir(tmp) if f.lower().endswith(".txt")]
            if not txt_files:
                return ""
            with open(os.path.join(tmp, txt_files[0]), "r",
                      encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception:
        return ""

def load_all_document(base_path="data"):
    """Devuelve una lista de tuplas (texto, fuente) con el contenido de cada
    documento. La `fuente` es la ruta relativa al directorio de datos."""
    paths = list(iter_document_paths(base_path))
    if not paths:
        return []

    max_workers = min(8, max(2, (os.cpu_count() or 2)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        contents = list(executor.map(read_document, paths))

    docs = []
    for path, text in zip(paths, contents):
        if text and text.strip():
            rel = os.path.relpath(path, base_path)
            docs.append((text, rel))
    return docs


def read_pdf(path):
    text = ""
    reader = PdfReader(path)
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text


def read_docx(path):
    doc = docx.Document(path)
    return "\n".join([para.text for para in doc.paragraphs])


def read_pptx(path):
    presentation = pptx.Presentation(path)
    text = ""
    for slide in presentation.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text += shape.text + "\n"
    return text


def read_txt(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()
