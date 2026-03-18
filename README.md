# CS499_JimCrowLaws

Searchable public digital archive of Kentucky Jim Crow laws (1865–1966).

**Pipeline:** Scanned PDFs → OCR → Document Processing (LLM) → Database → Website

---

## Setup

All API keys live in a single `.env` file in the project root. Copy the template and fill in your keys:

```bash
cp .env_template .env
# then edit .env with your keys
```

---

## OCR Component (`ocr/`)

Install dependencies:
```bash
pip install "llama-cloud>=1.0" pypdf python-dotenv
```

Run (opens a file picker to select a PDF):
```bash
python3 ocr/jim_crow_ocr.py
```

Output: `ocr_results/{filename}_results.json`

### Expected output format (v2)

The document processing component expects OCR output in this format.

```json
{
  "source": {
    "filename": "Gen_assemb_v1-1865.pdf",
    "title": "Acts Passed at the Session of the General Assembly of Kentucky",
    "author": "Kentucky General Assembly",
    "year": 1865,
    "document_type": null
  },
  "pages": [
    {
      "page_number": 87,
      "text": "# CHAPTER 399\n\nAN ACT to establish separate schools...",
      "keyword_hits": ["colored", "negro"]
    }
  ],
  "keyword_references": [
    {
      "keyword": "colored",
      "page_number": 87,
      "line_number_in_page": 3,
      "context": "...surrounding lines..."
    }
  ],
  "statistics": {
    "total_pages": 450,
    "pages_with_keyword_hits": 27,
    "total_keyword_hits": 34
  },
  "ocr_metadata": {
    "engine": "llama_cloud",
    "result_type": "markdown",
    "processed_at": "2026-02-19T10:00:00Z",
    "format_version": "2.0"
  }
}
```

See `doc_processing/sample_input/toy_ocr_output.json` for a full working example.

---

## Document Processing Component (`doc_processing/`)

Takes OCR output and classifies each statute section as a Jim Crow law, extracting structured metadata for the database.

### Install dependencies

Install the core packages plus the package for your chosen LLM provider:

```bash
pip3 install llama-index python-dotenv

# Pick one:
pip3 install llama-index-llms-anthropic   # Anthropic Claude (default)
pip3 install llama-index-llms-openai      # OpenAI GPT
pip3 install llama-index-llms-ollama      # Ollama (local/free)
pip3 install llama-index-llms-openai-like # Groq, Together AI, LM Studio, etc.
```

### Configure

In `.env`, set `LLM_PROVIDER` and the matching API key. See `.env_template` for all options.

### Run

```bash
# Against the built-in toy example (no OCR file needed):
python3 doc_processing/processor.py

# Against a real OCR output file:
python3 doc_processing/processor.py ocr_results/my_file_results.json
```

Output: `doc_processing_results/{filename}_classified.json`

### Output format

```json
{
  "source_document": { "filename": "...", "year": 1865 },
  "entries": [
    {
      "entry_id": "gen_assemb_1865_p87_s1",
      "page_number": 87,
      "citation": "Acts of KY General Assembly, 1865, p. 87",
      "ocr_text": "...",
      "classification": {
        "is_jim_crow": "yes",
        "confidence": 0.95,
        "category": "education",
        "summary": "Mandates separate schools for white and colored children.",
        "racial_indicator": "explicit",
        "needs_human_review": false
      }
    }
  ],
  "human_review_queue": [ ... ],
  "statistics": { "total_sections": 24, "classified_jim_crow": 3, ... }
}
```

Entries flagged `needs_human_review: true` (ambiguous cases or confidence < 0.7) are also listed separately in `human_review_queue`.

---

## Reviewer UI (`reviewer/`)

A Gradio web app for human reviewers to review, correct, and sign off on LLM classifications before the data goes into the archive database.

### Install

```bash
pip install gradio
```

### Run

```bash
python reviewer/reviewer_ui.py
```

Opens at `http://localhost:7860` in your browser.

### What it does

- Loads any classified JSON file from `doc_processing_results/`
- Shows entries in priority order: flagged (`needs_human_review`) first, then `is_jim_crow=yes`, then the rest
- Lets you correct `is_jim_crow` (yes / no / ambiguous) and `category`, leave a free-text note, and save
- Saves corrections back to the same JSON file immediately on each "Save Review" click
- Tracks progress with a live counter: overall entries reviewed and priority entries remaining

### What "reviewed" means for a file

A file is considered **complete** when all **priority entries** have been saved — that is, every entry where `is_jim_crow = "yes"` or `needs_human_review = true`. The UI shows a green "✅ All priority entries reviewed" banner when this threshold is reached.
