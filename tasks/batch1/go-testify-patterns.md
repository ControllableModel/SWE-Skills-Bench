# Task: Add a Deterministic Chunk-Planning Layer to the Consul State Backend

## Background

The Consul remote-state backend in this repository (`internal/backend/remote-state/consul`) stores a Terraform state payload in Consul's KV store using several layouts depending on payload size and gzip settings: a single entry, or a "link" record plus a series of fixed-size chunks. Today the size-based decision and chunk slicing are entangled with live Consul network calls inside `RemoteClient.Put`, which makes that logic impossible to test without a running Consul server. This task extracts the layout decision into a pure, in-memory layer so it can be exercised deterministically.

## Files to Create/Modify

- `internal/backend/remote-state/consul/chunkplan.go` (new) — a self-contained, network-free implementation of the layout planner and the stored-value classifier.
- `internal/backend/remote-state/consul/chunkplan_test.go` (new) — the deterministic test for the new layer.

The new code must live in the existing `consul` package and must not call Consul, the network, the filesystem, the clock, or any randomness.

## Requirements

### `PlanStorage`

Add an exported function:

```go
func PlanStorage(basePath string, payload []byte, limit int) (StoragePlan, error)
```

It computes — without performing any I/O — how a payload would be laid out under a chunk-size `limit` (in bytes), and returns a `StoragePlan` describing the result. The caller passes the already-final bytes (i.e. gzip, if any, has already been applied) plus the key prefix `basePath` (for example `"tfstate/my_project"`).

`StoragePlan` must expose at least:

- whether the payload is stored as a single KV entry or split into chunks,
- the ordered list of chunk byte-slices when chunked (and an empty/zero-length list otherwise),
- the ordered list of KV key paths under which those chunks would be written,
- the JSON "link" record bytes that would be written at `basePath` when chunked.

Behavior:

- **Single-entry decision.** If `len(payload) <= limit`, the plan is single-entry: no chunks, no chunk paths, no link record.
- **Chunked decision.** If `len(payload) > limit`, the plan is chunked. The payload is divided into consecutive pieces of exactly `limit` bytes each, with a final shorter piece holding the remainder when the length is not an exact multiple of `limit`. The concatenation of all chunk byte-slices, in order, must equal the original `payload` exactly. No chunk may be empty, and no chunk except possibly the last may have a length other than `limit`.
- **Chunk key paths.** When chunked, each chunk `i` (0-based) is assigned a key path of the form `<base>/tfstate.<id>/<i>`, where `<base>` is `basePath` with any trailing `/` removed and `<id>` is the lowercase hex MD5 of the original `payload`. The number of chunk paths must equal the number of chunks and the paths must be in chunk order.
- **Link record.** When chunked, the link record is a JSON object containing the key `current-hash` (the same lowercase hex MD5 `<id>` used in the paths) and the key `chunks` (the ordered list of chunk key paths, exactly as above). The link record must be valid JSON, and parsing it back must recover the identical hash string and chunk-path list. The link record must **not** be produced for single-entry plans.

Edge cases and constraints:

- A `limit <= 0` is invalid and must return a non-nil error (and a zero-value plan); it must not panic.
- An empty payload (`len(payload) == 0`) with a positive `limit` is a valid single-entry plan (it satisfies `len(payload) <= limit`).
- A payload whose length is exactly `limit` is single-entry, not chunked.
- A payload one byte longer than `limit` produces exactly two chunks (`limit` bytes, then 1 byte).

### `ClassifyStoredValue`

Add an exported function:

```go
func ClassifyStoredValue(value []byte) StoredKind
```

`StoredKind` is an enumeration that distinguishes how a value found at `basePath` should be interpreted, mirroring the layouts above. It classifies the raw bytes already present at the key:

- **Gzip single-entry.** A value whose first byte is `0x1f` (the gzip magic prefix) is classified as the gzip single-entry kind. Such a value is never treated as a link record even if its remaining bytes happen to resemble JSON.
- **Chunked link record.** A value that is a JSON object containing a `current-hash` key is classified as the chunked-link kind.
- **Plain single-entry.** A value that is valid JSON but has no `current-hash` key is classified as the plain single-entry kind.
- **Plain single-entry (non-JSON).** A value that is neither gzip-prefixed nor valid JSON is also classified as plain single-entry (it is treated as opaque state bytes).
- An empty value (`len(value) == 0`) must be classified as plain single-entry and must not panic.

The three or more `StoredKind` values must be distinct exported constants so a caller (and a test) can compare against them by name.

### General

- The MD5 hash and hex encoding used by `PlanStorage` must be consistent between the chunk key paths and the `current-hash` field of the link record (same payload ⇒ same id in both places).
- The implementation must be deterministic: identical inputs always produce identical `StoragePlan` and `StoredKind` results.

## Acceptance Criteria

The new test file `internal/backend/remote-state/consul/chunkplan_test.go` must drive the new code through a `github.com/stretchr/testify/suite` test suite (the project already depends on `github.com/stretchr/testify`) and must cover, at minimum:

- a single-entry payload (`len <= limit`) yielding no chunks, no chunk paths, and no link record;
- a payload exactly equal to `limit` staying single-entry;
- a payload one byte over `limit` producing exactly two chunks whose concatenation equals the original payload, with chunk key paths in order and a count matching the chunk count;
- a multi-chunk payload where the reconstructed bytes (chunks concatenated in order) equal the original payload;
- the link record parsing back to the same `current-hash` value and the same ordered chunk-path list that appear in the plan;
- `limit <= 0` returning a non-nil error without panicking;
- `ClassifyStoredValue` returning the correct distinct kind for: a gzip-prefixed value (first byte `0x1f`), a JSON object with `current-hash`, a JSON object without `current-hash`, a non-JSON opaque value, and an empty value.

The following command, run from the repository root, must pass:

```
cd internal/backend/remote-state/consul && go test -run TestStoragePlanSuite -v ./
```

(The suite launcher function must be named `TestStoragePlanSuite` and registered via `suite.Run`.)
