#!/usr/bin/env python3
"""Quick manual check of mg/llm.py against both models. Usage: python scripts/try_llm.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mg import llm

QUESTION = (
    'Do "Front light 800 lm USB-C" and "Frontlicht 800 Lumen, USB-C" describe the same product? '
    'Use the keys "same" (true or false) and "confidence" (0 to 1).'
)

for model in (llm.DEV_MODEL, llm.DEFAULT_MODEL):
    for label, ask in (
        ("text", lambda: llm.ask_text("Reply with the single word OK.", model=model, max_tokens=50)),
        ("json", lambda: llm.ask_json(QUESTION, model=model, max_tokens=100)),
    ):
        start = time.time()
        try:
            result = repr(ask())
        except llm.LLMError as error:
            result = f"FAILED: {error}"
        print(f"{model} {label} ({time.time() - start:.1f}s): {result}")
