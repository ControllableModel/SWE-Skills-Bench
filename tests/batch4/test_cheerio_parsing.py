"""Tests for the `cheerio-parsing` skill (variant ext4).

Skill task: add a product-card list extractor to the cheerio repo.

  * New file ``src/api/products.ts`` must export ``extractProducts(html)``.
  * ``extractProducts`` loads ``html`` with cheerio, selects every
    ``.product-card`` element, and returns one typed record per card in
    document order with keys:

        - ``name``  : trimmed text of descendant ``.title`` (``''`` if absent).
        - ``price`` : number parsed from descendant ``.price`` text by stripping
                      every character that is not a digit or a dot
                      (``null`` if no ``.price`` element; ``NaN`` if the price
                      text has no digits).
        - ``image`` : ``src`` attr of descendant ``<img>`` (``null`` if absent).
        - ``inStock``: ``false`` iff the card contains a ``.out-of-stock``
                       descendant, ``true`` otherwise.

  * New file ``src/api/products.spec.ts`` must contain deterministic cases.

The agent edits the cheerio repo at REPO_DIR. After it finishes, this file runs
with pytest. We verify behavior by:

  * L1 -- the deliverable files exist and are minimally well-formed (export the
    function, reference the required selectors / keys).
  * L2 -- DYNAMIC EXECUTION: we drop an INDEPENDENT vitest spec into the repo's
    own ``src/api`` directory so it imports the real, freshly-built
    ``extractProducts`` through ``./products.js``. Each assertion targets a
    concrete requirement (scoping per card, currency stripping, ``null`` vs
    ``NaN`` price, ``inStock`` toggling, image ``src``, empty input, document
    order). A naive implementation -- returning a fixed array, ignoring an
    input field, hardcoding ``inStock``, or leaking selectors across cards --
    fails these specs. We also run the variant's native acceptance command,
    ``npx vitest run src/api/products.spec.ts``.
"""

import json
import os
import subprocess

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not present
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cheerio"
API_DIR = os.path.join(REPO_DIR, "src", "api")
PRODUCTS_TS = os.path.join(API_DIR, "products.ts")
PRODUCTS_SPEC = os.path.join(API_DIR, "products.spec.ts")

# Name of the independent spec file we inject. Distinct from products.spec.ts so
# the repo's own spec is not clobbered and our run is isolated.
INJECTED_SPEC_NAME = "products_skillcheck.spec.ts"
INJECTED_SPEC_PATH = os.path.join(API_DIR, INJECTED_SPEC_NAME)


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node dependencies once before any native test runs."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    else:
        if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")):
            cmd = (
                ["npm", "ci", "--legacy-peer-deps"]
                if os.path.isfile(os.path.join(REPO_DIR, "package-lock.json"))
                else ["npm", "install", "--legacy-peer-deps"]
            )
            subprocess.run(
                cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=1800
            )
    yield
    # Best-effort cleanup of the injected spec.
    try:
        if os.path.isfile(INJECTED_SPEC_PATH):
            os.remove(INJECTED_SPEC_PATH)
    except OSError:
        pass


def _run_vitest(spec_relpath, timeout=600):
    """Run a single spec via vitest in JSON-reporter mode and parse the report.

    Returns a dict with keys: returncode, stdout, stderr, report (parsed JSON or
    None), and `assertions` (flattened list of {title, status, messages} dicts).
    """
    cmd = [
        "npx",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=json",
        # Disable typecheck for ad-hoc runs; our injected spec is runtime-only.
        "--typecheck.enabled=false",
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout
    )
    report = None
    out = proc.stdout
    start = out.find("{")
    end = out.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = out[start : end + 1]
        try:
            report = json.loads(candidate)
        except json.JSONDecodeError:
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        report = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
    assertions = []
    if report and isinstance(report.get("testResults"), list):
        for tr in report["testResults"]:
            for a in tr.get("assertionResults", []):
                assertions.append(
                    {
                        "title": a.get("title") or a.get("fullName") or "",
                        "fullName": a.get("fullName") or "",
                        "status": a.get("status"),
                        "messages": a.get("failureMessages") or [],
                    }
                )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "report": report,
        "assertions": assertions,
    }


# ---------------------------------------------------------------------------
# Injected independent spec content.
# ---------------------------------------------------------------------------
# Exercises extractProducts strictly through its public export. Each it(...)
# maps to a requirement and has a stable, greppable SKILLCHECK title so the
# Python layer can assert on individual outcomes (not just an aggregate pass),
# making partial / naive implementations detectable.
#
# Document fixture (built inline): two cards (Apple in stock $1.50, Pear out of
# stock $3) plus targeted single-card fixtures for each edge case.

