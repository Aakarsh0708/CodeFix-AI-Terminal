# app/api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import tempfile
from .runner import run_linter_for_language   # ensure runner.py is in app/
from .groq_client import ask_groq_json

router = APIRouter()


# ========== Diagnose Request ==========
class DiagnoseRequest(BaseModel):
    filename: str | None = None
    language: str | None = None
    code: str | None = None
    stderr: str | None = None
    mode: str | None = "quick"
    persona: str | None = "expert"


@router.post("/diagnose")
async def diagnose(req: DiagnoseRequest):
    """
    Calls Groq AI to analyze error and produce structured JSON:
    { summary, root_cause, fix, patch }
    """
    prompt = f"""
Diagnose the user's code and errors. Return ONLY valid JSON with keys 'summary', 'root_cause', 'fix', and 'patch'.
filename: {req.filename}
language: {req.language}
mode: {req.mode}
persona: {req.persona}
stderr: {req.stderr}

Code:
{req.code}
"""
    try:
        res = ask_groq_json(prompt)
        return {"diagnosis": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Run Code Request ==========
class RunRequest(BaseModel):
    language: str
    filename: str | None = None
    code: str


@router.post("/run")
async def run_code(req: RunRequest):
    """
    Uses runner.py to execute the code safely inside a temp directory.
    Handles Python / JavaScript / Java / C / C++
    """

    # choose extension based on language
    lang = (req.language or "").lower()
    ext = {
        "python": ".py",
        "javascript": ".js",
        "java": ".java",
        "c": ".c",
        "cpp": ".cpp",
        "c++": ".cpp",
    }.get(lang, ".txt")

    with tempfile.TemporaryDirectory() as td:
        # assign filename or fallback to main.ext
        file_path = os.path.join(td, req.filename or f"main{ext}")

        # write code to temp file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(req.code or "")

        # run using the universal runner.py logic
        stdout, stderr, rc, executed_cmd = run_linter_for_language(file_path, lang)

        return {
            "stdout": stdout,
            "stderr": stderr,
            "rc": rc,
            "executed_cmd": executed_cmd,
            "used_filename": file_path,
        }
