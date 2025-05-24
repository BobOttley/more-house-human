#!/usr/bin/env python3
import os
import sys
import io
import contextlib
import pickle

import numpy as np
import openai
import pdfplumber
from tqdm import tqdm
from dotenv import load_dotenv

# Load OpenAI key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("ERROR: OPENAI_API_KEY not set in .env")
    sys.exit(1)

# Settings
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
KB_FOLDER   = os.path.join(BASE_DIR, "kb_chunks")
EMB_MODEL   = "text-embedding-3-small"
VALID_EXT   = {".txt", ".md", ".pdf"}
CHUNK_CHARS = 4000
OUT_EMB     = os.path.join(BASE_DIR, "embeddings.pkl")
OUT_META    = os.path.join(BASE_DIR, "metadata.pkl")

def extract_pdf_pages(path):
    """Extract text from each PDF page, suppressing warnings."""
    pages = []
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                pages.append(p.extract_text() or "")
    return pages

def chunk_text(text, max_chars=CHUNK_CHARS):
    """Yield successive slices of text up to max_chars long."""
    for i in range(0, len(text), max_chars):
        yield text[i:i+max_chars]

# Prepare storage
embeddings = []  # list of numpy arrays
metadata   = []  # list of dicts

# Loop through files
for fname in tqdm(sorted(os.listdir(KB_FOLDER)), desc="Indexing"):
    ext = os.path.splitext(fname)[1].lower()
    if ext not in VALID_EXT:
        continue
    path = os.path.join(KB_FOLDER, fname)

    # Extract raw text blobs
    if ext == ".pdf":
        blobs = extract_pdf_pages(path)
    else:
        with open(path, encoding="utf-8") as f:
            blobs = [f.read()]

    # Chunk & embed each blob
    for page_idx, blob in enumerate(blobs):
        if not blob.strip():
            continue
        for chunk_idx, chunk in enumerate(chunk_text(blob)):
            resp = openai.embeddings.create(model=EMB_MODEL, input=chunk)
            vec  = np.array(resp.data[0].embedding, dtype="float32")
            embeddings.append(vec)
            metadata.append({
                "source": fname,
                "page": page_idx,
                "chunk": chunk_idx,
                "text": chunk
            })

# Save embeddings and metadata
with open(OUT_EMB, "wb") as f:
    pickle.dump(embeddings, f)
with open(OUT_META, "wb") as f:
    pickle.dump(metadata, f)

print("✅ Embeddings and metadata saved!")
