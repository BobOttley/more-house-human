import os
import openai
import faiss
import pickle
import numpy as np
from tqdm import tqdm

# ─── Configuration ───────────────────────────────────────────────────────────
EMB_MODEL  = "text-embedding-3-small"
INDEX_PATH = "kb_index.faiss"
META_PATH  = "kb_meta.pkl"
KB_FOLDER  = "kb_chunks"

# ─── Load environment & OpenAI key ───────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ─── Read all KB chunk files ──────────────────────────────────────────────────
texts, keys = [], []
for fname in sorted(os.listdir(KB_FOLDER)):
    path = os.path.join(KB_FOLDER, fname)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            texts.append(f.read())
            keys.append(fname)

if not texts:
    raise ValueError(f"No files found in {KB_FOLDER}/")

# ─── Embed each chunk ─────────────────────────────────────────────────────────
print(f"Embedding {len(texts)} documents with model {EMB_MODEL}…")
embeddings = []
for txt in tqdm(texts, desc="Embedding"):
    resp = openai.Embedding.create(model=EMB_MODEL, input=txt)
    embeddings.append(resp["data"][0]["embedding"])

# ─── Build FAISS index ───────────────────────────────────────────────────────
dim = len(embeddings[0])
index = faiss.IndexFlatL2(dim)
index.add(np.array(embeddings, dtype="float32"))
faiss.write_index(index, INDEX_PATH)
print(f"✅ FAISS index saved to {INDEX_PATH}")

# ─── Save metadata ───────────────────────────────────────────────────────────
with open(META_PATH, "wb") as f:
    pickle.dump((keys, texts), f)
print(f"✅ Metadata saved to {META_PATH}")
