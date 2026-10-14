"""The only place that talks to the model: AMD Token Factory, OpenAI-compatible API.

The model never does the maths. Here it reads the footnotes of the price lists
(mg/extract/pdf.py, read_note). The price lists themselves are read by the Evolus
extractor, which runs on the same model, and the supplier email is written by the
Evolus email tool.

Rules for this endpoint, found by testing:
- the first message is always a system message (without it Gemma does not stop);
- max_tokens is always set (max_completion_tokens is ignored by the gateway);
- reasoning_effort is never sent (it breaks Gemma's answers).
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "Gemma-4-31B-IT"  # the model used in the product
DEV_MODEL = "DeepSeek-V4-Flash"  # cheaper, for development runs

DEFAULT_SYSTEM = "You are a precise assistant for a purchasing team. Answer only what is asked."
TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 4  # how many times a rate-limited (429) call is tried
RETRY_WAIT_SECONDS = 5

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class LLMError(Exception):
    """The model call failed or returned something unusable."""


def load_env(path=ENV_FILE):
    """Copies the KEY=value lines of .env into the environment. Existing variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_payload(user, system=DEFAULT_SYSTEM, model=None, max_tokens=800, json_mode=False):
    """Builds the request body. Kept separate so the rules above can be tested offline."""
    payload = {
        "model": model or os.environ.get("AMD_MODEL") or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def send(payload, timeout=TIMEOUT_SECONDS):
    """One HTTP call to /chat/completions. Returns (status, body text, Retry-After header)."""
    load_env()
    key = os.environ.get("AMD_TOKENFACTORY_API_KEY", "")
    base = os.environ.get("AMD_TOKENFACTORY_BASE_URL", "").rstrip("/")
    if not key or not base:
        raise LLMError("AMD_TOKENFACTORY_API_KEY or AMD_TOKENFACTORY_BASE_URL is missing (see .env.example)")
    request = urllib.request.Request(
        base + "/chat/completions",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode(), None
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace"), error.headers.get("Retry-After")
    except (urllib.error.URLError, TimeoutError) as error:
        raise LLMError(f"network error: {error}") from error


def complete(payload, timeout=TIMEOUT_SECONDS):
    """Sends the payload and returns the answer text. On 429 it waits and tries again."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, body, retry_after = send(payload, timeout)
        if status == 200:
            choice = json.loads(body)["choices"][0]
            text = choice["message"].get("content") or ""
            if choice.get("finish_reason") == "length":
                raise LLMError("answer cut off at max_tokens: raise max_tokens or shorten the request")
            return text.strip()
        if status == 429 and attempt < MAX_ATTEMPTS:
            wait = float(retry_after) if retry_after and retry_after.isdigit() else RETRY_WAIT_SECONDS * attempt
            time.sleep(wait)
            continue
        raise LLMError(f"HTTP {status}: {body[:300]}")


def ask_text(user, system=DEFAULT_SYSTEM, model=None, max_tokens=800):
    """Asks the model and returns its answer as plain text."""
    return complete(build_payload(user, system, model, max_tokens))


def ask_json(user, system=DEFAULT_SYSTEM, model=None, max_tokens=800):
    """Asks the model for a JSON object and returns it parsed.

    The caller must still validate the fields: this only guarantees valid JSON.
    """
    system = system + " Reply with a single JSON object and nothing else."
    text = complete(build_payload(user, system, model, max_tokens, json_mode=True))
    # Some models wrap the JSON in a ```json fence: keep only the object itself.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"no JSON object in the answer: {text[:200]}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise LLMError(f"invalid JSON in the answer: {text[:200]}") from error


def model_answers(model=DEFAULT_MODEL) -> bool:
    """True if the model answers a one-word question right now. Used to say what failed, when something fails."""
    try:
        status, _, _ = send(build_payload("Reply with OK.", model=model, max_tokens=5), timeout=20)
    except LLMError:
        return False
    return status == 200
