#!/usr/bin/env python3
"""
Batch import all classified JSON files from doc_processing_results/ into PostgreSQL.
Only imports entries where is_jim_crow == 'yes'. Duplicates are safely skipped.

Usage:
    python import_all.py
"""

import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': 'localhost',
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'jimcrow_laws'),
    'user': os.getenv('POSTGRES_USER', 'jimcrow_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'JimCrow@1965'),
}

RESULTS_DIR = Path(__file__).parent / 'doc_processing_results'


def clean(value):
    """Strip NUL bytes that OCR sometimes embeds and psycopg2 rejects."""
    if isinstance(value, str):
        return value.replace('\x00', '')
    return value


def import_file(json_path: Path, cur) -> tuple[int, int]:
    """Import a single file. Returns (inserted, skipped) counts."""
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    source = data['source_document']
    all_entries = data['entries']
    entries = [e for e in all_entries if e['classification'].get('is_jim_crow') == 'yes']

    if not entries:
        return 0, 0

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
            ON CONFLICT (entry_id) DO NOTHING
            """,
            (
                clean(c.get('title') or entry['entry_id']),
                clean(entry.get('source_filename')),
                clean(source.get('document_type')),
                date_enacted,
                clean(entry.get('ocr_text')),
                clean(entry.get('entry_id')),
                year,
                clean(entry.get('citation')),
                clean(c.get('category')),
                clean(c.get('summary')),
                [clean(k) for k in keywords],
                clean(c.get('is_jim_crow')),
                c.get('confidence'),
                entry.get('page_number'),
                clean(c.get('racial_indicator')),
                c.get('needs_human_review', False),
                clean(c.get('reasoning')),
            ),
        )
        if cur.rowcount > 0:
            inserted += 1

    skipped = len(entries) - inserted
    return inserted, skipped


def main():
    json_files = sorted(RESULTS_DIR.glob('*_results_classified.json'))

    if not json_files:
        print(f"No classified JSON files found in {RESULTS_DIR}")
        return

    print(f"Found {len(json_files)} files to process.\n")
    print(f"{'File':<60} {'Inserted':>8} {'Skipped':>8}")
    print('-' * 78)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    total_inserted = 0
    total_skipped = 0
    errors = []

    for json_path in json_files:
        try:
            inserted, skipped = import_file(json_path, cur)
            conn.commit()
            total_inserted += inserted
            total_skipped += skipped
            print(f"{json_path.name:<60} {inserted:>8} {skipped:>8}")
        except Exception as e:
            conn.rollback()
            errors.append((json_path.name, str(e)))
            print(f"{json_path.name:<60}    ERROR: {e}")

    cur.close()
    conn.close()

    print('-' * 78)
    print(f"{'TOTAL':<60} {total_inserted:>8} {total_skipped:>8}")

    if errors:
        print(f"\n⚠ {len(errors)} file(s) had errors:")
        for name, msg in errors:
            print(f"  {name}: {msg}")
    else:
        print(f"\n✓ All files processed successfully.")


if __name__ == '__main__':
    main()
