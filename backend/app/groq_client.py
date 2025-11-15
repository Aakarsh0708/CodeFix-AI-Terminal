# app/groq_client.py
import os
import json
import logging
from typing import Union, Dict, Any

# load .env from this folder (app/) if present
from dotenv import load_dotenv

# load .env located in the same directory as this file
_here = os.path.dirname(__file__)
_dotenv_path = os.path.join(_here, ".env")
load_dotenv(dotenv_path=_dotenv_path, override=False)

# If your environment uses the 'groq' library, import it.
# If not available, adapt to your installed SDK.
try:
    from groq import Groq
except Exception:
    Groq = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def create_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        # helpful message for debugging
        raise RuntimeError(
            "GROQ_API_KEY not set in environment. "
            f"Tried to read from env and { _dotenv_path }. "
            "Make sure .env contains: GROQ_API_KEY=YOUR_KEY and restart the server."
        )
    if Groq is None:
        raise RuntimeError("groq package not available. Please pip install groq")
    # create client
    try:
        client = Groq(api_key=api_key)
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to create Groq client: {e}")


SYSTEM_JSON_INSTRUCTION = """
You are CodeFix AI. ALWAYS respond with a single, valid JSON object and NOTHING else.
The JSON object must contain exactly the keys: "summary", "root_cause", "fix", "patch".
- summary: short one-line summary (max 260 chars)
- root_cause: one-paragraph explanation (plain text, no markdown)
- fix: short exact fix steps or minimal code snippet (plain text, can include code text)
- patch: raw code patch content only (if no patch, return empty string "")
Do not include any markdown formatting, backticks, headings, or extraneous text.
Return strictly JSON in the response body.
"""

def _extract_content_from_resp(resp) -> str:
    """
    Robust extraction of text content from different SDK response shapes.
    Returns a string (may be long) or empty string if not found.
    """
    try:
        choice0 = resp.choices[0]
        # Try message attribute (dict or object)
        msg = getattr(choice0, "message", None)
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        if msg:
            # maybe ChatCompletionMessage object
            content = getattr(msg, "content", None)
            if content:
                return content
        # fallback to 'text' or other fields
        if hasattr(choice0, "text"):
            return getattr(choice0, "text") or ""
        # last resort: try top-level resp fields
    except Exception:
        pass

    # try some common top-level fields
    for attr in ("text", "content", "message"):
        val = getattr(resp, attr, None)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict) and "content" in val:
            return val.get("content", "") or ""
    # fallback to string representation
    try:
        return str(resp)
    except Exception:
        return ""


def ask_groq_json(prompt_text: str, model: str = "llama-3.3-70b-versatile", max_tokens: int = 1000) -> Union[Dict[str, Any], str]:
    """
    Ask Groq to respond with JSON and attempt to parse JSON.
    Returns dict on success, else returns raw text.
    """
    try:
        client = create_client()
    except Exception as e:
        logger.exception("Failed to create Groq client")
        # re-raise so caller can handle / return HTTP error
        raise

    # Compose messages: system enforces JSON-only output
    messages = [
        {"role": "system", "content": SYSTEM_JSON_INSTRUCTION},
        {"role": "user", "content": prompt_text}
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )

        content = _extract_content_from_resp(resp)

        # Try to parse JSON strictly
        if content and isinstance(content, str):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and any(k in parsed for k in ("summary", "root_cause", "fix", "patch")):
                    return parsed
            except Exception:
                # attempt to find JSON substring inside content (e.g., model wrapped it)
                import re
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        if isinstance(parsed, dict) and any(k in parsed for k in ("summary", "root_cause", "fix", "patch")):
                            return parsed
                    except Exception:
                        pass

        # If parsing failed or the content doesn't follow the schema, return raw content (string)
        return content or ""

    except Exception as e:
        logger.exception("Groq API error")
        raise RuntimeError(f"Groq API error: {str(e)}") from e
