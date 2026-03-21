import os
import re
import asyncio
import tempfile
import warnings
import logging

# Suppress pypdf font-table noise ("Skipping broken line", "Odd-length string")
# These come from emoji/unicode in HathiTrust PDF font tables and are harmless
warnings.filterwarnings("ignore", message=".*Skipping broken line.*")
warnings.filterwarnings("ignore", message=".*Odd-length string.*")
logging.getLogger("pypdf").setLevel(logging.ERROR)

from pathlib import Path
from dotenv import load_dotenv
from pypdf import PdfReader
from typing import List, Dict, Optional
import json
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from llama_cloud import AsyncLlamaCloud, Timeout

load_dotenv(Path(__file__).parent.parent / ".env")

# File picker 
def select_pdf() -> str:
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")]
    )

# PDF metadata 
def extract_pdf_metadata(pdf_path: str) -> Dict:
    """Extract embedded PDF metadata via pypdf. No cost."""
    metadata = {
        "title": None, "author": None, "publication_date": None,
        "subject": None, "keywords": None, "creator": None,
        "producer": None, "page_count": None, "metadata_source": "embedded"
    }
    try:
        reader = PdfReader(pdf_path)
        info = reader.metadata
        metadata["page_count"] = len(reader.pages)
        if info:
            metadata["title"]    = info.title or None
            metadata["author"]   = info.author or None
            metadata["subject"]  = info.subject or None
            metadata["keywords"] = info.keywords or None
            metadata["creator"]  = info.creator or None
            metadata["producer"] = info.producer or None
            raw_date = info.get("/CreationDate")
            if raw_date:
                metadata["publication_date"] = _parse_pdf_date(raw_date)
    except Exception as e:
        print(f"Warning: Could not extract embedded metadata: {e}")

    known_distributors = ["hathitrust", "internet archive", "google", "proquest"]
    producer = (metadata.get("producer") or "").lower()
    creator  = (metadata.get("creator") or "").lower()
    if any(d in producer or d in creator for d in known_distributors):
        metadata["metadata_warning"] = (
            "Embedded metadata appears to be from a distributor, not the original publisher."
        )
    return metadata

