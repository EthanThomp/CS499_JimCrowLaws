#!/usr/bin/env python3
"""
Import classified results from the LLM processing pipeline into the PostgreSQL database.

Usage:
    python import_classified.py [path/to/classified.json]

If no path is given, defaults to doc_processing_results/classified_results.json.
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': 'localhost',
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'jimcrow_laws'),
    'user': os.getenv('POSTGRES_USER', 'jimcrow_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'JimCrow@1965'),
}


def import_classified_results(json_path: Path):
    print(f"Loading: {json_path}")
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    source = data['source_document']
    all_entries = data['entries']
    entries = [e for e in all_entries if e['classification'].get('is_jim_crow') == 'yes']
    print(f"  Found {len(all_entries)} total entries, {len(entries)} classified as Jim Crow laws from: {source.get('title', 'Unknown')}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Clear all existing data cleanly so we only have properly imported records.
    # Cascade handles document_classifications and extracted_entities automatically.
    print("Clearing existing data...")
    cur.execute("TRUNCATE TABLE document_classifications, extracted_entities, legal_documents CASCADE")

    inserted = 0
    for entry in entries:
        c = entry['classification']

        year = entry.get('year')
        date_enacted = f"{year}-01-01" if year else None
        keywords = c.get('keywords') or []

        cur.execute(
            """
            INSERT INTO legal_documents (
                title,
                source_file,
                document_type,
                date_enacted,
                full_text,
                entry_id,
                year,
                citation,
                category,
                summary,
                keywords,
                is_jim_crow,
                confidence,
                page_number,
                racial_indicator,
                needs_human_review,
                reasoning
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )
            """,
            (
                c.get('title') or entry['entry_id'],
                entry.get('source_filename'),
                source.get('document_type'),
                date_enacted,
                entry.get('ocr_text'),
                entry.get('entry_id'),
                year,
                entry.get('citation'),
                c.get('category'),
                c.get('summary'),
                keywords,
                c.get('is_jim_crow'),
                c.get('confidence'),
                entry.get('page_number'),
                c.get('racial_indicator'),
                c.get('needs_human_review', False),
                c.get('reasoning'),
            ),
        )
        inserted += 1
        status = c.get('is_jim_crow', '?')
        print(f"  [{inserted:02d}] {status:9s} | {c.get('title', entry['entry_id'])[:70]}")

    conn.commit()
    cur.close()
    conn.close()

    # Summary
    jim_crow = sum(1 for e in entries if e['classification'].get('is_jim_crow') == 'yes')
    ambiguous = sum(1 for e in entries if e['classification'].get('is_jim_crow') == 'ambiguous')
    not_jc = sum(1 for e in entries if e['classification'].get('is_jim_crow') == 'no')

    print(f"\nDone. Inserted {inserted} entries total:")
    print(f"  Jim Crow (yes) : {jim_crow}")
    print(f"  Ambiguous      : {ambiguous}")
    print(f"  Not Jim Crow   : {not_jc}")


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / 'doc_processing_results' / 'classified_results.json'

    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    import_classified_results(path)
