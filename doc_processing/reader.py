"""
OCRJsonReader — LlamaIndex BaseReader for the v2 OCR JSON format.

Converts each page in the OCR JSON into a LlamaIndex Document with
structured metadata so downstream components can work page-by-page.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document


class OCRJsonReader(BaseReader):
    """Reads a v2 OCR JSON file and returns one Document per page."""

    def load_data(
        self,
        file: Path,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)

        source = data.get("source", {})
        pages = data.get("pages", [])

        documents = []
        for page in pages:
            metadata = {
                "page_number": page["page_number"],
                "source_filename": source.get("filename", ""),
                "source_title": source.get("title", ""),
                "year": source.get("year"),
                "document_type": source.get("document_type", ""),
                "keyword_hits": page.get("keyword_hits", []),
            }
            if extra_info:
                metadata.update(extra_info)

            doc = Document(
                text=page["text"],
                metadata=metadata,
                id_=f"{source.get('filename', 'doc')}_p{page['page_number']}",
            )
            documents.append(doc)

        return documents

    def load_data_from_dict(self, data: Dict[str, Any]) -> List[Document]:
        """Load from an already-parsed dict (useful for testing)."""
        source = data.get("source", {})
        pages = data.get("pages", [])

        documents = []
        for page in pages:
            metadata = {
                "page_number": page["page_number"],
                "source_filename": source.get("filename", ""),
                "source_title": source.get("title", ""),
                "year": source.get("year"),
                "document_type": source.get("document_type", ""),
                "keyword_hits": page.get("keyword_hits", []),
            }

            doc = Document(
                text=page["text"],
                metadata=metadata,
                id_=f"{source.get('filename', 'doc')}_p{page['page_number']}",
            )
            documents.append(doc)

        return documents
