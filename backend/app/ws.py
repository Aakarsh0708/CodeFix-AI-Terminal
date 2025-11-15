# app/ws.py
import asyncio
import json
import logging
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from .groq_client import ask_groq_json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# server-side ping interval in seconds
SERVER_PING_INTERVAL = 20


async def _send_ping_periodically(websocket: WebSocket, stop_event: asyncio.Event):
    """Periodically send lightweight keepalive messages to the client."""
    try:
        while not stop_event.is_set():
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                # socket likely closed — stop pinging
                break
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=SERVER_PING_INTERVAL)
            except asyncio.TimeoutError:
                continue
    finally:
        return


def _normalize_ai_response(ai_resp):
    """
    Normalize the response from ask_groq_json into a serializable object.
    ask_groq_json may return a dict or a string. We try to return a dict with
    keys summary, root_cause, fix, patch when possible — otherwise a fallback.
    """
    if isinstance(ai_resp, dict):
        # ensure all keys exist
        return {
            "summary": ai_resp.get("summary", "") if isinstance(ai_resp.get("summary", ""), str) else "",
            "root_cause": ai_resp.get("root_cause", "") if isinstance(ai_resp.get("root_cause", ""), str) else "",
            "fix": ai_resp.get("fix", "") if isinstance(ai_resp.get("fix", ""), str) else "",
            "patch": ai_resp.get("patch", "") if isinstance(ai_resp.get("patch", ""), str) else "",
            **{k: v for k, v in ai_resp.items() if k not in ("summary", "root_cause", "fix", "patch")}
        }

    if isinstance(ai_resp, str):
        # try to parse JSON substring
        try:
            parsed = json.loads(ai_resp)
            if isinstance(parsed, dict):
                return _normalize_ai_response(parsed)
        except Exception:
            import re
            m = re.search(r"\{[\s\S]*\}", ai_resp)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        return _normalize_ai_response(parsed)
                except Exception:
                    pass
        # fallback: put the raw text into root_cause for display
        return {"summary": "", "root_cause": ai_resp, "fix": "", "patch": ""}

    # fallback generic
    return {"summary": "", "root_cause": str(ai_resp), "fix": "", "patch": ""}


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that stays open and handles multiple 'diagnose' messages.
    Expected client message format (JSON):
      { "type": "diagnose", "filename": "...", "language": "...",
        "code": "...", "stderr": "...", "mode": "...", "persona": "..." }
    Server responses:
      { "type": "diagnosis", "diagnosis": <object> }
      { "type": "diagnosis_error", "message": "..." }
      { "type": "pong" } (optional)
      { "type": "ping" } (sent from server)
    """
    await websocket.accept()
    stop_event = asyncio.Event()
    ping_task = asyncio.create_task(_send_ping_periodically(websocket, stop_event))
    logger.info("WebSocket connection accepted")

    try:
        while True:
            try:
                data_raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected.")
                break
            except Exception as e:
                logger.exception("Error receiving from websocket; will close connection.")
                try:
                    await websocket.send_text(json.dumps({"type": "diagnosis_error", "message": f"Receive error: {str(e)}"}))
                except Exception:
                    pass
                break

            # parse JSON payload
            try:
                data = json.loads(data_raw)
            except Exception:
                # not JSON - notify and continue
                try:
                    await websocket.send_text(json.dumps({"type": "diagnosis_error", "message": "Invalid JSON request"}))
                except Exception:
                    pass
                continue

            # support simple ping/pong from client
            if data.get("type") == "ping":
                try:
                    await websocket.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    pass
                continue

            if data.get("type") != "diagnose":
                try:
                    await websocket.send_text(json.dumps({"type": "diagnosis_error", "message": "Unsupported message type; expected 'diagnose'."}))
                except Exception:
                    pass
                continue

            # Extract fields for prompt
            filename = data.get("filename")
            language = data.get("language")
            code = data.get("code", "")
            stderr = data.get("stderr", "")
            mode = data.get("mode", "quick")
            persona = data.get("persona", "expert")

            code_preview = code if code is None or len(code) < 8000 else code[:8000] + "\n...<truncated>"

            prompt = f"""
You are CodeFix AI (persona={persona}, mode={mode}). ALWAYS respond with a single valid JSON object with keys: summary, root_cause, fix, patch.
Language: {language}
Filename: {filename}
STDERR:
{stderr}

Code:
{code_preview}
"""

            # Call the blocking AI client in a thread pool
            loop = asyncio.get_running_loop()
            try:
                ai_resp = await loop.run_in_executor(None, ask_groq_json, prompt)
            except Exception as e:
                logger.exception("Groq query failed")
                # send an error but keep the socket open so client may retry
                try:
                    await websocket.send_text(json.dumps({"type": "diagnosis_error", "message": f"AI error: {str(e)}"}))
                except Exception:
                    pass
                # do not break — allow further messages
                continue

            # Normalize AI result and send back
            try:
                payload = _normalize_ai_response(ai_resp)
                await websocket.send_text(json.dumps({"type": "diagnosis", "diagnosis": payload}))
            except WebSocketDisconnect:
                logger.info("Client disconnected while sending diagnosis.")
                break
            except Exception:
                logger.exception("Failed to send diagnosis over websocket.")
                try:
                    await websocket.send_text(json.dumps({"type": "diagnosis_error", "message": "Failed to send diagnosis"}))
                except Exception:
                    pass
                # continue to allow subsequent messages if any
                continue

    finally:
        # Stop the ping task and close socket gracefully
        stop_event.set()
        try:
            await asyncio.wait_for(ping_task, timeout=1.0)
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WebSocket handler closed")
