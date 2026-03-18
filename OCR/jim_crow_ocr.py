import os
import re
import asyncio
import tempfile

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

def select_pdf() -> str:
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")]
    )

def extract_pdf_metadata(pdf_path: str) -> Dict:
    """Extract embedded PDF metadata via pypdf. No API cost."""
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
            raw = info.get("/CreationDate")
            if raw:
                metadata["publication_date"] = _parse_pdf_date(raw)
    except Exception as e:
        print(f"Warning: Could not extract embedded metadata: {e}")

    # Flag distributor metadata so we know to check the title page instead
    distributors = ["hathitrust", "internet archive", "google", "proquest"]
    producer = (metadata.get("producer") or "").lower()
    creator  = (metadata.get("creator") or "").lower()
    if any(d in producer or d in creator for d in distributors):
        metadata["metadata_warning"] = (
            "Embedded metadata appears to be from a distributor, not the original publisher."
        )
    return metadata


def _parse_pdf_date(raw: str) -> Optional[str]:
    """Convert PDF date string e.g. 'D:20050915' → '2005-09-15'."""
    try:
        if raw.startswith("D:"):
            raw = raw[2:]
        return datetime.strptime(raw[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return raw

def extract_title_page_metadata(chunks: List[Dict]) -> Dict:
    """
    Pull real title/author/year from the document's own title page.
    Used when embedded metadata belongs to a distributor (HathiTrust etc.).
    Heuristics:
      - Title:  first markdown H1 heading (# ...)
      - Author: line following 'by' / 'compiled by' / 'edited by'
      - Year:   first 4-digit year in the Jim Crow era (1865–1965)
    """
    title = author = year = None
    candidates = [c for c in chunks[:5] if not _is_junk(c["text"])]

    for chunk in candidates:
        lines = [l.strip() for l in chunk["text"].split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if title is None and line.startswith("# "):
                title = line.lstrip("# ").strip()
            if author is None:
                ll = line.lower()
                if ll in ("by", "compiled by", "edited by", "prepared by"):
                    if i + 1 < len(lines):
                        author = lines[i + 1].strip()
                elif ll.startswith(("by ", "compiled by ", "edited by ")):
                    author = re.sub(
                        r"^(compiled by|edited by|prepared by|by)\s+", "",
                        line, flags=re.IGNORECASE
                    ).strip()
            if year is None:
                m = re.search(r"\b(18[6-9]\d|19[0-5]\d|196[0-5])\b", line)
                if m:
                    year = m.group(1)
        if title and author and year:
            break

    return {"title": title, "author": author, "publication_date": year,
            "metadata_source": "title_page"}

_JUNK = {"nogle", "google"}

def _is_junk(text: str) -> bool:
    """Filter out distributor watermark pages (HathiTrust, Google, etc.)."""
    s = text.strip().lower()
    return len(s) < 20 or all(t in _JUNK for t in s.split())

def split_pdf(pdf_path: str, output_dir: str, pages_per_chunk: int) -> List[str]:
    """
    Split a large PDF into smaller parts using pypdf.
    Uses short names (part001.pdf) to avoid Windows MAX_PATH issues.
    """
    from pypdf import PdfWriter
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    parts = []

    for start in range(0, total, pages_per_chunk):
        end = min(start + pages_per_chunk, total)
        part_num = (start // pages_per_chunk) + 1
        out = os.path.join(output_dir, f"part{part_num:03d}.pdf")

        writer = PdfWriter()
        for page in reader.pages[start:end]:
            writer.add_page(page)
        with open(out, "wb") as f:
            writer.write(f)

        parts.append(out)
        print(f"  Part {part_num}: pages {start + 1}–{end}")

    print(f"  Split into {len(parts)} parts ({pages_per_chunk} pages each max).")
    return parts

class JimCrowOCR:
    # Keep parts under ~40 MB — llama-cloud rejects larger uploads
    PAGES_PER_CHUNK = 150

    KEYWORDS = [
        "jim crow", "segregation", "separate but equal",
        "colored", "negro", "white only", "colored only",
        "racial discrimination", "miscegenation",
        "poll tax", "literacy test", "grandfather clause", "marriage"
    ]

    def __init__(self, api_key: str):
        self.client = AsyncLlamaCloud(
            api_key=api_key,
            # Large scanned PDFs can take several minutes to parse server-side.
            # connect=30s, read/write/pool=20min each.
            timeout=Timeout(connect=30.0, read=1200.0, write=1200.0, pool=1200.0),
        )

    # ── Diagnostic (uncomment to debug raw API output) 
    # def inspect(self, pdf_path: str):
    #     async def _run():
    #         with open(pdf_path, "rb") as f:
    #             file_obj = await self.client.files.create(file=f, purpose="parse")
    #         result = await self.client.parsing.parse(
    #             file_id=file_obj.id, tier="cost_effective", version="latest", expand=["markdown"]
    #         )
    #         for i, page in enumerate(result.markdown.pages):
    #             print(f"\n--- Page {i+1} (page_number={getattr(page,'page_number','?')}) ---")
    #             print(repr(page.markdown[:300]))
    #     asyncio.run(_run())

    async def _upload_and_parse(self, part_path: str, label: str, offset: int) -> List[Dict]:
        """Upload one PDF part to llama-cloud and return its page chunks."""
        try:
            print(f"  Uploading: {label}")
            with open(part_path, "rb") as f:
                file_obj = await self.client.files.create(file=f, purpose="parse")

            print(f"  Parsing:   {label}")
            # Retry up to 3 times on timeout — server-side parsing can be slow for large parts
            result = None
            for attempt in range(1, 4):
                try:
                    result = await self.client.parsing.parse(
                        file_id=file_obj.id,
                        tier="cost_effective",   # upgrade to "agentic" if OCR quality is poor
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
                        raise

            if not result.markdown or not result.markdown.pages:
                print(f"  WARNING: No pages returned for {label}.")
                return []

            chunks = []
            for i, page in enumerate(result.markdown.pages):
                text = page.markdown or ""
                if _is_junk(text):
                    continue

                # llama-cloud returns page_number directly on each page object
                true_page = None
                if getattr(page, "page_number", None) is not None:
                    try:
                        true_page = int(page.page_number)
                    except (ValueError, TypeError):
                        pass

                idx = offset + i
                chunks.append({
                    "page_number": true_page if true_page is not None else idx + 1,
                    "text":        text,
                })
            return chunks

        except Exception as e:
            import traceback
            print(f"  ERROR on {label}: {e}")
            traceback.print_exc()
            return []

    def parse_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Parse a PDF and return page chunks. Large files are split automatically.
        Sends the ORIGINAL PDF directly — no preprocessing — to minimise
        file size and API credit usage. The llama-cloud OCR handles most
        historical scans well without local preprocessing.
        """
        return asyncio.run(self._parse_async(pdf_path))

    async def _parse_async(self, pdf_path: str) -> List[Dict]:
        print(f"Processing: {pdf_path}")
        size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        split_dir = None

        try:
            page_count = len(PdfReader(pdf_path).pages)
        except Exception:
            page_count = 0

        if size_mb > 40 or page_count > self.PAGES_PER_CHUNK:
            print(f"  {size_mb:.1f} MB / {page_count} pages — splitting...")
            split_dir = tempfile.mkdtemp(prefix="jimcrow_")
            parts = split_pdf(pdf_path, split_dir, self.PAGES_PER_CHUNK)
        else:
            parts = [pdf_path]

        all_chunks: List[Dict] = []
        try:
            for i, part in enumerate(parts):
                label = os.path.basename(part) if len(parts) > 1 else os.path.basename(pdf_path)
                if len(parts) > 1:
                    print(f"\n  Part {i+1}/{len(parts)}")
                all_chunks.extend(await self._upload_and_parse(part, label, i * self.PAGES_PER_CHUNK))
        except Exception as e:
            import traceback
            print(f"ERROR: {e}")
            traceback.print_exc()
        finally:
            if split_dir and os.path.exists(split_dir):
                import shutil
                shutil.rmtree(split_dir)
                if len(parts) > 1:
                    print(f"  Cleaned up {len(parts)} split parts.")

        return all_chunks

    def find_references(self, chunks: List[Dict], metadata: Dict, filename: str) -> Dict:
        """
        Search chunks for Jim Crow keywords and build the standard output document.
        """
        # Merge chunks into pages
        pages_map: Dict[int, Dict] = {}
        for chunk in chunks:
            p = chunk["page_number"]
            if p not in pages_map:
                pages_map[p] = {
                    "page_number":  p,
                    "text":         chunk["text"],
                    "keyword_hits": [],
                }
            else:
                pages_map[p]["text"] += "\n" + chunk["text"]

        keyword_refs = []
        pages_with_hits: set = set()

        for p in sorted(pages_map):
            page = pages_map[p]
            lines = page["text"].split("\n")
            hits: List[str] = []

            for i, line in enumerate(lines):
                ll = line.lower()
                for kw in self.KEYWORDS:
                    if kw in ll:
                        keyword_refs.append({
                            "keyword":             kw,
                            "page_number":         p,
                            "line_number_in_page": i + 1,
                            "context":             "\n".join(lines[max(0, i-2):min(len(lines), i+3)]),
                        })
                        if kw not in hits:
                            hits.append(kw)
                        break  # one match per line

            if hits:
                page["keyword_hits"] = hits
                pages_with_hits.add(p)

        # Only include pages that had keyword hits — no need to store every page
        pages = [pages_map[p] for p in sorted(pages_with_hits)]

        pub = metadata.get("publication_date") or ""
        ym = re.search(r"\b(1[89]\d{2})\b", pub)
        year = int(ym.group(1)) if ym else None

        return {
            "source": {
                "filename":      filename,
                "title":         metadata.get("title"),
                "author":        metadata.get("author"),
                "year":          year,
                "document_type": None,  # Fill in manually or via future classifier
            },
            "pages": pages,
            "keyword_references": keyword_refs,
            "statistics": {
                "total_pages":             metadata.get("page_count"),
                "pages_with_keyword_hits": len(pages_with_hits),
                "total_keyword_hits":      len(keyword_refs),
            },
            "ocr_metadata": {
                "engine":         "llama_cloud",
                "result_type":    "markdown",
                "processed_at":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format_version": "2.0",
            },
        }

    def save(self, results: Dict, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {output_path}") 

def main():
    api_key = os.getenv("LLAMA_API_KEY")
    if not api_key:
        print("LLAMA_API_KEY not found in environment.")
        return

    ocr = JimCrowOCR(api_key=api_key)

    print("Please select a PDF file")
    pdf_path = select_pdf()
    if not pdf_path or not os.path.exists(pdf_path):
        print("No file selected. Exiting.")
        return

    filename = os.path.basename(pdf_path)

    # Metadata from embedded PDF headers (free)
    print("Extracting document metadata...")
    metadata = extract_pdf_metadata(pdf_path)

    # OCR via llama-cloud (sends original PDF to save credits)
    chunks = ocr.parse_pdf(pdf_path)

    # Override distributor metadata with real title-page values
    if metadata.get("metadata_warning") or not all(
        metadata.get(k) for k in ("title", "author", "publication_date")
    ):
        print("Extracting metadata from title page...")
        tp = extract_title_page_metadata(chunks)
        for field in ("title", "author", "publication_date"):
            if tp.get(field):
                metadata[field] = tp[field]
                metadata["metadata_source"] = "title_page"
        print(f"  Title:  {tp.get('title') or '(not found)'}")
        print(f"  Author: {tp.get('author') or '(not found)'}")
        print(f"  Date:   {tp.get('publication_date') or '(not found)'}")

    missing = [k for k in ("title", "author", "publication_date") if not metadata.get(k)]
    if missing:
        print(f"Note: Could not resolve {missing} — fill in manually in the JSON.")



    # Keyword search and output assembly
    results = ocr.find_references(chunks, metadata, filename)
    out = f"{os.path.splitext(filename)[0]}_results.json"
    ocr.save(results, out)

    s = results["statistics"]
    print("\nExtraction complete!")
    print(f"  Title:              {results['source'].get('title') or '(not found)'}")
    print(f"  Author:             {results['source'].get('author') or '(not found)'}")
    print(f"  Year:               {results['source'].get('year') or '(not found)'}")
    print(f"  Pages with hits:    {s['pages_with_keyword_hits']}")
    print(f"  Total keyword hits: {s['total_keyword_hits']}")


if __name__ == "__main__":
    main()