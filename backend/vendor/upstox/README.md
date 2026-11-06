# Upstox V3 feed schema

Official source downloaded 2026-11-06:
https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto

SHA-256: `3e1c939dce2c83a3fef91405c5ca268dfa089aae973319f56685f12a5afcf612`.
The published schema is unmodified. Its declarations match the official SDK schema
at commit `d88a12ef5738a4c8d71f3b88eb7b79a359277c9d`; the SDK additionally has explanatory inline comments:
https://github.com/upstox/upstox-python/blob/d88a12ef5738a4c8d71f3b88eb7b79a359277c9d/examples/websocket/market_data/v3/MarketDataFeedV3.proto

Upstox SDK MIT attribution is preserved in SDK-LICENSE (official LICENSE.txt).
Python/stub files are generated, never hand-edited. Generated code uses protoc Python
6.31.1 via grpcio-tools1.76.0. Runtime is locked in uv.lock; grpcio-tools is an isolated
build tool, not an application dependency.

Regenerate with:

```sh
uvx --from grpcio-tools==1.76.0 python -m grpc_tools.protoc -I backend/vendor/upstox --python_out=backend/vendor/upstox --pyi_out=backend/vendor/upstox backend/vendor/upstox/MarketDataFeed.proto
```

Review upstream changes and update the schema hash test deliberately. Generated files
are excluded from Ruff; only their unparameterized Mapping annotations receive a
targeted mypy exception. Application code keeps strict type checks.
