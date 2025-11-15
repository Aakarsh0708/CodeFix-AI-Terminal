# For prototype, simple local file storage of history (append).
from pathlib import Path
import json
HISTORY_FILE = Path(__file__).resolve().parent.parent / "diagnostics_history.json"

def save_history(entry: dict):
    data = []
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(entry)
    HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
