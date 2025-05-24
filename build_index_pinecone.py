#!/usr/bin/env python3
import os
import sys
import io
import contextlib
import openai
import pinecone
import pdfplumber
from tqdm import tqdm
from dotenv import load_dotenv

# ─── Load env & sanity-check keys & env ───────────────────────────────────────
load_dotenv()

import os
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    print(f"✅ .env file found at: {env_path}")
else:
    print(f"❌ .env file not found at: {env_path}")
    sys.exit(1)

# OpenAI key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("❌ ERROR: OPENAI_API_KEY not set in .env")
    sys.exit(1)

# Pinecone key
pine_key = os.getenv("PINECONE_API_KEY")
if not pine_key:
    print("❌ ERROR: PINECONE_API_KEY not set in .env")
    sys.exit(1)

# Pinecone environment (the string between .svc. and .pinecone.io in your host URL)
pine_env = os.getenv("PINECONE_ENVIRONMENT")
if not pine_env:
    print("❌ ERROR: PINECONE_ENVIRONMENT not set in .env")
    sys.exit(1)

# Pinecone index name
index_name = os.getenv("PINECONE_INDEX")
if not index_name:
    print("❌ ERROR: PINECONE_INDEX not set in .env")
    sys.exit(1)

print(f"🔑 Pinecone key loaded ({len(pine_key)} chars), env: {pine_env}, index: {index_name}")

# ─── Init Pinecone & smoke-test connection ────────────────────────────────────
pinecone.init(api_key=pine_key, environment=pine_env)
try:
    available = pinecone.list_indexes()
    print("🗂️  Pinecone indexes available:", available)
    if index_name not in available:
        print(f"❌ ERROR: Index '{index_name}' not found.")
        sys.exit(1)
except Exception as e:
    print(f"❌ ERROR: Unable to connect to Pinecone: {e}")
    sys.exit(1)

index = pinecone.Index(index_name)

# ─── Paths & settings ────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
KB_FOLDER   = os.path.join(BASE_DIR, "kb_chunks")
EMB_MODEL   = "text-embedding-3-small"
VALID_EXT   = {".txt", ".md", ".pdf"}
CHUNK_CHARS = 4000   # safe chunk size

if not os.path.isdir(KB_FOLDER):
    print(f"❌ ERROR: folder not found at {KB_FOLDER}")
    sys.exit(1)

def extract_pdf_pages(path):
    """Extract text from each PDF page, suppressing CropBox warnings."""
    pages = []
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                pages.append(p.extract_text() or "")
    return pages

def chunk_text(text, max_chars=CHUNK_CHARS):
    """Yield slices of text up to max_chars long."""
    for i in range(0, len(text), max_chars):
        yield text[i:i + max_chars]

# ─── Upsert each chunk into Pinecone ─────────────────────────────────────────
for fname in tqdm(sorted(os.listdir(KB_FOLDER)), desc="Indexing"):
    ext = os.path.splitext(fname)[1].lower()
    if ext not in VALID_EXT:
        print(f"  – Skipping unsupported file: {fname}")
        continue

    path = os.path.join(KB_FOLDER, fname)
    try:
        # Extract blobs (pages for PDFs, whole text for others)
        if ext == ".pdf":
            blobs = extract_pdf_pages(path)
        else:
            with open(path, "r", encoding="utf-8") as f:
                blobs = [f.read()]

        # Chunk & embed each blob
        for page_idx, blob in enumerate(blobs):
            if not blob.strip():
                continue
            for chunk_idx, chunk in enumerate(chunk_text(blob)):
                resp = openai.embeddings.create(model=EMB_MODEL, input=chunk)
                vector = resp.data[0].embedding

                upsert_id = f"{fname}::p{page_idx}::c{chunk_idx}"
                metadata = {"source": fname, "page": page_idx, "chunk": chunk_idx}

                index.upsert([(upsert_id, vector, metadata)])

    except Exception as e:
        print(f"  – Skipping {fname} due to error: {e}")

print("✅ Pinecone index populated!")
