import json

import pytest

from mg import llm


def test_payload_follows_the_endpoint_rules():
    payload = llm.build_payload("hello", model=llm.DEFAULT_MODEL)
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1] == {"role": "user", "content": "hello"}
    assert payload["max_tokens"] > 0
    assert "reasoning_effort" not in payload
    assert "max_completion_tokens" not in payload


def answer(text, finish_reason="stop"):
    body = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": finish_reason}]})
    return 200, body, None


def test_a_429_is_retried(monkeypatch):
    replies = [(429, "slow down", None), answer("OK")]
    monkeypatch.setattr(llm, "send", lambda payload, *_: replies.pop(0))
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    assert llm.ask_text("hello") == "OK"
    assert replies == []


def test_it_gives_up_after_too_many_429(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "send", lambda payload, *_: calls.append(1) or (429, "slow down", None))
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    with pytest.raises(llm.LLMError):
        llm.ask_text("hello")
    assert len(calls) == llm.MAX_ATTEMPTS


def test_a_cut_off_answer_is_an_error(monkeypatch):
    monkeypatch.setattr(llm, "send", lambda payload, *_: answer("OK and then", finish_reason="length"))
    with pytest.raises(llm.LLMError):
        llm.ask_text("hello")


def test_json_inside_a_code_fence_is_still_parsed(monkeypatch):
    monkeypatch.setattr(llm, "send", lambda payload, *_: answer('```json\n{"same": true}\n```'))
    assert llm.ask_json("same product?") == {"same": True}


def test_an_answer_without_json_is_an_error(monkeypatch):
    monkeypatch.setattr(llm, "send", lambda payload, *_: answer("I think they are the same."))
    with pytest.raises(llm.LLMError):
        llm.ask_json("same product?")


@pytest.mark.network
@pytest.mark.parametrize("model", [llm.DEV_MODEL, llm.DEFAULT_MODEL])
def test_real_call_text(model):
    assert "OK" in llm.ask_text("Reply with the single word OK.", model=model, max_tokens=50)


@pytest.mark.network
@pytest.mark.parametrize("model", [llm.DEV_MODEL, llm.DEFAULT_MODEL])
def test_real_call_json(model):
    data = llm.ask_json('Reply with the JSON object {"ok": true}.', model=model, max_tokens=50)
    assert data == {"ok": True}
