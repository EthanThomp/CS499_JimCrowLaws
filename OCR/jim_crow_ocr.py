import os
import re
import warnings
import logging
import tempfile

# Warning suppression 
# Must come before ALL other imports so warnings fired at import time are caught
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*Odd-length string.*")
warnings.filterwarnings("ignore", message=".*Skipping broken line.*")
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)
logging.getLogger("pypdf.generic").setLevel(logging.ERROR)

from pathlib import Path
from dotenv import load_dotenv
from pypdf import PdfReader
from typing import List, Dict, Optional
import json
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from llama_parse import LlamaParse

load_dotenv(Path(__file__).parent.parent / ".env")


def select_pdf():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")]
    )
    return file_path


def extract_pdf_metadata(pdf_path: str) -> Dict:
    """
    Extract embedded metadata from a PDF file using pypdf.
    Falls back to None for missing fields.
    """
    metadata = {
        "title": None,
        "author": None,
        "publication_date": None,
        "subject": None,
        "keywords": None,
        "creator": None,    # Software used to author the PDF
        "producer": None,   # Software used to convert/export the PDF
        "page_count": None,
        "metadata_source": "embedded"
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
        print(f"Warning: Could not extract embedded metadata: {str(e)}")

    # Distributors like HathiTrust overwrite embedded metadata with their own info.
    # Flag this so the researcher knows the fields may not reflect the actual document.
    known_distributors = ["hathitrust", "internet archive", "google", "proquest"]
    producer = (metadata.get("producer") or "").lower()
    creator  = (metadata.get("creator") or "").lower()
    if any(d in producer or d in creator for d in known_distributors):
        metadata["metadata_warning"] = (
            "Embedded metadata appears to be from a distributor, not the original publisher. "
            "Title, author, and date may reflect the digitization source rather than the document. "
            "Consider extracting these fields from the document's title page instead."
        )

    return metadata


def _parse_pdf_date(raw_date: str) -> Optional[str]:
    """
    Convert a PDF date string like "D:20050915120000-07'00'"
    to a readable ISO format like "2005-09-15".
    Returns the raw string if parsing fails.
    """
    try:
        if raw_date.startswith("D:"):
            raw_date = raw_date[2:]
        parsed = datetime.strptime(raw_date[:8], "%Y%m%d")
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return raw_date


def _extract_page_number(doc_metadata: dict, chunk_index: int) -> Optional[int]:
    """
    Pull the true page number out of a LlamaParse chunk's metadata dict.

    LlamaParse uses 'page_label' for the human-readable page label (can be
    Roman numerals, "i", "ii", etc.) and 'page' for the 0-based page index.
    We prefer 'page' (converting to 1-based) but fall back through several
    known field names in case the schema changes between LlamaParse versions.

    If nothing is found we return None — the caller will fall back to the
    chunk index so the data is never silently wrong.
    """
    # 0-based integer page index — most reliable
    if "page" in doc_metadata:
        try:
            return int(doc_metadata["page"]) + 1
        except (ValueError, TypeError):
            pass

    # Human-readable label — works for standard Arabic-numeral docs
    if "page_label" in doc_metadata:
        try:
            return int(doc_metadata["page_label"])
        except (ValueError, TypeError):
            # Non-numeric label (e.g. "iv") — return as-is later if needed
            pass

    # Older LlamaParse versions used 'page_number' directly
    if "page_number" in doc_metadata:
        try:
            return int(doc_metadata["page_number"])
        except (ValueError, TypeError):
            pass

    return None  # Caller will use chunk_index as fallback

# Known junk patterns from HathiTrust and similar distributors
JUNK_PATTERNS = ["nogle", "google"]

def _is_junk_chunk(text: str) -> bool:
    """
    Returns True for distributor wrapper pages that contain no real content.
    HathiTrust inserts pages with just 'nogle' (a Google/HathiTrust watermark artifact).
    """
    stripped = text.strip().lower()
    # Empty or nearly empty
    if len(stripped) < 20:
        return True
    # Only contains known junk tokens
    if all(token in JUNK_PATTERNS for token in stripped.split()):
        return True
    return False


def extract_title_page_metadata(chunks: List[Dict]) -> Dict:
    """
    Extract real document metadata (title, author, date) from the title page chunk.
    This is necessary for HathiTrust and other digitized documents where the embedded
    PDF metadata reflects the distributor, not the original publisher.

    Looks at the first few non-junk chunks and uses simple heuristics:
      - Title: first H1 markdown heading (# ...)
      - Author/compiler: line after keywords like 'by', 'compiled by'
      - Year: first 4-digit year within the Jim Crow era (1865-1965)
    """
    import re

    title = None
    author = None
    year = None

    # Only look at the first few chunks — title page info won't be deep in the doc
    candidates = [c for c in chunks[:5] if not _is_junk_chunk(c["text"])]

    for chunk in candidates:
        lines = [l.strip() for l in chunk["text"].split("\n") if l.strip()]

        for i, line in enumerate(lines):
            # Title: first markdown H1 heading
            if title is None and line.startswith("# "):
                title = line.lstrip("# ").strip()

            # Author: line after "by" or "compiled by"
            if author is None:
                line_lower = line.lower()
                if line_lower in ("by", "compiled by", "edited by", "prepared by"):
                    if i + 1 < len(lines):
                        author = lines[i + 1].strip()
                elif line_lower.startswith(("by ", "compiled by ", "edited by ")):
                    author = re.sub(r"^(compiled by|edited by|prepared by|by)\s+", "", line, flags=re.IGNORECASE).strip()

            # Year: first 4-digit year within the Jim Crow era (1865-1965)
            if year is None:
                match = re.search(r"\b(18[6-9][0-9]|19[0-5][0-9]|1960|1961|1962|1963|1964|1965)\b", line)
                if match:
                    year = match.group(1)

        if title and author and year:
            break

    return {
        "title": title,
        "author": author,
        "publication_date": year,
        "metadata_source": "title_page"
    }




def build_page_index(pdf_path: str) -> Dict[int, str]:
    """
    Use pypdf to extract raw text from every physical page in the PDF.
    Returns a dict of {1-based page number: normalized text}.
    This is used to match LlamaParse chunks back to real page numbers
    when LlamaParse doesn't return page metadata (common with scanned docs).
    """
    import re
    page_index = {}
    try:
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            # Normalize: lowercase, collapse whitespace, strip punctuation
            # so minor OCR differences don't break matching
            normalized = re.sub(r"[^a-z0-9 ]", " ", text.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()
            page_index[i] = normalized
    except Exception as e:
        print(f"Warning: Could not build page index from pypdf: {e}")
    return page_index


def match_chunk_to_page(chunk_text: str, page_index: Dict[int, str]) -> Optional[int]:
    """
    Find which physical page a chunk most likely belongs to by comparing
    a sample of words from the chunk against each page's extracted text.

    Strategy: take the first 30 meaningful words from the chunk, then find
    the page that contains the most of them. This is fuzzy enough to survive
    OCR differences between LlamaParse and pypdf.
    """
    import re

    # Normalize chunk text the same way as page_index
    normalized_chunk = re.sub(r"[^a-z0-9 ]", " ", chunk_text.lower())
    normalized_chunk = re.sub(r"\s+", " ", normalized_chunk).strip()

    # Take a sample of words — skip very common words that appear everywhere
    stopwords = {"the", "a", "an", "and", "of", "to", "in", "is", "that", "it",
                 "for", "on", "with", "as", "be", "at", "or", "from", "this", "by"}
    words = [w for w in normalized_chunk.split() if w not in stopwords and len(w) > 3]
    sample = words[:30]

    if not sample:
        return None

    best_page = None
    best_score = 0

    for page_num, page_text in page_index.items():
        score = sum(1 for w in sample if w in page_text)
        if score > best_score:
            best_score = score
            best_page = page_num

    # Only trust the match if enough words aligned (at least 40% of sample)
    min_score = max(3, len(sample) * 0.4)
    return best_page if best_score >= min_score else None


def split_pdf(pdf_path: str, output_dir: str, pages_per_chunk: int = 200) -> List[str]:
    """
    Split a large PDF into smaller chunks so each piece stays under LlamaParse's
    Returns a list of chunk file paths.

    Uses pymupdf (fitz) — no external dependencies needed.
    Chunks are written to output_dir and named <stem>_part001.pdf, etc.
    """
    try:
        import fitz
    except ImportError:
        print("Warning: pymupdf not installed. Cannot split PDF.")
        print("  Run: pip install pymupdf")
        return [pdf_path]  # Fall back to trying the whole file

    doc = fitz.open(pdf_path)
    total = len(doc)
    # Use a short fixed name to avoid Windows MAX_PATH issues with long document titles
    chunk_paths = []

    for start in range(0, total, pages_per_chunk):
        end = min(start + pages_per_chunk, total)
        part_num = (start // pages_per_chunk) + 1
        out_path = os.path.join(output_dir, f"part{part_num:03d}.pdf")

        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        chunk_doc.save(out_path)
        chunk_doc.close()
        chunk_paths.append(out_path)
        print(f"  Split part {part_num}: pages {start + 1}–{end} → {os.path.basename(out_path)}")

    doc.close()
    print(f"  Split {total} pages into {len(chunk_paths)} chunks of up to {pages_per_chunk} pages each.")
    return chunk_paths


def preprocess_pdf(pdf_path: str, output_path: str, dpi: int = 300) -> bool:
    """
    Preprocess a scanned PDF to improve OCR quality by:
      - Rendering each page to a high-res image via pymupdf (no poppler needed)
      - Sharpening (helps with blurry/out-of-focus scans)
      - Enhancing contrast (helps with faded text)
      - Converting to clean black & white (removes background noise)
      - Repacking into a new PDF via Pillow

    Returns True if successful, False if preprocessing failed (so caller
    can fall back to the original PDF).

    Requires: pip install pymupdf Pillow
    No external binaries needed — pymupdf is pure Python.
    """
    try:
        import fitz  # pymupdf
        from PIL import Image, ImageFilter, ImageEnhance, ImageOps
        import io
    except ImportError:
        print("Warning: pymupdf or Pillow not installed. Skipping preprocessing.")
        print("  Run: pip install pymupdf Pillow")
        return False

    try:
        print(f"Preprocessing PDF (dpi={dpi})...")
        doc = fitz.open(pdf_path)
        total = len(doc)
        print(f"  Rendering {total} pages...")

        # fitz uses a zoom matrix — 72 DPI is the base, so zoom = dpi/72
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        processed_pages = []
        for i, page in enumerate(doc):
            # Render page to a pixmap (raw image)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Convert pixmap bytes to a Pillow image
            img = Image.open(io.BytesIO(pix.tobytes("png")))

            # Convert to greyscale — colour is noise for text documents
            img = img.convert("L")

            # Sharpen — reduces blur from out-of-focus scans (applied twice for strength)
            img = img.filter(ImageFilter.SHARPEN)
            img = img.filter(ImageFilter.SHARPEN)

            # Contrast enhancement — brings up faded text
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)  # tune down to 1.5 if over-sharpened

            # Auto-level — normalizes uneven page lighting (common in bound books)
            img = ImageOps.autocontrast(img, cutoff=2)

            # Binarize to pure black & white — removes grey background noise
            threshold = 180  # lower toward 150 if text gets clipped
            img = img.point(lambda x: 0 if x < threshold else 255, "1")

            # Convert back to RGB for PDF saving
            img = img.convert("RGB")
            processed_pages.append(img)

            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{total} pages...")

        doc.close()

        # Save all processed pages as a single PDF
        if processed_pages:
            processed_pages[0].save(
                output_path,
                save_all=True,
                append_images=processed_pages[1:],
                resolution=dpi
            )
            print(f"  Preprocessed PDF saved to: {output_path}")
            return True

    except Exception as e:
        import traceback
        print(f"Warning: PDF preprocessing failed: {e}")
        traceback.print_exc()

    return False

class JimCrowOCR:
    def __init__(self, api_key: str):
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            verbose=True,
            language="en"
        )

    # def inspect_chunks(self, pdf_path: str):
    #     """
    #     Diagnostic helper — prints raw chunk metadata so you can verify
    #     what LlamaParse is returning for your specific documents.
    #     Uncomment to debug field names returned by LlamaParse.
    #     """
    #     print(f"\n=== Chunk inspection for: {pdf_path} ===")
    #     documents = self.parser.load_data(pdf_path)
    #     for i, doc in enumerate(documents):
    #         print(f"\n--- Chunk {i} ---")
    #         print(f"  metadata keys : {list(doc.metadata.keys())}")
    #         print(f"  metadata      : {doc.metadata}")
    #         print(f"  text preview  : {doc.text[:150]!r}")
    #     print("=== End inspection ===\n")

    # LlamaParse rejects uploads over ~50MB. Preprocessed scans at 300 DPI can easily
    # exceed this for large documents. We split at 150 pages per chunk to stay safe.
    PAGES_PER_CHUNK = 150

    def parse_pdf(self, pdf_path: str, page_index: Dict[int, str] = None) -> List[Dict]:
        """
        Parse a PDF and return a list of chunk dicts. Automatically splits large
        PDFs into smaller pieces to stay under LlamaParse's upload size limit.

        Each chunk includes:
          - chunk_index        : global position across all split parts
          - page_number        : matched via pypdf or LlamaParse metadata
          - page_number_source : 'llama_parse' | 'pypdf_match' | 'fallback_chunk_index'
          - text               : the chunk's OCR'd text
        """
        print(f"Processing: {pdf_path}")

        # Check file size — split if large to avoid 413 errors from LlamaParse
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        split_dir = None

        try:
            import fitz
            page_count = len(fitz.open(pdf_path))
        except Exception:
            page_count = 0

        if file_size_mb > 40 or page_count > self.PAGES_PER_CHUNK:
            print(f"  File is {file_size_mb:.1f} MB / {page_count} pages — splitting into chunks...")
            split_dir = tempfile.mkdtemp(prefix="jimcrow_split_")
            pdf_parts = split_pdf(pdf_path, split_dir, pages_per_chunk=self.PAGES_PER_CHUNK)
        else:
            pdf_parts = [pdf_path]

        all_chunks = []
        global_chunk_index = 0

        try:
            for part_path in pdf_parts:
                part_label = os.path.basename(part_path) if len(pdf_parts) > 1 else os.path.basename(pdf_path)
                if len(pdf_parts) > 1:
                    print(f"  Parsing part: {part_label}")

                try:
                    documents = self.parser.load_data(part_path)
                except Exception as e:
                    print(f"  ERROR parsing {part_label}: {e}")
                    continue

                if not documents:
                    print(f"  WARNING: LlamaParse returned 0 documents for {part_label}.")
                    print("  Possible causes: invalid API key, encrypted PDF, or network error.")
                    continue

                for doc in documents:
                    if _is_junk_chunk(doc.text):
                        global_chunk_index += 1
                        continue

                    true_page = _extract_page_number(doc.metadata, global_chunk_index)
                    page_source = "llama_parse"

                    if true_page is None and page_index:
                        true_page = match_chunk_to_page(doc.text, page_index)
                        page_source = "pypdf_match" if true_page is not None else "fallback_chunk_index"
                    elif true_page is None:
                        page_source = "fallback_chunk_index"

                    all_chunks.append({
                        "chunk_index":        global_chunk_index,
                        "page_number":        true_page if true_page is not None else global_chunk_index + 1,
                        "page_number_source": page_source,
                        "text":               doc.text,
                    })
                    global_chunk_index += 1

            return all_chunks

        except Exception as e:
            import traceback
            print(f"ERROR parsing {pdf_path}: {str(e)}")
            traceback.print_exc()
            return []

        finally:
            # Clean up split temp files
            if split_dir and os.path.exists(split_dir):
                import shutil
                shutil.rmtree(split_dir)
                if len(pdf_parts) > 1:
                    print(f"  Cleaned up {len(pdf_parts)} split parts.")

    def parse_multiple_pdfs(self, pdf_paths: List[str]) -> Dict[str, List[Dict]]:
        """Batch parse multiple PDFs, returning per-chunk data for each."""
        return {
            os.path.basename(pdf_path): self.parse_pdf(pdf_path)
            for pdf_path in pdf_paths
        }

    KEYWORDS = [
        "jim crow",
        "segregation",
        "separate but equal",
        "colored",
        "negro",
        "white only",
        "colored only",
        "racial discrimination",
        "miscegenation",
        "poll tax",
        "literacy test",
        "grandfather clause"
    ]

    def find_jim_crow_references(
        self,
        chunks: List[Dict],
        metadata: Dict,
        source_filename: str
    ) -> Dict:
        """
        Search chunks for Jim Crow keywords and assemble the full output document
        in the standard format expected by the document processing component.

        Returns a dict with keys: source, pages, keyword_references, statistics,
        ocr_metadata.
        """
        # Group chunks by page number so we can build the pages array
        pages_map: Dict[int, Dict] = {}
        for chunk in chunks:
            pnum = chunk["page_number"]
            if pnum not in pages_map:
                pages_map[pnum] = {
                    "page_number":        pnum,
                    "page_number_source": chunk["page_number_source"],
                    "text":               chunk["text"],
                    "keyword_hits":       [],
                }
            else:
                # Append text from multiple chunks on the same page
                pages_map[pnum]["text"] += "\n" + chunk["text"]

        # Scan every page for keyword matches
        keyword_references = []
        pages_with_hits = set()

        for pnum in sorted(pages_map.keys()):
            page = pages_map[pnum]
            lines = page["text"].split("\n")
            hits_on_page = []

            for i, line in enumerate(lines):
                line_lower = line.lower()
                for keyword in self.KEYWORDS:
                    if keyword in line_lower:
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context = "\n".join(lines[start:end])

                        keyword_references.append({
                            "keyword":          keyword,
                            "page_number":      pnum,
                            "line_number_in_page": i + 1,
                            "context":          context,
                        })

                        if keyword not in hits_on_page:
                            hits_on_page.append(keyword)
                        break  # one match per line

            if hits_on_page:
                page["keyword_hits"] = hits_on_page
                pages_with_hits.add(pnum)

        # Build pages array (only pages that have text)
        pages = [pages_map[p] for p in sorted(pages_map.keys())]

        # Extract year from publication_date
        pub_date = metadata.get("publication_date") or ""
        year = None
        year_match = re.search(r"\b(1[89]\d{2})\b", pub_date)
        if year_match:
            year = int(year_match.group(1))

        return {
            "source": {
                "filename":      source_filename,
                "title":         metadata.get("title"),
                "author":        metadata.get("author"),
                "year":          year,
                "document_type": None,   # Fill in manually or via future classifier
            },
            "pages": pages,
            "keyword_references": keyword_references,
            "statistics": {
                "total_pages":           metadata.get("page_count"),
                "parsed_chunks":         len(chunks),
                "pages_with_keyword_hits": len(pages_with_hits),
                "total_keyword_hits":    len(keyword_references),
            },
            "ocr_metadata": {
                "engine":         "llama_parse",
                "result_type":    "markdown",
                "processed_at":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format_version": "2.0",
            },
        }

    def save_results(self, results: Dict, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {output_path}")


def main():
    API_KEY = os.getenv("LLAMA_API_KEY")

    if not API_KEY:
        print("LLAMA_API_KEY not found in environment variables.")
        return

    ocr = JimCrowOCR(api_key=API_KEY)

    print("Please select a PDF file")
    pdf_path = select_pdf()

    if not pdf_path:
        print("No file selected. Exiting.")
        return

    if not os.path.exists(pdf_path):
        print(f"PDF file not found: {pdf_path}")
        return

    filename = os.path.basename(pdf_path)

    # Extract embedded PDF metadata (no API cost)
    print("Extracting document metadata...")
    metadata = extract_pdf_metadata(pdf_path)

    # Diagnostic: uncomment to inspect raw LlamaParse chunk metadata
    # ocr.inspect_chunks(pdf_path)

    # Preprocess the PDF to improve OCR quality
    # Creates a sharpened, contrast-enhanced version for LlamaParse
    # Falls back to original if preprocessing fails or dependencies missing
    preprocessed_path = Path(pdf_path).with_stem(Path(pdf_path).stem + "_preprocessed").with_suffix(".pdf")
    preprocessing_succeeded = preprocess_pdf(pdf_path, str(preprocessed_path))
    parse_path = str(preprocessed_path) if preprocessing_succeeded else pdf_path

    if not preprocessing_succeeded:
        print("Falling back to original PDF for parsing.")

    # Build page index from the ORIGINAL pdf for accurate page number matching
    print("Building page index for page number matching...")
    page_index = build_page_index(pdf_path)
    print(f"  Indexed {len(page_index)} physical pages from pypdf.")

    # Parse the preprocessed (or original) PDF into chunks
    chunks = ocr.parse_pdf(parse_path, page_index=page_index)

    # Clean up preprocessed file after parsing to save disk space
    if preprocessing_succeeded and preprocessed_path.exists():
        preprocessed_path.unlink()
        print("  Cleaned up preprocessed PDF.")

    # If embedded metadata looks like it came from a distributor (HathiTrust etc.),
    # extract the real title/author/date from the document's own title page instead.
    if metadata.get("metadata_warning") or not all(metadata.get(k) for k in ("title", "author", "publication_date")):
        print("Embedded metadata missing or from distributor — extracting from title page...")
        title_page_meta = extract_title_page_metadata(chunks)

        # Merge: title page values take priority for the three core fields,
        # but keep embedded values as fallback if title page extraction fails.
        for field in ("title", "author", "publication_date"):
            if title_page_meta.get(field):
                metadata[field] = title_page_meta[field]
                metadata["metadata_source"] = "title_page"

        print(f"  Title page title:  {title_page_meta.get('title') or '(not found)'}")
        print(f"  Title page author: {title_page_meta.get('author') or '(not found)'}")
        print(f"  Title page date:   {title_page_meta.get('publication_date') or '(not found)'}")

    missing = [k for k in ("title", "author", "publication_date") if not metadata.get(k)]
    if missing:
        print(f"Note: Could not resolve [{', '.join(missing)}] — fill in manually in the output JSON.")

    # Warn if any chunks fell back to chunk index for page number
    fallback_count = sum(1 for c in chunks if c["page_number_source"] == "fallback_chunk_index")
    if fallback_count:
        print(f"Warning: {fallback_count}/{len(chunks)} chunks could not determine true page number — "
              f"chunk index used as fallback (pypdf text too different from LlamaParse OCR to match).")

    # Find keyword references and assemble the output document
    results = ocr.find_jim_crow_references(chunks, metadata, filename)

    output_filename = f"{os.path.splitext(filename)[0]}_results.json"
    ocr.save_results(results, output_filename)

    stats = results["statistics"]
    print("\nExtraction complete!")
    print(f"  Title:            {results['source'].get('title') or '(not found)'}")
    print(f"  Author:           {results['source'].get('author') or '(not found)'}")
    print(f"  Year:             {results['source'].get('year') or '(not found)'}")
    print(f"  Chunks parsed:    {stats['parsed_chunks']}")
    print(f"  Pages with hits:  {stats['pages_with_keyword_hits']}")
    print(f"  Total keyword hits: {stats['total_keyword_hits']}")


if __name__ == "__main__":
    main()