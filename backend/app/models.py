from pydantic import BaseModel
from typing import Optional

class DiagnoseRequest(BaseModel):
    filename: str
    language: str
    code: str
    run_cmd: Optional[str] = None
    stderr: Optional[str] = None
    mode: Optional[str] = "quick"  # quick or deep
    persona: Optional[str] = "expert"  # e.g., teacher, simple, expert
