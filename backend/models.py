from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Strict):
    page: int = Field(ge=1)
    printed_page: str = ''
    kind: Literal['table', 'diagram', 'description', 'footnote'] = 'table'
    quote: str = ''
    # Model coordinates are intentionally not trusted. v1 uses page-level evidence.

class Candidate(Strict):
    model: str = Field(min_length=1)
    package: str = Field(min_length=1)
    pin_count: int | None = Field(default=None, ge=1)
    fact: Literal['explicit', 'inferred', 'uncertain'] = 'uncertain'
    observation: str = ''
    evidence: list[Evidence] = Field(min_length=1)

class TableRow(Strict):
    page: int = Field(ge=1)
    name: str
    selected_column: str = Field(min_length=1)
    columns: dict[str,list[str]]

class Pin(Strict):
    number: str = Field(min_length=1)
    original_name: str
    symbol_name: str
    electrical_type: Literal['Unknown','Input','Output','Bidirectional','Passive','Power','Open Collector','Open Emitter','3-State'] = 'Unknown'
    # Reserved for spreadsheet compatibility. Functional grouping is disabled in v1.
    group: str = ''
    part: str = '1'
    position: Literal['Left','Right','Top','Bottom'] = 'Left'
    kind: Literal['electrical','NC','DNC','exposed_pad','shield','mechanical','uncertain'] = 'electrical'
    # All pins are visible. Invisible pins are not supported in this review workspace.
    visibility: Literal['Visible','1'] = '1'
    fact: Literal['explicit','inferred','uncertain'] = 'uncertain'
    observation: str = ''
    issues: list[str] = []
    evidence: list[Evidence] = Field(min_length=1)
    table_row: TableRow | None = None

class CompactPin(Strict):
    number: str = Field(min_length=1)
    original_name: str
    electrical_type: Literal['Unknown','Input','Output','Bidirectional','Passive','Power','Open Collector','Open Emitter','3-State'] = 'Unknown'
    part: str = '1'
    position: Literal['Left','Right','Top','Bottom'] = 'Left'
    kind: Literal['electrical','NC','DNC','exposed_pad','shield','mechanical','uncertain'] = 'electrical'
    fact: Literal['explicit','inferred','uncertain'] = 'uncertain'
    observation: str = ''
    issues: list[str] = []
    evidence_ids: list[int] = Field(min_length=1)
    table_row_id: int | None = None

class Scan(Strict):
    candidates: list[Candidate]
    relevant_pages: list[int]
    notes: list[str] = []

class Extraction(Strict):
    pins: list[Pin]
    notes: list[str] = []

class CompactExtraction(Strict):
    evidence: list[Evidence] = Field(min_length=1)
    table_rows: list[TableRow] = []
    pins: list[CompactPin]
    notes: list[str] = []

class RunRequest(Strict):
    stage: Literal['scan','extract']
    pages: list[int] = []

class EditRequest(Strict):
    revision: int
    numbers: list[str]
    values: dict

class TargetRequest(Strict):
    revision: int
    candidate: Candidate

class PartsRequest(Strict):
    revision: int
    parts: list[str] = Field(min_length=1)

class AIConfigRequest(Strict):
    provider: Literal['DeepSeek','OpenAI-compatible']
    base_url: str = Field(min_length=9, max_length=300)
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=8, max_length=500)

class VisionConfigRequest(Strict):
    base_url: str = Field(min_length=9, max_length=300)
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=8, max_length=500)

class ModelConfigRequest(Strict):
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(min_length=9, max_length=300)
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=8, max_length=500)
