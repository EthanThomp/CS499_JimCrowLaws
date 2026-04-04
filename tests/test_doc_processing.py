"""
test_pipeline.py — Tests for the document processing pipeline.

Verifies that OCR JSON is correctly read, segmented, and aggregated.

Run:
    pytest tests/test_pipeline.py -v
"""

import sys
from pathlib import Path

# Allow imports from doc_processing/
sys.path.insert(0, str(Path(__file__).parent.parent / "doc_processing"))

from reader import OCRJsonReader
from processor import segment_documents, aggregate_results
from models import StatuteClassification, StatuteEntry

# ---------------------------------------------------------------------------
# Shared test fixture: a minimal OCR JSON with 3 pages (one blank)
# ---------------------------------------------------------------------------

SAMPLE_OCR = {
    "source": {
        "filename": "Test_Statutes_1900.pdf",
        "title": "Test Statutes",
        "author": "Kentucky",
        "year": 1900,
        "document_type": "session_laws",
    },
    "pages": [
        {
            "page_number": 1,
            "text": "AN ACT to establish separate schools for white and colored children.",
            "keyword_hits": ["colored"],
        },
        {
            "page_number": 2,
            "text": "   ",  # blank page — should be skipped
            "keyword_hits": [],
        },
        {
            "page_number": 3,
            "text": "AN ACT to regulate the inspection of boilers.",
            "keyword_hits": [],
        },
    ],
}


# ---------------------------------------------------------------------------
# 1. OCRJsonReader: produces correct Documents with correct metadata
# ---------------------------------------------------------------------------

class TestOCRJsonReader:
    def setup_method(self):
        reader = OCRJsonReader()
        self.docs = reader.load_data_from_dict(SAMPLE_OCR)

    def test_returns_one_document_per_page(self):
        assert len(self.docs) == 3

    def test_document_text_matches_input(self):
        assert "separate schools" in self.docs[0].text
        assert "boilers" in self.docs[2].text

    def test_metadata_page_number(self):
        assert self.docs[0].metadata["page_number"] == 1
        assert self.docs[2].metadata["page_number"] == 3

    def test_metadata_source_fields(self):
        meta = self.docs[0].metadata
        assert meta["source_filename"] == "Test_Statutes_1900.pdf"
        assert meta["year"] == 1900

    def test_metadata_keyword_hits(self):
        assert self.docs[0].metadata["keyword_hits"] == ["colored"]
        assert self.docs[1].metadata["keyword_hits"] == []


# ---------------------------------------------------------------------------
# 2. segment_documents: converts Documents to TextNodes, skips blanks
# ---------------------------------------------------------------------------

class TestSegmentDocuments:
    def setup_method(self):
        reader = OCRJsonReader()
        docs = reader.load_data_from_dict(SAMPLE_OCR)
        self.nodes = segment_documents(docs)

    def test_blank_page_is_skipped(self):
        assert len(self.nodes) == 2  # 3 pages, 1 blank → 2 nodes

    def test_node_text_preserved(self):
        texts = [n.text for n in self.nodes]
        assert any("separate schools" in t for t in texts)
        assert any("boilers" in t for t in texts)

    def test_node_metadata_preserved(self):
        assert self.nodes[0].metadata["page_number"] == 1
        assert self.nodes[1].metadata["page_number"] == 3


# ---------------------------------------------------------------------------
# 3. aggregate_results: correct statistics and human review queue
# ---------------------------------------------------------------------------

def _make_entry(page, is_jim_crow, confidence, racial_indicator, needs_review):
    """Helper to build a StatuteEntry with a given classification."""
    return StatuteEntry(
        entry_id=f"test_p{page}",
        source_filename="Test_Statutes_1900.pdf",
        page_number=page,
        year=1900,
        ocr_text="test text",
        citation="Test Statutes, 1900, p. " + str(page),
        classification=StatuteClassification(
            is_jim_crow=is_jim_crow,
            confidence=confidence,
            category="education" if is_jim_crow != "no" else None,
            document_type="session_laws",
            title="Test",
            summary="Test summary.",
            keywords=["test"],
            racial_indicator=racial_indicator,
            needs_human_review=needs_review,
            reasoning="test reasoning",
        ),
    )


class TestAggregateResults:
    def setup_method(self):
        self.entries = [
            _make_entry(1, "yes", 0.95, "explicit", False),
            _make_entry(2, "no", 0.90, "none", False),
            _make_entry(3, "ambiguous", 0.50, "implicit", True),  # low confidence + implicit
        ]
        self.source = SAMPLE_OCR["source"]
        self.result = aggregate_results(self.entries, self.source)

    def test_statistics_counts(self):
        stats = self.result["statistics"]
        assert stats["total_sections"] == 3
        assert stats["classified_jim_crow"] == 1
        assert stats["not_jim_crow"] == 1
        assert stats["ambiguous"] == 1
        assert stats["needs_human_review"] == 1

    def test_human_review_queue_contains_flagged_entry(self):
        queue = self.result["human_review_queue"]
        assert len(queue) == 1
        assert queue[0]["entry_id"] == "test_p3"

    def test_human_review_reason_is_low_confidence(self):
        queue = self.result["human_review_queue"]
        assert queue[0]["reason"] == "low confidence"

    def test_source_document_preserved(self):
        assert self.result["source_document"]["year"] == 1900
        assert self.result["source_document"]["title"] == "Test Statutes"

    def test_processed_at_is_present(self):
        assert "processed_at" in self.result
