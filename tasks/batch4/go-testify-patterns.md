# Task: Add an IPv4 CIDR Membership Classifier

## Background

The `internal/ipaddr` package is a vendored, self-contained IP-parsing library used inside Terraform. It already knows how to parse IPv4 addresses and CIDR masks, but offers no helper to classify whether a single address falls inside a given IPv4 CIDR block. This task adds a deterministic classifier built on the package's existing parsing.

## Files to Create/Modify

- `internal/ipaddr/cidrmatch.go` (new) — a self-contained classifier in package `ipaddr`.
- `internal/ipaddr/cidrmatch_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `ipaddr` package and must not perform any network/DNS calls, I/O, or randomness. It may use the package's existing IPv4/CIDR parsing.

## Requirements

### `IPv4InCIDR`

Add an exported function:

```go
func IPv4InCIDR(ip string, cidr string) (bool, error)
```

It reports whether dotted-quad IPv4 address `ip` is contained within IPv4 `cidr` (e.g. `"10.0.0.0/8"`).

Behavior and constraints:

- Returns `(true, nil)` when `ip` is inside the block, `(false, nil)` when it is a syntactically valid IPv4 address outside the block.
- Membership is decided by masking: `ip` is inside `cidr` iff the high `prefix`-bits of `ip` equal the network address of `cidr`.
- The network address itself and the broadcast/last address of the block are both considered **inside** the block.
- A `/0` prefix contains every valid IPv4 address; a `/32` prefix contains only the single exact address.
- Invalid inputs return a non-nil error and `false` (never a panic): an `ip` that is not a valid dotted-quad IPv4; a `cidr` lacking a `/`; a prefix length outside `0..32`; or any non-numeric / out-of-range octet.
- The function must be IPv4-only: an IPv6 address or an IPv6 CIDR is treated as invalid input (non-nil error).

### Expected Functionality

- `IPv4InCIDR("10.1.2.3", "10.0.0.0/8")` -> `(true, nil)`.
- `IPv4InCIDR("11.0.0.1", "10.0.0.0/8")` -> `(false, nil)`.
- `IPv4InCIDR("192.168.1.255", "192.168.1.0/24")` -> `(true, nil)` (last address is inside).
- `IPv4InCIDR("anything", "0.0.0.0/0")` for any valid IPv4 -> `(true, nil)`.
- `IPv4InCIDR("256.0.0.1", "10.0.0.0/8")` -> error.
- `IPv4InCIDR("10.0.0.1", "10.0.0.0/33")` -> error.

## Acceptance Criteria

The new test file `internal/ipaddr/cidrmatch_test.go` must exercise `IPv4InCIDR` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- an address inside and an address outside a `/8` and a `/24` block;
- the network address and the last (broadcast) address both classified as inside;
- `/0` containing any valid IPv4 and `/32` containing only the exact address;
- invalid `ip` (bad octet / out of range), invalid `cidr` (missing `/`, prefix out of `0..32`), and an IPv6 input — each returning a non-nil error and `false`, without panicking.

The following command, run from the repository root, must pass:

```
go test ./internal/ipaddr/ -run TestIPv4InCIDR -v
```
