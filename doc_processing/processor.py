"""
processor.py — Document Processing Pipeline

Usage:
    python3 doc_processing/processor.py [path/to/ocr_output.json]

If no path is given, defaults to doc_processing/sample_input/toy_ocr_output.json.

Output: doc_processing_results/{input_stem}_classified.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.core.program import LLMTextCompletionProgram
from llama_index.core.schema import Document, TextNode

from models import StatuteClassification, StatuteEntry
from prompts import CLASSIFICATION_PROMPT
from reader import OCRJsonReader

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env")

# Supported providers: anthropic | openai | ollama | openai_like
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "")


def build_llm():
    """
    Build a LlamaIndex LLM from environment variables.

    Set in DocProcessing/.env:
        LLM_PROVIDER  = anthropic | openai | ollama | openai_like
        LLM_MODEL     = model name (provider-specific, see .env for examples)

    Provider-specific keys:
        anthropic   → ANTHROPIC_API_KEY
        openai      → OPENAI_API_KEY
        ollama      → OLLAMA_BASE_URL  (default: http://localhost:11434)
        openai_like → OPENAI_LIKE_API_KEY, OPENAI_LIKE_BASE_URL
                      (works with Groq, Together, LM Studio, etc.)
    """
    if LLM_PROVIDER == "anthropic":
        from llama_index.llms.anthropic import Anthropic  # pip install llama-index-llms-anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set in DocProcessing/.env")
        model = LLM_MODEL or "claude-haiku-4-5-20251001"
        return Anthropic(model=model, api_key=api_key, max_tokens=1024)

    elif LLM_PROVIDER == "openai":
        from llama_index.llms.openai import OpenAI  # pip install llama-index-llms-openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set in DocProcessing/.env")
        model = LLM_MODEL or "gpt-4o-mini"
        return OpenAI(model=model, api_key=api_key, max_tokens=1024)

    elif LLM_PROVIDER == "ollama":
        from llama_index.llms.ollama import Ollama  # pip install llama-index-llms-ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = LLM_MODEL or "llama3"
        return Ollama(model=model, base_url=base_url, request_timeout=120.0)

    elif LLM_PROVIDER == "openai_like":
        # Works with Groq, Together AI, LM Studio, vLLM, etc.
        from llama_index.llms.openai_like import OpenAILike  # pip install llama-index-llms-openai-like
        api_key = os.getenv("OPENAI_LIKE_API_KEY")
        base_url = os.getenv("OPENAI_LIKE_BASE_URL")
        if not api_key or not base_url:
            raise EnvironmentError(
                "OPENAI_LIKE_API_KEY and OPENAI_LIKE_BASE_URL must be set in DocProcessing/.env"
            )
        model = LLM_MODEL
        if not model:
            raise EnvironmentError("LLM_MODEL must be set when using openai_like provider")
        return OpenAILike(
            model=model,
            api_key=api_key,
            api_base=base_url,
            max_tokens=1024,
            is_chat_model=True,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. "
            "Choose from: anthropic, openai, ollama, openai_like"
        )


# ---------------------------------------------------------------------------
# Step 1: Parse OCR JSON → Documents
# ---------------------------------------------------------------------------

def load_documents(ocr_path: Path) -> tuple[list[Document], dict]:
    reader = OCRJsonReader()
    docs = reader.load_data(ocr_path)
    with open(ocr_path) as f:
        raw = json.load(f)
    return docs, raw["source"]


# ---------------------------------------------------------------------------
# Step 2: Convert pages → TextNodes (one node per page)
# ---------------------------------------------------------------------------

def segment_documents(docs: List[Document]) -> List[TextNode]:
    """
    Convert each page Document into a single TextNode.
    Pages with no text content are skipped.
    """
    nodes = []
    for doc in docs:
        text = doc.text.strip()
        if not text:
            continue
        node = TextNode(
            text=text,
            metadata=dict(doc.metadata),
        )
        nodes.append(node)
    return nodes


# ---------------------------------------------------------------------------
# Step 3: Classify each section with LLM
# ---------------------------------------------------------------------------

def build_program() -> LLMTextCompletionProgram:
    llm = build_llm()
    Settings.llm = llm
    print(f"  Using LLM: {LLM_PROVIDER} / {llm.metadata.model_name}")

    program = LLMTextCompletionProgram.from_defaults(
        output_cls=StatuteClassification,
        prompt_template_str=CLASSIFICATION_PROMPT,
        llm=llm,
        verbose=False,
    )
    return program


def make_entry_id(filename: str, page_number: int) -> str:
    stem = Path(filename).stem.lower().replace(" ", "_")[:30]
    return f"{stem}_p{page_number}"


def make_citation(source: dict, page_number: int) -> str:
    title = source.get("title", source.get("filename", "Unknown"))
    year = source.get("year", "")
    return f"{title}, {year}, p. {page_number}"


def classify_node(
    node: TextNode,
    program: LLMTextCompletionProgram,
    source: dict,
) -> StatuteEntry:
    meta = node.metadata
    filename = meta.get("source_filename", "")
    page_number = meta.get("page_number", 0)
    year = meta.get("year")

    classification: StatuteClassification = program(
        source_filename=filename,
        page_number=page_number,
        year=year if year else "unknown",
        statute_text=node.text,
        schema=StatuteClassification.model_json_schema(),
    )

    return StatuteEntry(
        entry_id=make_entry_id(filename, page_number),
        source_filename=filename,
        page_number=page_number,
        year=year,
        ocr_text=node.text,
        citation=make_citation(source, page_number),
        classification=classification,
    )


# ---------------------------------------------------------------------------
# Step 4: Aggregate results and write output
# ---------------------------------------------------------------------------

def aggregate_results(entries: List[StatuteEntry], source: dict) -> dict:
    jim_crow = sum(1 for e in entries if e.classification.is_jim_crow == "yes")
    ambiguous = sum(1 for e in entries if e.classification.is_jim_crow == "ambiguous")
    needs_review = sum(1 for e in entries if e.classification.needs_human_review)
    not_jim_crow = sum(1 for e in entries if e.classification.is_jim_crow == "no")

    human_review_queue = [
        {
            "entry_id": e.entry_id,
            "reason": (
                "low confidence" if e.classification.confidence < 0.7
                else "ambiguous racial indicator"
                if e.classification.racial_indicator == "implicit"
                else "flagged by classifier"
            ),
        }
        for e in entries
        if e.classification.needs_human_review
    ]

    return {
        "source_document": source,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "entries": [e.model_dump() for e in entries],
        "human_review_queue": human_review_queue,
        "statistics": {
            "total_sections": len(entries),
            "classified_jim_crow": jim_crow,
            "ambiguous": ambiguous,
            "needs_human_review": needs_review,
            "not_jim_crow": not_jim_crow,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        ocr_path = Path(sys.argv[1])
    else:
        ocr_path = Path(__file__).parent / "sample_input" / "toy_ocr_output.json"

    if not ocr_path.exists():
        print(f"Error: {ocr_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Loading OCR output: {ocr_path}")
    docs, source = load_documents(ocr_path)
    print(f"  Loaded {len(docs)} pages")

    print("Converting pages to text nodes...")
    nodes = segment_documents(docs)
    print(f"  Produced {len(nodes)} page nodes")

    print("Building LLM classification program...")
    program = build_program()

    entries = []
    for i, node in enumerate(nodes):
        page = node.metadata.get("page_number", "?")
        preview = node.text[:60].replace("\n", " ")
        print(f"  [{i+1}/{len(nodes)}] p{page}: {preview}...")
        entry = classify_node(node, program, source)
        entries.append(entry)
        result = entry.classification
        print(
            f"    → {result.is_jim_crow} | confidence={result.confidence:.2f}"
            f" | review={result.needs_human_review}"
        )

    print("Aggregating results...")
    output = aggregate_results(entries, source)

    out_dir = Path(__file__).parent.parent / "doc_processing_results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{ocr_path.stem}_classified.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    stats = output["statistics"]
    print(f"\nDone. Results written to {out_path}")
    print(f"  Total sections : {stats['total_sections']}")
    print(f"  Jim Crow       : {stats['classified_jim_crow']}")
    print(f"  Ambiguous      : {stats['ambiguous']}")
    print(f"  Needs review   : {stats['needs_human_review']}")
    print(f"  Not Jim Crow   : {stats['not_jim_crow']}")


if __name__ == "__main__":
    main()