_INJECTED_SPEC = r"""
import { describe, expect, it } from 'vitest';
import { extractProducts } from './products.js';

const TWO_CARDS = `
  <div class="catalog">
    <div class="product-card">
      <h2 class="title">  Apple  </h2>
      <span class="price">$1.50</span>
      <img src="apple.png" alt="apple">
    </div>
    <div class="product-card">
      <h2 class="title">Pear</h2>
      <span class="price">$3</span>
      <img src="pear.png">
      <span class="out-of-stock">Sold out</span>
    </div>
  </div>
`;

describe('extractProducts skillcheck', () => {
  it('SKILLCHECK returns one record per card in document order', () => {
    const out = extractProducts(TWO_CARDS);
    expect(Array.isArray(out)).toBe(true);
    expect(out.length).toBe(2);
    expect(out.map((r: any) => r.name)).toStrictEqual(['Apple', 'Pear']);
  });

  it('SKILLCHECK name is trimmed title text', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out[0].name).toBe('Apple');
    expect(out[1].name).toBe('Pear');
  });

  it('SKILLCHECK name empty string when title absent', () => {
    const out = extractProducts(
      '<div class="product-card"><span class="price">$2</span></div>',
    );
    expect(out.length).toBe(1);
    expect(out[0].name).toBe('');
  });

  it('SKILLCHECK price parses currency and decimal', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out[0].price).toBe(1.5);
    expect(out[1].price).toBe(3);
    expect(typeof out[0].price).toBe('number');
  });

  it('SKILLCHECK price strips thousands separators', () => {
    const out = extractProducts(
      '<div class="product-card"><span class="price">$1,299.50</span></div>',
    );
    expect(out[0].price).toBe(1299.5);
  });

  it('SKILLCHECK price is null when .price element absent', () => {
    const out = extractProducts(
      '<div class="product-card"><h2 class="title">NoPrice</h2></div>',
    );
    expect(out.length).toBe(1);
    expect(out[0].price).toBeNull();
  });

  it('SKILLCHECK price is NaN when .price has no digits', () => {
    const out = extractProducts(
      '<div class="product-card"><span class="price">Free!</span></div>',
    );
    expect(out.length).toBe(1);
    expect(Number.isNaN(out[0].price)).toBe(true);
    // NaN is distinct from null: ensure it was NOT collapsed to null.
    expect(out[0].price).not.toBeNull();
  });

  it('SKILLCHECK image is img src attribute', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out[0].image).toBe('apple.png');
    expect(out[1].image).toBe('pear.png');
  });

  it('SKILLCHECK image is null when no img', () => {
    const out = extractProducts(
      '<div class="product-card"><h2 class="title">NoImg</h2></div>',
    );
    expect(out[0].image).toBeNull();
  });

  it('SKILLCHECK image is null when img has no src', () => {
    const out = extractProducts(
      '<div class="product-card"><img alt="x"></div>',
    );
    expect(out[0].image).toBeNull();
  });

  it('SKILLCHECK inStock true by default', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out[0].inStock).toBe(true);
  });

  it('SKILLCHECK inStock false when out-of-stock descendant present', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out[1].inStock).toBe(false);
  });

  it('SKILLCHECK empty array when no product-card matches', () => {
    const out = extractProducts('<div class="other">nothing here</div>');
    expect(out).toStrictEqual([]);
  });

  it('SKILLCHECK lookups are scoped per card (no leakage)', () => {
    // Card A has only a title; card B has only a price. If scoping is wrong, A
    // would pick up B's price and/or B would pick up A's title.
    const html = `
      <div class="product-card"><h2 class="title">OnlyTitle</h2></div>
      <div class="product-card"><span class="price">$9.99</span></div>
    `;
    const out = extractProducts(html);
    expect(out.length).toBe(2);
    expect(out[0].name).toBe('OnlyTitle');
    expect(out[0].price).toBeNull();
    expect(out[1].name).toBe('');
    expect(out[1].price).toBe(9.99);
  });

  it('SKILLCHECK full record shape for the canonical two-card example', () => {
    const out = extractProducts(TWO_CARDS);
    expect(out).toStrictEqual([
      { name: 'Apple', price: 1.5, image: 'apple.png', inStock: true },
      { name: 'Pear', price: 3, image: 'pear.png', inStock: false },
    ]);
  });
});
"""


def _write_injected_spec():
    assert os.path.isdir(API_DIR), f"missing api dir: {API_DIR}"
    with open(INJECTED_SPEC_PATH, "w", encoding="utf-8") as fh:
        fh.write(_INJECTED_SPEC)


