#!/usr/bin/env python3
"""Checks the AMD Token Factory connection: model list, a plain answer, a tool call.
Reads the key from .env and never prints it."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path):
    if not path.exists():
        sys.exit(f"{path} not found: copy .env.example to .env and fill it in")
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:400]}


load_env(Path(__file__).resolve().parent.parent / ".env")
KEY = os.environ.get("AMD_TOKENFACTORY_API_KEY", "")
BASE = os.environ.get("AMD_TOKENFACTORY_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("AMD_MODEL", "Gemma-4-31B-IT")
if not KEY:
    sys.exit("AMD_TOKENFACTORY_API_KEY is empty in .env")
print(f"key: present ({len(KEY)} chars), base: {BASE}, model: {MODEL}")

status, data = call("GET", "/models")
ids = [m.get("id") for m in data.get("data", [])] if status == 200 else []
print(f"1. models: HTTP {status}", ids if ids else data)

status, data = call("POST", "/chat/completions", {
    "model": MODEL,
    "messages": [{"role": "system", "content": "You are concise."},
                 {"role": "user", "content": "Say hello in one sentence."}],
    "max_tokens": 200,
})
text = data["choices"][0]["message"].get("content") if status == 200 else data
print(f"2. chat: HTTP {status}", text)

status, data = call("POST", "/chat/completions", {
    "model": MODEL,
    "messages": [{"role": "system", "content": "Use the tool when you need data."},
                 {"role": "user", "content": "What is the gross margin of product SKU-42?"}],
    "tools": [{"type": "function", "function": {
        "name": "get_margin",
        "description": "Returns the gross margin of a product",
        "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
    }}],
    "max_tokens": 400,
})
calls = data["choices"][0]["message"].get("tool_calls") if status == 200 else data
print(f"3. tool call: HTTP {status}", json.dumps(calls)[:400])
