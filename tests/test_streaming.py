import asyncio
from types import SimpleNamespace

import openai

from app.retrieval import streaming
from app.retrieval.generation import GeneratedAnswer, GenerationError, GenerationTimeoutError, GenerationUnavailableError
from app.retrieval.streaming import (
    AnswerDelta,
    _AnswerFieldExtractor,
    _decode_json_string_prefix,
    stream_answer,
)


# ---- _decode_json_string_prefix -------------------------------------------------


def test_decode_simple_text_not_closed():
    decoded, consumed, closed = _decode_json_string_prefix("hello")
    assert decoded == "hello"
    assert consumed == 5
    assert closed is False


def test_decode_stops_at_closing_quote():
    decoded, consumed, closed = _decode_json_string_prefix('hi"rest')
    assert decoded == "hi"
    assert consumed == 3
    assert closed is True


def test_decode_handles_escaped_quote():
    decoded, consumed, closed = _decode_json_string_prefix(r'say \"hi\" done' + '"')
    assert decoded == 'say "hi" done'
    assert closed is True


def test_decode_handles_unicode_escape():
    decoded, consumed, closed = _decode_json_string_prefix("caf\\u00e9" + '"')
    assert decoded == "café"
    assert closed is True


def test_decode_leaves_incomplete_trailing_escape_unconsumed():
    decoded, consumed, closed = _decode_json_string_prefix("abc\\")
    assert decoded == "abc"
    assert consumed == 3
    assert closed is False


def test_decode_leaves_incomplete_unicode_escape_unconsumed():
    decoded, consumed, closed = _decode_json_string_prefix("abc\\u00")
    assert decoded == "abc"
    assert consumed == 3
    assert closed is False


def test_decode_handles_newline_escape():
    decoded, consumed, closed = _decode_json_string_prefix(r"line1\nline2" + '"')
    assert decoded == "line1\nline2"
    assert closed is True


# ---- _AnswerFieldExtractor -------------------------------------------------------


def test_extractor_reconstructs_full_real_world_trace():
    # Mirrors the actual delta sequence observed from the real streaming API.
    chunks = [
        '{"', "answer", '":"', "The", " sky", " is", " blue", ",", " and", " the",
        " grass", " is", " green", ".", '","cited_labels":["S1"],"insufficient_evidence":false}',
    ]
    extractor = _AnswerFieldExtractor()
    reconstructed = "".join(extractor.feed(c) for c in chunks)

    assert reconstructed == "The sky is blue, and the grass is green."


def test_extractor_emits_nothing_before_value_starts():
    extractor = _AnswerFieldExtractor()
    assert extractor.feed('{"') == ""
    assert extractor.feed("answer") == ""
    assert extractor.feed('":"') == ""


def test_extractor_stops_emitting_after_close():
    extractor = _AnswerFieldExtractor()
    extractor.feed('{"answer":"hi"')
    assert extractor.feed(',"cited_labels":[]') == ""
    assert extractor.feed("more text entirely") == ""


def test_extractor_handles_escaped_quote_inside_answer():
    extractor = _AnswerFieldExtractor()
    result = extractor.feed('{"answer":"she said \\"hi\\""')
    assert result == 'she said "hi"'


def test_extractor_handles_unicode_escape_split_across_feeds():
    extractor = _AnswerFieldExtractor()
    out = ""
    out += extractor.feed('{"answer":"caf')
    out += extractor.feed("\\u00")  # incomplete escape split across chunks
    out += extractor.feed('e9"')
    assert out == "café"


def test_extractor_handles_key_pattern_split_across_feeds():
    extractor = _AnswerFieldExtractor()
    out = ""
    out += extractor.feed('{"answ')
    out += extractor.feed('er":"')
    out += extractor.feed("hi")
    out += extractor.feed('"')
    assert out == "hi"


def test_extractor_ignores_empty_feed():
    extractor = _AnswerFieldExtractor()
    assert extractor.feed("") == ""


# ---- stream_answer ---------------------------------------------------------------


class _FakeAsyncStream:
    def __init__(self, events):
        self._events = list(events)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def close(self):
        self.closed = True


def _delta(text):
    return SimpleNamespace(type="response.output_text.delta", delta=text)


def _done(text):
    return SimpleNamespace(type="response.output_text.done", text=text)


class _FakeResponses:
    def __init__(self, stream):
        self._stream = stream

    async def create(self, **kwargs):
        return self._stream


class _FakeClient:
    def __init__(self, stream):
        self.responses = _FakeResponses(stream)


async def _collect(question="q", context="c"):
    items = []
    async for item in stream_answer(question, context):
        items.append(item)
    return items


def test_stream_answer_happy_path(monkeypatch):
    events = [_delta('{"'), _delta("answer"), _delta('":"'), _delta("hi"), _delta('","cited_labels":["S1"],"insufficient_evidence":false}')]
    fake_stream = _FakeAsyncStream(events + [_done('{"answer":"hi","cited_labels":["S1"],"insufficient_evidence":false}')])
    monkeypatch.setattr(streaming, "_async_client", _FakeClient(fake_stream))

    items = asyncio.run(_collect())

    deltas = [i for i in items if isinstance(i, AnswerDelta)]
    final = items[-1]
    assert "".join(d.text for d in deltas) == "hi"
    assert isinstance(final, GeneratedAnswer)
    assert final.answer == "hi"
    assert fake_stream.closed is True


def test_stream_answer_closes_stream_even_on_error(monkeypatch):
    class _RaisingStream(_FakeAsyncStream):
        async def __anext__(self):
            raise openai.APIConnectionError(request=None)

    fake_stream = _RaisingStream([])
    monkeypatch.setattr(streaming, "_async_client", _FakeClient(fake_stream))

    items = asyncio.run(_collect())

    assert len(items) == 1
    assert isinstance(items[0], GenerationUnavailableError)
    assert fake_stream.closed is True


def test_stream_answer_maps_timeout_error(monkeypatch):
    class _TimeoutStream(_FakeAsyncStream):
        async def __anext__(self):
            raise openai.APITimeoutError(request=None)

    fake_stream = _TimeoutStream([])
    monkeypatch.setattr(streaming, "_async_client", _FakeClient(fake_stream))

    items = asyncio.run(_collect())

    assert isinstance(items[-1], GenerationTimeoutError)


def test_stream_answer_no_final_text_is_generation_error(monkeypatch):
    fake_stream = _FakeAsyncStream([_delta('{"answer":"hi"')])  # never sends a "done" event
    monkeypatch.setattr(streaming, "_async_client", _FakeClient(fake_stream))

    items = asyncio.run(_collect())

    assert isinstance(items[-1], GenerationError)


def test_stream_answer_malformed_final_json_is_generation_error(monkeypatch):
    fake_stream = _FakeAsyncStream([_done("not json")])
    monkeypatch.setattr(streaming, "_async_client", _FakeClient(fake_stream))

    items = asyncio.run(_collect())

    assert isinstance(items[-1], GenerationError)
