#!/usr/bin/env python3
"""Probes how Gemma-4-31B-IT on AMD Token Factory reacts to different request shapes.
Reads the key from .env and never prints it. Stays under the 20 requests/minute limit."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
KEY = os.environ["AMD_TOKENFACTORY_API_KEY"]
BASE = os.environ["AMD_TOKENFACTORY_BASE_URL"].rstrip("/")
MODEL = os.environ.get("AMD_MODEL", "Gemma-4-31B-IT")
USER = [{"role": "user", "content": "Reply with the single word OK."}]

TESTS = {
    "no system message": {"messages": USER, "max_tokens": 30},
    "max_tokens=1": {"messages": USER, "max_tokens": 1},
    "max_tokens=5": {"messages": USER, "max_tokens": 5},
    "max_completion_tokens instead of max_tokens": {"messages": USER, "max_completion_tokens": 20},
    "system message first": {"messages": [{"role": "system", "content": "Be brief."}] + USER, "max_tokens": 30},
    "developer message first": {"messages": [{"role": "developer", "content": "Be brief."}] + USER, "max_tokens": 30},
    "reasoning_effort none": {"messages": USER, "max_tokens": 30, "reasoning_effort": "none"},
    "reasoning_effort low": {"messages": USER, "max_tokens": 30, "reasoning_effort": "low"},
    "reasoning_effort minimal": {"messages": USER, "max_tokens": 30, "reasoning_effort": "minimal"},
    "temperature 0": {"messages": USER, "max_tokens": 30, "temperature": 0},
    "stream_options": {"messages": USER, "max_tokens": 30, "stream": False, "stream_options": {"include_usage": True}},
    "content as parts": {"messages": [{"role": "user", "content": [{"type": "text", "text": USER[0]["content"]}]}], "max_tokens": 30},
}


def call(body):
    start = time.time()
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            choice = json.loads(r.read())["choices"][0]
            return r.status, round(time.time() - start, 1), (choice["message"].get("content") or "")[:40], choice.get("finish_reason")
    except urllib.error.HTTPError as e:
        return e.code, round(time.time() - start, 1), e.read().decode(errors="replace")[:200], ""
    except Exception as e:
        return "ERR", round(time.time() - start, 1), repr(e)[:120], ""


for name, body in TESTS.items():
    body["model"] = MODEL
    print(f"{name} => {call(body)}")
    time.sleep(3.2)
