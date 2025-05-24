#!/usr/bin/env python3
import os
import pickle
import requests
from readability import Document
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dotenv import load_dotenv
import pdfplumber
import tiktoken

# ─── Configuration ────────────────────────────────────────────────────────────
load_dotenv()
KB_FOLDER = os.path.join(os.path.dirname(__file__), "kb_chunks")
os.makedirs(KB_FOLDER, exist_ok=True)

# ─── Full list of pages to scrape ─────────────────────────────────────────────
URLS = [
    "https://www.morehouse.org.uk/",
    "https://www.morehouse.org.uk/admissions/our-open-events/",
    "https://www.morehouse.org.uk/our-school/meet-the-head/",
    "https://www.morehouse.org.uk/our-school/equity-diversity-and-inclusion-edi/",
    "https://www.morehouse.org.uk/our-school/our-ethos/",
    "https://www.morehouse.org.uk/beyond-the-classroom/faith-life/",
    "https://www.morehouse.org.uk/our-school/pastoral-care/",
    "https://www.morehouse.org.uk/our-school/more-house-stories/",
    "https://www.morehouse.org.uk/our-school/history/",
    "https://www.morehouse.org.uk/our-school/houses/",
    "https://www.morehouse.org.uk/pre-senior/",
    "https://www.morehouse.org.uk/learning/academic-life/",
    "https://www.morehouse.org.uk/learning/subjects/",
    "https://www.morehouse.org.uk/learning/sixth-form/",
    "https://www.morehouse.org.uk/learning/our-creative-suite/",
    "https://www.morehouse.org.uk/learning/be-more/",
    "https://www.morehouse.org.uk/learning/learning-support/",
    "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "https://www.morehouse.org.uk/beyond-the-classroom/sport/",
    "https://www.morehouse.org.uk/beyond-the-classroom/co-curricular-programme/",
    "https://www.morehouse.org.uk/beyond-the-classroom/city-curriculum/",
    "https://www.morehouse.org.uk/partnerships/",
    "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "https://www.morehouse.org.uk/information/safeguarding/",
    "https://www.morehouse.org.uk/information/school-uniform/",
    "https://www.morehouse.org.uk/information/lettings/",
    "https://www.morehouse.org.uk/information/school-lunches/",
    "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "https://www.morehouse.org.uk/information/school-policies/",
    "https://www.morehouse.org.uk/information/inspection-reports/",
    "https://www.morehouse.org.uk/contact/",
    "https://www.morehouse.org.uk/news-and-calendar/calendar/",
    "https://www.morehouse.org.uk/upcoming-events/",
    "https://www.morehouse.org.uk/admissions/fees/",
    "https://www.morehouse.org.uk/senior-school/",
    "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "https://www.morehouse.org.uk/wp-content/uploads/2022/05/11-consortium-faqs.pdf",
    "https://www.morehouse.org.uk/wp-content/uploads/2023/06/registration-form-2023.pdf",
    "https://www.morehouse.org.uk/international-applications-and-visas/",
    "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "https://www.morehouse.org.uk/news-and-calendar/news/",
]

# ─── Chunking parameters ──────────────────────────────────────────────────────
CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50
tokenizer     = tiktoken.get_encoding("cl100k_base")

def text_to_chunks(text):
    tokens = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + CHUNK_SIZE
        chunks.append(tokenizer.decode(tokens[start:end]))
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

# ─── Scrape & chunk ─────────────────────────────────────────────────────────—
metadata = []

for url in URLS:
    print("Fetching:", url)
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print("  ⚠️ fetch failed:", e)
        continue

    # Extract full text
    if url.lower().endswith(".pdf"):
        try:
            with open("temp.pdf", "wb") as f:
                f.write(res.content)
            text = ""
            with pdfplumber.open("temp.pdf") as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
        finally:
            os.remove("temp.pdf")
        full_text = text
    else:
        soup_full = BeautifulSoup(res.text, "html.parser")
        tables = []
        for table in soup_full.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all(["td","th"])]
                if cols:
                    rows.append(" | ".join(cols))
            if rows:
                tables.append("TABLE:\n" + "\n".join(rows))

        doc = Document(res.text)
        article_html = doc.summary()
        article_text = BeautifulSoup(article_html, "html.parser").get_text(separator="\n").strip()
        full_text = "\n\n".join(tables + [article_text])

    # Chunking
    chunks = text_to_chunks(full_text)
    print(f"  → {len(chunks)} chunks")

    for chunk in chunks:
        metadata.append({"text": chunk, "url": url})

# ─── Save metadata.pkl ─────────────────────────────────────────────────────────
with open("metadata.pkl", "wb") as f:
    pickle.dump(metadata, f)
print(f"Saved metadata ({len(metadata)} chunks) to metadata.pkl")