def _assert_titles_passed(result, required_substrings):
    """Assert each required title-substring exists and passed in vitest report."""
    if result["report"] is None:
        pytest.fail(
            "Could not parse vitest JSON report.\n"
            f"returncode={result['returncode']}\n"
            f"STDOUT(tail):\n{result['stdout'][-3000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
    by_title = {a["title"]: a for a in result["assertions"]}
    for sub in required_substrings:
        match = next((a for t, a in by_title.items() if sub in t), None)
        assert match is not None, (
            f"Expected a test titled containing {sub!r}, but none ran. "
            f"Ran titles: {sorted(by_title)}"
        )
        assert match["status"] == "passed", (
            f"Test {match['title']!r} did not pass (status={match['status']}). "
            f"Messages: {match['messages']}"
        )


# Cache for the single injected-spec run, shared across L2 tests.
_INJECTED_RESULT = {}


def _get_injected_result():
    if "result" not in _INJECTED_RESULT:
        _write_injected_spec()
        rel = os.path.join("src", "api", INJECTED_SPEC_NAME)
        _INJECTED_RESULT["result"] = _run_vitest(rel, timeout=600)
    return _INJECTED_RESULT["result"]


class TestCheerioParsing:
    REPO_DIR = "/workspace/cheerio"

    # ----------------------- L1: deliverables exist -----------------------

    def test_l1_products_source_exists(self):
        """L1: src/api/products.ts exists and exports extractProducts."""
        assert os.path.isfile(PRODUCTS_TS), f"missing {PRODUCTS_TS}"
        content = open(PRODUCTS_TS, encoding="utf-8").read()
        assert "extractProducts" in content, (
            "products.ts must define extractProducts"
        )
        assert "export" in content, "products.ts must export extractProducts"
        assert len(content) > 200, "products.ts unexpectedly small"

    def test_l1_products_source_references_selector_and_keys(self):
        """L1: products.ts references the required selector and record keys."""
        content = open(PRODUCTS_TS, encoding="utf-8").read()
        assert "product-card" in content, (
            "products.ts must select .product-card elements"
        )
        for key in ("name", "price", "image", "inStock"):
            assert key in content, f"products.ts must reference the '{key}' key"

    def test_l1_spec_exists_and_exercises_extractor(self):
        """L1: src/api/products.spec.ts exists and calls extractProducts."""
        assert os.path.isfile(PRODUCTS_SPEC), f"missing {PRODUCTS_SPEC}"
        content = open(PRODUCTS_SPEC, encoding="utf-8").read()
        assert "extractProducts" in content, (
            "products.spec.ts must exercise extractProducts(...)"
        )

    def test_l1_spec_covers_required_cases(self):
        """L1: products.spec.ts covers the required scenarios named in the doc."""
        content = open(PRODUCTS_SPEC, encoding="utf-8").read()
        for token in ("product-card", "price", "out-of-stock"):
            assert token in content, (
                f"products.spec.ts must cover '{token}' behavior"
            )

    # ----------------------- L2: dynamic execution -----------------------

    def test_l2_injected_spec_runs_clean(self):
        """L2: the injected independent spec compiles and runs (vitest exit 0).

        This is the gate: if extractProducts is missing, broken, or hardcoded,
        the behavioral assertions below fail and drive a non-zero exit code.
        """
        result = _get_injected_result()
        assert result["returncode"] == 0, (
            "Injected vitest spec failed.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )

    def test_l2_one_record_per_card_in_order(self):
        """L2: one record per .product-card, in document order."""
        _assert_titles_passed(
            _get_injected_result(),
            ["returns one record per card in document order"],
        )

    def test_l2_name_trimmed_and_empty(self):
        """L2: name is trimmed title text, '' when title absent."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "name is trimmed title text",
                "name empty string when title absent",
            ],
        )

    def test_l2_price_currency_and_decimal(self):
        """L2: price strips currency symbols / separators to a number."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "price parses currency and decimal",
                "price strips thousands separators",
            ],
        )

    def test_l2_price_null_vs_nan(self):
        """L2: price is null when .price absent, NaN when it has no digits."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "price is null when .price element absent",
                "price is NaN when .price has no digits",
            ],
        )

    def test_l2_image_src_and_nulls(self):
        """L2: image is the img src, null when no img or no src attribute."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "image is img src attribute",
                "image is null when no img",
                "image is null when img has no src",
            ],
        )

    def test_l2_instock_toggles_on_out_of_stock(self):
        """L2: inStock defaults true, false when .out-of-stock descendant present."""
        _assert_titles_passed(
            _get_injected_result(),
            [
                "inStock true by default",
                "inStock false when out-of-stock descendant present",
            ],
        )

    def test_l2_empty_input_yields_empty_array(self):
        """L2: no .product-card matches yields []."""
        _assert_titles_passed(
            _get_injected_result(),
            ["empty array when no product-card matches"],
        )

    def test_l2_per_card_scoping(self):
        """L2: lookups are scoped per card; no selector leakage across cards."""
        _assert_titles_passed(
            _get_injected_result(),
            ["lookups are scoped per card"],
        )

    def test_l2_canonical_record_shape(self):
        """L2: the full canonical two-card example matches exactly."""
        _assert_titles_passed(
            _get_injected_result(),
            ["full record shape for the canonical two-card example"],
        )

    def test_l2_native_acceptance_command_passes(self):
        """L2: the doc's native command `npx vitest run src/api/products.spec.ts`."""
        rel = os.path.join("src", "api", "products.spec.ts")
        assert os.path.isfile(PRODUCTS_SPEC), f"missing {PRODUCTS_SPEC}"
        result = _run_vitest(rel, timeout=600)
        assert result["returncode"] == 0, (
            "The agent's products.spec.ts must pass under `vitest run`.\n"
            f"STDOUT(tail):\n{result['stdout'][-4000:]}\n"
            f"STDERR(tail):\n{result['stderr'][-2000:]}"
        )
