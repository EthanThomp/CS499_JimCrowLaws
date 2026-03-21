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
- document_type: infer the type of the source document from context clues in the text:
    "session_laws"       = acts passed at a legislative session (e.g. "Acts of 1865")
    "constitution"       = general constitutional text
    "state_constitution" = Kentucky state constitution specifically
    "amendments"         = constitutional or statutory amendments
    "codes"              = compiled statutes or revised codes (e.g. Kentucky Revised Statutes)
    "criminal_laws"      = criminal codes or penal statutes
    "civil_laws"         = civil codes or civil procedure statutes
    "other"              = any other document type not listed above
- reasoning should explain your chain of thought step by step.
"""
