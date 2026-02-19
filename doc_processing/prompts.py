CLASSIFICATION_PROMPT = """\
You are analyzing historical Kentucky legal statutes (1865–1966) for a Jim Crow laws archive.

SOURCE: {source_filename}, page {page_number}, year {year}

STATUTE TEXT:
{statute_text}

Classify this statute. Return a JSON object matching this schema:
{schema}

Important notes:
- Many Jim Crow laws do not mention race explicitly. Look for:
  separate facilities, differential penalties, restrictions on rights,
  or enforcement mechanisms that historically applied to Black Kentuckians.
- Set needs_human_review=true if the statute is ambiguous or confidence < 0.7.
- category is null if is_jim_crow is "no".
- racial_indicator values:
    "explicit" = statute names a race directly (colored, negro, white, mulatto)
    "implicit" = statute encodes racial restriction without naming race
    "none"     = no racial dimension detected
- reasoning should explain your chain of thought step by step.
"""
