from pydantic import BaseModel
from typing import Optional, List, Literal


class StatuteClassification(BaseModel):
    is_jim_crow: Literal["yes", "no", "ambiguous"]
    confidence: float           # 0.0–1.0
    category: Optional[Literal[
        "education", "housing", "marriage",
        "public_accommodations", "incarceration",
        "voting", "labor", "other"
    ]]
    title: str
    summary: str                # 1–2 sentences
    keywords: List[str]
    racial_indicator: Literal["explicit", "implicit", "none"]
    needs_human_review: bool
    reasoning: str              # internal chain-of-thought, not shown to public


class StatuteEntry(BaseModel):
    entry_id: str               # e.g. "gen_assemb_1865_p87_s1"
    source_filename: str
    page_number: int
    year: Optional[int]
    ocr_text: str
    citation: str               # e.g. "Acts of KY General Assembly, 1865, p. 87"
    classification: StatuteClassification
