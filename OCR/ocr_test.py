import sys
sys.path.insert(0, ".")
from jim_crow_ocr import find_references, extract_title_page_metadata, _is_junk, _pypdf_text_usable, KEYWORDS

passed = 0
failed = 0


def run_test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS: {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: {name} — {e}")
        failed += 1


# Test 1: Keyword Detection

def test_keyword_detection():
    mock_pages = [
        {"page_number": 1, "text": "General provisions of the act.", "keyword_hits": []},
        {"page_number": 2, "text": "No colored person shall be admitted to the same car as white passengers.", "keyword_hits": []},
        {"page_number": 3, "text": "The fee for filing shall be two dollars.", "keyword_hits": []},
    ]
    mock_metadata = {
        "title": "Acts of the General Assembly",
        "author": "Kentucky General Assembly",
        "publication_date": "1890",
        "page_count": 3,
    }

    results = find_references(mock_pages, mock_metadata, "test.pdf")

    pages_with_hits = [p for p in results["pages"] if p["keyword_hits"]]
    assert len(pages_with_hits) == 1, f"Expected 1 page with hits, got {len(pages_with_hits)}"
    assert pages_with_hits[0]["page_number"] == 2
    assert "colored" in pages_with_hits[0]["keyword_hits"]
    assert len(results["keyword_references"]) >= 1
    assert results["keyword_references"][0]["keyword"] == "colored"
    assert results["keyword_references"][0]["page_number"] == 2
    assert results["statistics"]["pages_with_keyword_hits"] == 1


# Test 2: Title Page Metadata Extraction 

def test_title_page_metadata():
    mock_pages = [
        {
            "page_number": 1,
            "text": "# Acts of the General Assembly of Kentucky\n\nBy\nKentucky General Assembly\n\n1890\n\nFrankfort, Kentucky",
            "keyword_hits": [],
        },
        {
            "page_number": 2,
            "text": "CHAPTER 1\n\nAN ACT relating to public schools.",
            "keyword_hits": [],
        },
    ]

    result = extract_title_page_metadata(mock_pages)

    assert result["title"] == "Acts of the General Assembly of Kentucky", f"Unexpected title: {result['title']}"
    assert result["author"] == "Kentucky General Assembly", f"Unexpected author: {result['author']}"
    assert result["publication_date"] == "1890", f"Unexpected date: {result['publication_date']}"
    assert result["metadata_source"] == "title_page"


# Test 3: Junk Page Filtering 

def test_junk_filtering():
    junk_cases = ["", "   ", "nogle", "google nogle", "abc"]
    real_cases = [
        "AN ACT to establish separate schools for white and colored children.",
        "# CHAPTER 399\n\nAN ACT relating to the registration of voters.",
        "The General Assembly of Kentucky hereby enacts as follows:",
    ]

    for text in junk_cases:
        assert _is_junk(text), f"Expected junk: {repr(text)}"

    for text in real_cases:
        assert not _is_junk(text), f"Expected real content: {repr(text)}"


# Test 4: pypdf Text Quality Check 

def test_pypdf_quality():
    good_cases = [
        "AN ACT to establish separate schools for white and colored children of this state, and to provide for the funding thereof.",
        "The General Assembly of Kentucky hereby enacts as follows: Section 1. All children shall attend the school designated for their race.",
    ]
    bad_cases = [
        "ANACTtoestablishseparateschoolsforwhiteandcoloredchildren",
        "abc",
        "x" * 200,
    ]

    for text in good_cases:
        assert _pypdf_text_usable(text), f"Expected usable: {repr(text[:60])}"

    for text in bad_cases:
        assert not _pypdf_text_usable(text), f"Expected unusable: {repr(text[:60])}"


# Test 5: Output JSON Schema 

def test_output_schema():
    mock_pages = [
        {"page_number": 1, "text": "No colored person shall ride in the same car.", "keyword_hits": []},
    ]
    mock_metadata = {
        "title": "Acts of 1890",
        "author": "Kentucky General Assembly",
        "publication_date": "1890",
        "page_count": 100,
    }

    results = find_references(mock_pages, mock_metadata, "test.pdf")

    required_keys = {"source", "pages", "keyword_references", "statistics", "ocr_metadata"}
    assert required_keys == set(results.keys()), f"Missing or extra keys: {set(results.keys()) ^ required_keys}"

    for field in ("filename", "title", "author", "year", "document_type"):
        assert field in results["source"], f"Missing source field: {field}"
    assert results["source"]["year"] == 1890

    for page in results["pages"]:
        for field in ("page_number", "text", "keyword_hits"):
            assert field in page, f"Missing page field: {field}"

    for ref in results["keyword_references"]:
        for field in ("keyword", "page_number", "line_number_in_page", "context"):
            assert field in ref, f"Missing ref field: {field}"

    for field in ("total_pages", "pages_with_keyword_hits", "total_keyword_hits"):
        assert field in results["statistics"], f"Missing stats field: {field}"

    assert results["ocr_metadata"]["format_version"] == "2.0"
    assert results["ocr_metadata"]["engine"] == "pypdf+llama_cloud"


# Run all tests

run_test("Keyword Detection",           test_keyword_detection)
run_test("Title Page Metadata",         test_title_page_metadata)
run_test("Junk Page Filtering",         test_junk_filtering)
run_test("pypdf Text Quality Check",    test_pypdf_quality)
run_test("Output JSON Schema",          test_output_schema)

print(f"\n{passed}/{passed + failed} tests passed.")
if failed:
    sys.exit(1)