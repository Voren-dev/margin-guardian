#!/usr/bin/env python3
"""Checks the Evolus workspace connection: agent list and AI tools catalog.
Read-only. Reads the key from .env and never prints it."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CHAT_BASE = "https://api.evolus.ai/v1"
REST_BASE = "https://api.evolus.ai/api/v1"


def load_env(path):
    if not path.exists():
        sys.exit(f"{path} not found: copy .env.example to .env and fill it in")
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:300]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


load_env(Path(__file__).resolve().parent.parent / ".env")
KEY = os.environ.get("EVOLUS_API_KEY", "")
APP_ID = os.environ.get("EVOLUS_APPLICATION_ID", "")
if not KEY or not APP_ID:
    sys.exit("EVOLUS_API_KEY or EVOLUS_APPLICATION_ID is empty in .env")
print(f"key: present ({len(KEY)} chars), application id: present ({len(APP_ID)} chars)")

# 1. Agents of the workspace, through the OpenAI-compatible chat API.
status, data = get(f"{CHAT_BASE}/models", {"Authorization": f"Bearer {KEY}"})
if status == 200:
    agents = [m.get("id", "?").split(":")[-1] for m in data.get("data", [])]
    print(f"1. agents: HTTP 200, {len(agents)} found: {agents}")
else:
    print(f"1. agents: HTTP {status} {data}")

# 2. AI tools catalog, through the REST API.
status, data = get(f"{REST_BASE}/ai-tools", {"X-ApiKey": KEY, "X-Application-Id": APP_ID})
if status == 200:
    print(f"2. ai tools: HTTP 200 {[tool.get('slug') for tool in data]}")
else:
    print(f"2. ai tools: HTTP {status} {data}")
