import os
import docx
import pptx
from pypdf import PdfReader

def load_all_document(base_path="data"):
    documents = []

    for root, dirs, files in os.walk(base_path):
        for file in files:
            path = os.path.join(root, file)

            if file.endswith(".pdf"):
                documents.append(read_pdf(path))

            elif file.endswith(".docx"):
                documents.append(read_docx(path))

            elif file.endswith(".pptx"):
                documents.append(read_pptx(path))

            elif file.endswith(".txt"):
                documents.append(read_txt(path))

    return documents


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
