import gzip
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from backend.app.instruments import source
from backend.app.instruments.source import (
    InstrumentError,
    InstrumentSource,
    decoded_chunks,
    json_records,
)


def source_response(content, **headers):
    return httpx.Response(
        200,
        stream=httpx.ByteStream(content),
        headers={
            "Last-Modified": format_datetime(datetime.now(UTC) - timedelta(minutes=1), usegmt=True),
            **headers,
        },
    )


def test_fixed_public_source_without_credentials():
    body = gzip.compress(b'[{"segment":"NSE_INDEX"}]')

    def handler(request):
        assert str(request.url) == source.SOURCE_URL and request.method == "GET"
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        return source_response(body)

    result = InstrumentSource(httpx.MockTransport(handler)).download()
    assert result.body == body and result.retrieved_at.tzinfo is not None
    assert len(result.sha256) == 64


@pytest.mark.parametrize(
    "headers,code",
    [
        ({"Last-Modified": "bad"}, "UNVERIFIED_PUBLICATION_TIME"),
        (
            {"Last-Modified": format_datetime(datetime.now(UTC) - timedelta(days=3), usegmt=True)},
            "STALE_SOURCE",
        ),
        (
            {"Last-Modified": format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)},
            "FUTURE_PUBLICATION_TIME",
        ),
        ({"Content-Encoding": "gzip"}, "UNSUPPORTED_ENCODING"),
    ],
)
def test_source_headers_fail_closed(headers, code):
    client = InstrumentSource(httpx.MockTransport(lambda _: source_response(b"ignored", **headers)))
    with pytest.raises(InstrumentError, match=code):
        client.download()


def test_redirect_is_not_followed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    with pytest.raises(InstrumentError, match="SOURCE_UNAVAILABLE"):
        InstrumentSource(httpx.MockTransport(handler)).download()
    assert len(calls) == 1


def test_compressed_download_limit(monkeypatch):
    monkeypatch.setattr(source, "MAX_COMPRESSED", 10)
    with pytest.raises(InstrumentError, match="COMPRESSED_LIMIT"):
        InstrumentSource(httpx.MockTransport(lambda _: source_response(b"x" * 11))).download()


def test_decompression_bomb_limit(monkeypatch):
    monkeypatch.setattr(source, "MAX_DECODED", 10)
    with pytest.raises(InstrumentError, match="DECODED_LIMIT"):
        list(decoded_chunks(gzip.compress(b"a" * 100_000)))


@pytest.mark.parametrize(
    "blob",
    [
        b"invalid",
        gzip.compress(b"[]")[:-3],
        gzip.compress(b"[]") + b"extra",
        gzip.compress(b"[]") * 2,
    ],
)
def test_bad_truncated_or_concatenated_gzip_rejected(blob):
    with pytest.raises(InstrumentError):
        list(decoded_chunks(blob))


def test_json_records_across_every_utf8_boundary():
    body = json.dumps(
        [{"name": "निफ्टी", "number": 1.25}, {"name": "second"}], ensure_ascii=False
    ).encode()
    records = list(json_records(iter(bytes([value]) for value in body)))
    assert records[0]["name"] == "निफ्टी" and str(records[0]["number"]) == "1.25"
    assert len(records) == 2


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[1]",
        b'[{"a":1},]',
        b'[{"a":1}] trailing',
        b'[{"a":1}',
        b'[{"a":1,"a":2}]',
        b'[{"a":NaN}]',
        b"[{} {}]",
        b'["\xff"]',
    ],
)
def test_invalid_json_shapes_rejected(body):
    with pytest.raises(InstrumentError):
        list(json_records(iter([body])))


def test_streamed_record_count_and_size_limits(monkeypatch):
    monkeypatch.setattr(source, "MAX_RECORDS", 1)
    with pytest.raises(InstrumentError, match="RECORD_LIMIT"):
        list(json_records(iter([b"[{},{}]"])))
    monkeypatch.setattr(source, "MAX_RECORD_BYTES", 10)
    with pytest.raises(InstrumentError, match="OVERSIZED_RECORD"):
        list(json_records(iter([b'[{"very-long-field":1}]'])))
