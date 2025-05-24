#!/usr/bin/env python3
import os
import pickle
import numpy as np
import openai
import tiktoken
from dotenv import load_dotenv

# Load OpenAI API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

# Embedding model (must match app.py)
EMB_MODEL = "text-embedding-3-small"

# Directory containing scraped text files
KB_FOLDER = "kb_chunks"

# Maximum token limit for the embedding model
MAX_TOKENS = 8192

# Initialize tokenizer
tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")

# Function to count tokens
def count_tokens(text):
    return len(tokenizer.encode(text))

# Function to generate embeddings
def generate_embeddings(text_chunks):
    embeddings = []
    for chunk in text_chunks:
        # Check token count
        token_count = count_tokens(chunk["text"])
        if token_count > MAX_TOKENS:
            print(f"Skipping chunk (too many tokens: {token_count}): {chunk['text'][:50]}...")
            embeddings.append(None)
            continue
        try:
            response = openai.embeddings.create(model=EMB_MODEL, input=chunk["text"])
            embedding = response.data[0].embedding
            embeddings.append(embedding)
        except Exception as e:
            print(f"Error generating embedding for chunk: {chunk['text'][:50]}... - {e}")
            embeddings.append(None)
    return embeddings

# Mapping of filenames to source URLs (simplified for key files)
FILENAME_TO_URL = {
    "admissions_joining-more-house.txt": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    # Add other mappings as needed
}

# Load and chunk the text from all files in kb_chunks
def load_and_chunk_text(directory=KB_FOLDER):
    text_chunks = []
    for filename in os.listdir(directory):
        # Skip non-text files
        if filename.startswith(".") or not filename.endswith((".txt", ".pdf")):
            print(f"Skipping non-text file: {filename}")
            continue
        filepath = os.path.join(directory, filename)
        print(f"Reading file: {filepath}")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            print(f"  ⚠️ UTF-8 decoding failed for {filepath}, trying Latin-1...")
            try:
                with open(filepath, "r", encoding="latin-1") as f:
                    text = f.read()
            except Exception as e:
                print(f"  ⚠️ Failed to read {filepath}: {e}")
                continue
        # Split into chunks (max 600 words per chunk, but try to keep related content together)
        paragraphs = text.split("\n\n")
        current_chunk = ""
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            # Check word count of current chunk + new paragraph
            if len(current_chunk.split()) + len(paragraph.split()) <= 600:
                current_chunk += "\n\n" + paragraph if current_chunk else paragraph
            else:
                if current_chunk:
                    # Include the source URL in the chunk metadata
                    chunk_data = {
                        "text": current_chunk,
                        "source_url": FILENAME_TO_URL.get(filename, "https://www.morehouse.org.uk")
                    }
                    text_chunks.append(chunk_data)
                current_chunk = paragraph
        if current_chunk:
            chunk_data = {
                "text": current_chunk,
                "source_url": FILENAME_TO_URL.get(filename, "https://www.morehouse.org.uk")
            }
            text_chunks.append(chunk_data)
    return text_chunks

# Main process
if __name__ == "__main__":
    # Step 1: Load and chunk the text
    print("Loading and chunking text from kb_chunks...")
    text_chunks = load_and_chunk_text()

    # Step 2: Generate embeddings
    print("Generating embeddings...")
    embeddings = generate_embeddings(text_chunks)
    embeddings = [emb for emb, chunk in zip(embeddings, text_chunks) if emb is not None]
    text_chunks = [chunk for emb, chunk in zip(embeddings, text_chunks) if emb is not None]

    # Step 3: Save embeddings and metadata
    print("Saving embeddings and metadata...")
    embeddings_array = np.array(embeddings, dtype="float32")
    with open("embeddings.pkl", "wb") as f:
        pickle.dump(embeddings_array, f)

    # Save metadata with source URLs
    metadata = [{"text": chunk["text"], "source_url": chunk["source_url"]} for chunk in text_chunks]
    with open("metadata.pkl", "wb") as f:
        pickle.dump(metadata, f)

    print(f"Generated {len(embeddings)} embeddings and saved to embeddings.pkl and metadata.pkl")
