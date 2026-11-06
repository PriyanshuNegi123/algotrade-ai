"""Bounded public BOD download/decompression and streaming JSON-array validation."""

import codecs
import hashlib
import json
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

SOURCE_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
MAX_COMPRESSED = 16 * 1024 * 1024
MAX_DECODED = 128 * 1024 * 1024
MAX_RECORD_BYTES = 65_536
MAX_RECORDS = 300_000


class InstrumentError(Exception):
    """Safe local reason code; never interpolate a remote response or record."""


@dataclass(frozen=True)
class Download:
    body: bytes
    modified_at: datetime
    retrieved_at: datetime

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


class InstrumentSource:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def download(self) -> Download:
        deadline = time.monotonic() + 45
        try:
            with httpx.Client(
                transport=self._transport, timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "GET", SOURCE_URL, headers={"Accept-Encoding": "identity"}
                ) as response:
                    if response.status_code != 200:
                        raise InstrumentError("SOURCE_UNAVAILABLE")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise InstrumentError("UNSUPPORTED_ENCODING")
                    published = parsedate_to_datetime(response.headers.get("last-modified", ""))
                    if published.tzinfo is None:
                        raise InstrumentError("UNVERIFIED_PUBLICATION_TIME")
                    published = published.astimezone(UTC)
                    validate_publication(published, datetime.now(UTC))
                    body = bytearray()
                    for chunk in response.iter_raw(chunk_size=65_536):
                        if time.monotonic() > deadline:
                            raise InstrumentError("SOURCE_TIMEOUT")
                        body.extend(chunk)
                        if len(body) > MAX_COMPRESSED:
                            raise InstrumentError("COMPRESSED_LIMIT_EXCEEDED")
            retrieved = datetime.now(UTC)
            validate_publication(published, retrieved)
            return Download(bytes(body), published, retrieved)
        except httpx.HTTPError:
            raise InstrumentError("SOURCE_UNAVAILABLE") from None
        except (ValueError, TypeError, OverflowError):
            raise InstrumentError("UNVERIFIED_PUBLICATION_TIME") from None


def validate_publication(published: datetime, retrieved: datetime) -> None:
    if published.tzinfo is None or retrieved.tzinfo is None:
        raise InstrumentError("UNVERIFIED_PUBLICATION_TIME")
    age = retrieved - published
    if age < -timedelta(minutes=5):
        raise InstrumentError("FUTURE_PUBLICATION_TIME")
    if age > timedelta(hours=36):
        raise InstrumentError("STALE_SOURCE")


def decoded_chunks(body: bytes) -> Iterator[bytes]:
    if not body or len(body) > MAX_COMPRESSED:
        raise InstrumentError("COMPRESSED_LIMIT_EXCEEDED")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    total = 0
    try:
        for offset in range(0, len(body), 65_536):
            pending = body[offset : offset + 65_536]
            while pending:
                chunk = decoder.decompress(pending, 65_536)
                pending = decoder.unconsumed_tail
                total += len(chunk)
                if total > MAX_DECODED:
                    raise InstrumentError("DECODED_LIMIT_EXCEEDED")
                if chunk:
                    yield chunk
                if decoder.unused_data:
                    raise InstrumentError("TRAILING_GZIP_DATA")
        if not decoder.eof:
            raise InstrumentError("TRUNCATED_GZIP")
    except zlib.error:
        raise InstrumentError("INVALID_GZIP") from None


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise InstrumentError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise InstrumentError("INVALID_JSON_NUMBER")


def json_records(chunks: Iterator[bytes]) -> Iterator[dict[str, Any]]:
    """Hold at most one bounded partial record, rather than a complete decoded master."""
    decoder = json.JSONDecoder(
        parse_float=Decimal, object_pairs_hook=_pairs, parse_constant=_invalid_constant
    )
    utf8 = codecs.getincrementaldecoder("utf-8")()
    buffer, position, state, count = "", 0, "start", 0
    try:
        for chunk in _with_end(chunks):
            final = chunk is None
            buffer = buffer[position:] + utf8.decode(chunk or b"", final=final)
            position = 0
            while True:
                while position < len(buffer) and buffer[position] in " \r\n\t":
                    position += 1
                if position == len(buffer):
                    break
                symbol = buffer[position]
                if state == "closed":
                    raise InstrumentError("TRAILING_JSON_DATA")
                if state == "start":
                    if symbol != "[":
                        raise InstrumentError("INVALID_JSON_ARRAY")
                    position += 1
                    state = "first"
                    continue
                if state in {"first", "value"}:
                    if symbol == "]" and state == "first":
                        position += 1
                        state = "closed"
                        continue
                    try:
                        value, end = decoder.raw_decode(buffer, position)
                    except json.JSONDecodeError:
                        if final:
                            raise InstrumentError("INVALID_JSON") from None
                        break
                    if len(
                        buffer[position:end].encode("utf-8")
                    ) > MAX_RECORD_BYTES or not isinstance(value, dict):
                        raise InstrumentError("INVALID_OR_OVERSIZED_RECORD")
                    count += 1
                    if count > MAX_RECORDS:
                        raise InstrumentError("RECORD_LIMIT_EXCEEDED")
                    position, state = end, "separator"
                    yield value
                    continue
                if symbol == ",":
                    position += 1
                    state = "value"
                elif symbol == "]":
                    position += 1
                    state = "closed"
                else:
                    raise InstrumentError("INVALID_JSON_SEPARATOR")
            if len(buffer[position:].encode("utf-8")) > MAX_RECORD_BYTES:
                raise InstrumentError("INVALID_OR_OVERSIZED_RECORD")
        if state != "closed":
            raise InstrumentError("INCOMPLETE_JSON_ARRAY")
    except (UnicodeError, RecursionError, ValueError):
        raise InstrumentError("INVALID_JSON") from None


def _with_end(chunks: Iterator[bytes]) -> Iterator[bytes | None]:
    yield from chunks
    yield None