def _parse_pdf_date(raw_date: str) -> Optional[str]:
    try:
        if raw_date.startswith("D:"):
            raw_date = raw_date[2:]
        return datetime.strptime(raw_date[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return raw_date


# Junk detection 
JUNK_TOKENS = {"nogle", "google"}

def _is_junk(text: str) -> bool:
    stripped = text.strip().lower()
    if len(stripped) < 20:
        return True
    return all(token in JUNK_TOKENS for token in stripped.split())

# Title page metadata extraction 
def extract_title_page_metadata(pages: List[Dict]) -> Dict:
    """
    Extract real title/author/year from the document title page.
    Used when embedded metadata belongs to a distributor (HathiTrust etc.).
    Heuristics:
      - Title: first H1 markdown heading, or longest ALL CAPS line
      - Author: line following "by" / "compiled by" / "edited by"
      - Year: first 4-digit year in Jim Crow era (1865-1965)
    """
    title = author = year = None
    candidates = [p for p in pages[:5] if not _is_junk(p["text"])]

    for page in candidates:
        lines = [l.strip() for l in page["text"].split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if title is None and line.startswith("# "):
                title = line.lstrip("# ").strip()
            if title is None and line.isupper() and len(line) > 10:
                title = line.strip()
            if author is None:
                ll = line.lower()
                if ll in ("by", "compiled by", "edited by", "prepared by"):
                    if i + 1 < len(lines):
                        author = lines[i + 1].strip()
                elif ll.startswith(("by ", "compiled by ", "edited by ")):
                    author = re.sub(
                        r"^(compiled by|edited by|prepared by|by)\s+",
                        "", line, flags=re.IGNORECASE
                    ).strip()
            if year is None:
                m = re.search(r"\b(18[6-9][0-9]|19[0-5][0-9]|196[0-5])\b", line)
                if m:
                    year = m.group(1)
        if title and author and year:
            break

    return {
        "title": title, "author": author,
        "publication_date": year, "metadata_source": "title_page"
    }

#  OCR 
# Minimum characters pypdf must extract for a page to be considered readable.
PYPDF_MIN_CHARS = 100

# If the ratio of spaces to total characters is below this, the text is likely
# a garbled run-together string (e.g. "ANACTtoestablish") and unusable.
# Real prose typically has a space ratio of 0.12-0.20+.
PYPDF_MIN_SPACE_RATIO = 0.08


def _pypdf_text_usable(text: str) -> bool:
    """
    Returns True if pypdf text looks like real readable prose.
    Rejects pages where text is too short or has almost no spaces
    (which indicates the font encoding is broken and words are merged).
    """
    if len(text) < PYPDF_MIN_CHARS:
        return False
    space_ratio = text.count(" ") / len(text)
    return space_ratio >= PYPDF_MIN_SPACE_RATIO

# Max pages per llama-cloud upload (stays well under the size limit)
LLAMAPARSE_CHUNK_PAGES = 150


def _build_pypdf_index(pdf_path: str) -> Dict[int, str]:
    """Extract embedded text from every page via pypdf. Fast, free, no API."""
    index: Dict[int, str] = {}
    try:
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            index[i] = (page.extract_text() or "").strip()
    except Exception as e:
        print(f"Warning: pypdf text extraction failed: {e}")
    return index


def _split_pdf_pages(pdf_path: str, page_indices: List[int], output_dir: str) -> List[str]:
    """
    Write a subset of pages (by 0-based index) from a PDF into chunked files.
    Uses pypdf — no extra dependencies.
    Returns list of output file paths.
    """
    from pypdf import PdfWriter
    reader = PdfReader(pdf_path)
    chunk_paths = []

    for chunk_start in range(0, len(page_indices), LLAMAPARSE_CHUNK_PAGES):
        chunk = page_indices[chunk_start:chunk_start + LLAMAPARSE_CHUNK_PAGES]
        part_num = (chunk_start // LLAMAPARSE_CHUNK_PAGES) + 1
        out_path = os.path.join(output_dir, f"scan_part{part_num:03d}.pdf")
        writer = PdfWriter()
        for idx in chunk:
            writer.add_page(reader.pages[idx])
        with open(out_path, "wb") as f:
            writer.write(f)
        chunk_paths.append((out_path, chunk))  # keep page indices for remapping

    return chunk_paths


async def _llamaparse_pages(pdf_path: str, page_indices: List[int], api_key: str) -> Dict[int, str]:
    """
    Send only the image-only pages to llama-cloud for OCR.
    Returns a dict of {original 0-based page index: ocr text}.
    """
    client = AsyncLlamaCloud(
        api_key=api_key,
        timeout=Timeout(connect=30.0, read=1200.0, write=1200.0, pool=1200.0),
    )

    results: Dict[int, str] = {}
    tmp_dir = tempfile.mkdtemp(prefix="jimcrow_llama_")

    try:
        chunks = _split_pdf_pages(pdf_path, page_indices, tmp_dir)
        print(f"  Sending {len(page_indices)} image pages to llama-cloud in {len(chunks)} part(s)...")

        for part_path, chunk_indices in chunks:
            label = os.path.basename(part_path)
            for attempt in range(1, 4):
                try:
                    print(f"  Uploading {label}...")
                    with open(part_path, "rb") as f:
                        file_obj = await client.files.create(file=f, purpose="parse")

                    result = await client.parsing.parse(
                        file_id=file_obj.id,
                        tier="cost_effective",
                        version="latest",
                        expand=["markdown"],
                        processing_options={"ocr_parameters": {"languages": ["en"]}},
                    )
                    break
                except Exception as e:
                    if attempt < 3:
                        wait = 30 * attempt
                        print(f"  Attempt {attempt} failed ({e.__class__.__name__}), retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        print(f"  ERROR: {label} failed after 3 attempts — skipping.")
                        result = None

            if result and result.markdown and result.markdown.pages:
                for i, page in enumerate(result.markdown.pages):
                    if i < len(chunk_indices):
                        orig_idx = chunk_indices[i]
                        results[orig_idx] = (page.markdown or "").strip()

    finally:
        import shutil
        shutil.rmtree(tmp_dir)

    return results


def ocr_pdf(pdf_path: str, api_key: str) -> List[Dict]:
    """
    Extract text from each PDF page using a two-pass strategy:

    Pass 1 — pypdf (free, instant):
        Pages with >= PYPDF_MIN_CHARS of embedded text are used as-is.

    Pass 2 — llama-cloud (paid, high quality):
        Image-only pages are batched and sent to llama-cloud for OCR.
        Only pages that need it consume API credits.

    Returns a list of {page_number, text, keyword_hits} dicts.

    Requires: pip install pypdf python-dotenv llama-cloud>=1.0
    """
    reader = PdfReader(pdf_path)
    total = len(reader.pages)

    print(f"Pass 1: Extracting embedded text from {total} pages via pypdf...")
    pypdf_index = _build_pypdf_index(pdf_path)

    pypdf_pages: Dict[int, str] = {}   # 0-based index → text
    scan_indices: List[int] = []       # pages that need llama-cloud

    for i in range(total):
        text = pypdf_index.get(i, "")
        if _pypdf_text_usable(text):
            pypdf_pages[i] = text
        else:
            scan_indices.append(i)

    print(f"  {len(pypdf_pages)} pages have embedded text, {len(scan_indices)} need OCR.")

    # send image-only pages to llama-cloud
    llama_pages: Dict[int, str] = {}
    if scan_indices and api_key:
        print(f"Pass 2: Sending {len(scan_indices)} pages to llama-cloud...")
        llama_pages = asyncio.run(_llamaparse_pages(pdf_path, scan_indices, api_key))
    elif scan_indices:
        print(f"Warning: {len(scan_indices)} image-only pages skipped (no LLAMA_API_KEY).")

    # Merge results in page order
    pages = []
    for i in range(total):
        if i in pypdf_pages:
            text, method = pypdf_pages[i], "pypdf"
        elif i in llama_pages:
            text, method = llama_pages[i], "llama_cloud"
        else:
            continue  # no text from either source

        if not _is_junk(text):
            pages.append({
                "page_number":  i + 1,
                "text":         text,
                "keyword_hits": [],
            })

    print(f"  Done: {len(pypdf_pages)} pypdf, {len(llama_pages)} llama-cloud, {len(pages)} total pages.")
    return pages

# Keyword search 
KEYWORDS = [
    "jim crow", "segregation", "separate but equal",
    "colored", "negro", "white only", "colored only",
    "racial discrimination", "miscegenation",
    "poll tax", "literacy test", "grandfather clause", "marriage"
]


def find_references(pages: List[Dict], metadata: Dict, filename: str) -> Dict:
    """
    Search all pages for Jim Crow keywords and assemble the output document.
    All pages included so the LLM can catch references keyword search missed.
    """
    keyword_refs = []
    pages_with_hits: set = set()

    for page in pages:
        lines = page["text"].split("\n")
        hits: List[str] = []

        for i, line in enumerate(lines):
            ll = line.lower()
            for kw in KEYWORDS:
                if kw in ll:
                    context = "\n".join(lines[max(0, i - 2):min(len(lines), i + 3)])
                    keyword_refs.append({
                        "keyword":             kw,
                        "page_number":         page["page_number"],
                        "line_number_in_page": i + 1,
                        "context":             context,
                    })
                    if kw not in hits:
                        hits.append(kw)
                    break  # one match per line

        if hits:
            page["keyword_hits"] = hits
            pages_with_hits.add(page["page_number"])

    pub = metadata.get("publication_date") or ""
    ym = re.search(r"\b(1[89]\d{2})\b", pub)
    year = int(ym.group(1)) if ym else None

    return {
        "source": {
            "filename":      filename,
            "title":         metadata.get("title"),
            "author":        metadata.get("author"),
            "year":          year,
            "document_type": None,
        },
        "pages": pages,
        "keyword_references": keyword_refs,
        "statistics": {
            "total_pages":             metadata.get("page_count"),
            "pages_with_keyword_hits": len(pages_with_hits),
            "total_keyword_hits":      len(keyword_refs),
        },
        "ocr_metadata": {
            "engine":         "pypdf+llama_cloud",
            "result_type":    "text",
            "processed_at":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "format_version": "2.0",
        },
    }


def save_results(results: Dict, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {output_path}")

# Main 
def main():
    print("Please select a PDF file")
    pdf_path = select_pdf()
    if not pdf_path or not os.path.exists(pdf_path):
        print("No file selected. Exiting.")
        return

    filename = os.path.basename(pdf_path)

    # Embedded metadata (free)
    print("Extracting document metadata...")
    metadata = extract_pdf_metadata(pdf_path)

    # pypdf for embedded text, llama-cloud for image-only pages
    api_key = os.getenv("LLAMA_API_KEY")
    pages = ocr_pdf(pdf_path, api_key=api_key)
    if not pages:
        print("Error: No pages extracted. Check your PDF and LLAMA_API_KEY.")
        return

    # Resolve metadata from title page if needed
    if metadata.get("metadata_warning") or not all(
        metadata.get(k) for k in ("title", "author", "publication_date")
    ):
        print("Extracting metadata from title page...")
        tp = extract_title_page_metadata(pages)
        for field in ("title", "author", "publication_date"):
            if tp.get(field):
                metadata[field] = tp[field]
                metadata["metadata_source"] = "title_page"
        print(f"  Title:  {tp.get('title') or '(not found)'}")
        print(f"  Author: {tp.get('author') or '(not found)'}")
        print(f"  Date:   {tp.get('publication_date') or '(not found)'}")

    missing = [k for k in ("title", "author", "publication_date") if not metadata.get(k)]
    if missing:
        print(f"Note: Could not resolve {missing} - fill in manually in the output JSON.")

    # Find keywords and build output
    results = find_references(pages, metadata, filename)

    output_filename = f"{os.path.splitext(filename)[0]}_results.json"
    save_results(results, output_filename)

    s = results["statistics"]
    print("\nExtraction complete!")

if __name__ == "__main__":
    main()