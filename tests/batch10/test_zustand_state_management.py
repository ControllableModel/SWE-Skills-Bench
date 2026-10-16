"""Benchmark tests for the `zustand-state-management` skill (variant ext10).

Verifies the agent's implementation of a self-contained tic-tac-toe GAME store
module built on top of zustand's public vanilla `createStore` + `redux`
middleware API.

Source of truth: tasks/ext10/zustand-state-management.md. The task asks the
agent to create:
  - examples/game-store/gameStore.ts  (pure `gameReducer` + factory
    `createGameStore` returning getState/setState/subscribe/dispatch + types)
  - tests/gameStore.test.ts           (the agent's own Vitest suite, >=10 cases)

L1 checks: the deliverable files exist, are minimally well-formed, declare the
required exported symbols, and the agent's own suite passes via
`pnpm vitest run tests/gameStore.test.ts` with at least 10 cases.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write INDEPENDENT Vitest driver files into REPO_DIR/tests/
that import the agent's `createGameStore` factory and `gameReducer` directly and
exercise the real runtime behavior:
  - play places a mark and toggles currentPlayer; dispatch routes through reducer
  - out-of-range index rejected; occupied cell rejected (state unchanged)
  - row / column / diagonal win each set status='won', winner, freeze player
  - a no-winner full board sets status='draw'
  - further play after won/draw is a no-op until reset
  - reset restores the canonical initial state
  - gameReducer purity: inputs (state object AND board array) are never mutated,
    for both accepted and rejected actions, and equal inputs give equal output

A naive / hardcoded / "looks related" implementation (e.g. one that mutates the
board in place, ignores occupancy, never detects wins, or advances the player
after a win) fails these driver tests.

Native acceptance command driven by L2: `pnpm vitest run <driver>` from
REPO_DIR, mirroring the task's `pnpm vitest run tests/gameStore.test.ts`.
"""

import os
import re
import shutil
import subprocess
import uuid

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper is present at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/zustand"
GAME_STORE = os.path.join(REPO_DIR, "examples", "game-store", "gameStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "gameStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Unique tag avoids clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_game_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the game store module.
_IMPORT = "../examples/game-store/gameStore"


def _pnpm_available():
    return shutil.which("pnpm") is not None


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort install of node deps before running native vitest."""
    if ensure_npm_dependencies is not None:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            if _pnpm_available():
                subprocess.run(
                    ["pnpm", "install", "--frozen-lockfile=false"],
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` (or npx fallback) from REPO_DIR."""
    if _pnpm_available():
        cmd = ["pnpm", "vitest", "run", rel_file, "--reporter=verbose"]
    else:
        cmd = ["npx", "vitest", "run", rel_file, "--reporter=verbose"]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(body):
    """Write an independent vitest driver file under tests/ and return rel name."""
    os.makedirs(os.path.dirname(DRIVER_PATH), exist_ok=True)
    with open(DRIVER_PATH, "w") as fh:
        fh.write(body)
    return _DRIVER_BASENAME


def _cleanup_driver():
    try:
        if os.path.exists(DRIVER_PATH):
            os.remove(DRIVER_PATH)
    except OSError:
        pass


def _run_driver(body):
    """Write a driver, run it, clean up, return CompletedProcess."""
    rel = _write_driver(body)
    try:
        return _run_vitest(rel)
    finally:
        _cleanup_driver()


def _assert_passed(proc, scenario):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"vitest driver for '{scenario}' failed (rc={proc.returncode}).\n"
        f"{combined[-4000:]}"
    )


# A small TS preamble reused by drivers: helpers to import both the factory and
# the reducer, build the canonical initial state, and snapshot the board.
_PRELUDE = f"""
import {{ describe, it, expect }} from 'vitest'
import * as GS from '{_IMPORT}'

const createGameStore = (GS as any).createGameStore
const gameReducer = (GS as any).gameReducer

function initialState() {{
  // Derive an empty initial state from a fresh store so we follow the
  // implementation's own shape exactly.
  return createGameStore().getState()
}}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_game_store_module_exists(self):
        """L1: examples/game-store/gameStore.ts exists and is non-trivial."""
        assert os.path.isfile(GAME_STORE), f"missing {GAME_STORE}"
        size = os.path.getsize(GAME_STORE)
        assert size > 200, f"gameStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_required_symbols(self):
        """L1: module declares exported `createGameStore` and `gameReducer`."""
        with open(GAME_STORE) as fh:
            src = fh.read()
        assert re.search(r"\bcreateGameStore\b", src), (
            "createGameStore not found in gameStore.ts"
        )
        assert re.search(r"\bgameReducer\b", src), (
            "gameReducer not found in gameStore.ts"
        )
        # Must export both (named exports per acceptance criteria).
        assert re.search(r"export\b", src), "no exports in gameStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes_with_enough_cases(self):
        """L1/L2: agent's `tests/gameStore.test.ts` passes with >=10 cases."""
        proc = _run_vitest("tests/gameStore.test.ts")
        _assert_passed(proc, "agent gameStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_initial_state_shape(self):
        """L2: a fresh store starts empty, player X, status playing, no winner."""
        body = _PRELUDE + """
describe('bench-initial', () => {
  it('store starts in the canonical initial state', () => {
    const s = createGameStore().getState()
    expect(Array.isArray(s.board)).toBe(true)
    expect(s.board.length).toBe(9)
    expect(s.board.every((c: any) => c === null)).toBe(true)
    expect(s.currentPlayer).toBe('X')
    expect(s.status).toBe('playing')
    expect(s.winner).toBe(null)
    // store exposes the vanilla handles + dispatch
    const store = createGameStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    expect(typeof store.dispatch).toBe('function')
  })
})
"""
        _assert_passed(_run_driver(body), "initial state shape")

    def test_play_places_mark_and_toggles_player(self):
        """L2: dispatch play sets the cell to currentPlayer and toggles player."""
        body = _PRELUDE + """
describe('bench-play', () => {
  it('play places the mark and advances the player via dispatch', () => {
    const store = createGameStore()
    store.dispatch({ type: 'play', index: 4 })
    let s = store.getState()
    expect(s.board[4]).toBe('X')
    expect(s.board.filter((c: any) => c !== null).length).toBe(1)
    expect(s.currentPlayer).toBe('O')
    expect(s.status).toBe('playing')
    store.dispatch({ type: 'play', index: 0 })
    s = store.getState()
    expect(s.board[0]).toBe('O')
    expect(s.currentPlayer).toBe('X')
    expect(s.board.filter((c: any) => c !== null).length).toBe(2)
  })

  it('gameReducer drives the same transition as dispatch', () => {
    const init = initialState()
    const next = gameReducer(init, { type: 'play', index: 2 })
    expect(next.board[2]).toBe('X')
    expect(next.currentPlayer).toBe('O')
    // dispatch must route through the reducer: getState reflects it
    const store = createGameStore()
    store.dispatch({ type: 'play', index: 2 })
    expect(store.getState().board[2]).toBe('X')
    expect(store.getState().currentPlayer).toBe('O')
  })
})
"""
        _assert_passed(_run_driver(body), "play places mark + toggles")

    def test_out_of_range_index_rejected(self):
        """L2: play with index outside 0..8 leaves the state unchanged."""
        body = _PRELUDE + """
describe('bench-oob', () => {
  it('rejects out-of-range indices without mutation', () => {
    const init = initialState()
    for (const bad of [-1, 9, 100, 3.5, NaN]) {
      const next = gameReducer(init, { type: 'play', index: bad })
      expect(next.board.every((c: any) => c === null)).toBe(true)
      expect(next.currentPlayer).toBe('X')
      expect(next.status).toBe('playing')
    }
    const store = createGameStore()
    store.dispatch({ type: 'play', index: 9 })
    const s = store.getState()
    expect(s.board.every((c: any) => c === null)).toBe(true)
    expect(s.currentPlayer).toBe('X')
  })
})
"""
        _assert_passed(_run_driver(body), "out-of-range index rejected")

    def test_occupied_cell_rejected(self):
        """L2: playing into an occupied cell is rejected (no change, no toggle)."""
        body = _PRELUDE + """
describe('bench-occupied', () => {
  it('rejects a play into an already-occupied cell', () => {
    const store = createGameStore()
    store.dispatch({ type: 'play', index: 4 })   // X at 4
    const before = store.getState()
    expect(before.board[4]).toBe('X')
    expect(before.currentPlayer).toBe('O')
    store.dispatch({ type: 'play', index: 4 })   // O tries same cell
    const after = store.getState()
    // still X (occupant unchanged), player NOT advanced, count unchanged
    expect(after.board[4]).toBe('X')
    expect(after.currentPlayer).toBe('O')
    expect(after.board.filter((c: any) => c !== null).length).toBe(1)
  })
})
"""
        _assert_passed(_run_driver(body), "occupied cell rejected")

    def test_row_win(self):
        """L2: completing the top row makes X the winner; player not advanced."""
        body = _PRELUDE + """
describe('bench-row-win', () => {
  it('top row of X sets status won + winner X and freezes player', () => {
    const store = createGameStore()
    // X:0  O:3  X:1  O:4  X:2  -> X wins row 0,1,2
    for (const i of [0, 3, 1, 4, 2]) store.dispatch({ type: 'play', index: i })
    const s = store.getState()
    expect(s.status).toBe('won')
    expect(s.winner).toBe('X')
    expect(s.board[0]).toBe('X')
    expect(s.board[1]).toBe('X')
    expect(s.board[2]).toBe('X')
    // currentPlayer was NOT advanced on the winning move (stays X)
    expect(s.currentPlayer).toBe('X')
  })
})
"""
        _assert_passed(_run_driver(body), "row win")

    def test_column_win(self):
        """L2: completing a column makes the mark the winner with status won."""
        body = _PRELUDE + """
describe('bench-col-win', () => {
  it('left column of X sets status won + winner X', () => {
    const store = createGameStore()
    // X:0 O:1 X:3 O:2 X:6  -> X wins column 0,3,6
    for (const i of [0, 1, 3, 2, 6]) store.dispatch({ type: 'play', index: i })
    const s = store.getState()
    expect(s.status).toBe('won')
    expect(s.winner).toBe('X')
    expect(s.board[0]).toBe('X')
    expect(s.board[3]).toBe('X')
    expect(s.board[6]).toBe('X')
  })
})
"""
        _assert_passed(_run_driver(body), "column win")

    def test_diagonal_win(self):
        """L2: completing a diagonal makes the mark the winner with status won."""
        body = _PRELUDE + """
describe('bench-diag-win', () => {
  it('main diagonal of X sets status won + winner X', () => {
    const store = createGameStore()
    // X:0 O:1 X:4 O:2 X:8  -> X wins diagonal 0,4,8
    for (const i of [0, 1, 4, 2, 8]) store.dispatch({ type: 'play', index: i })
    const s = store.getState()
    expect(s.status).toBe('won')
    expect(s.winner).toBe('X')
    expect(s.board[0]).toBe('X')
    expect(s.board[4]).toBe('X')
    expect(s.board[8]).toBe('X')
  })

  it('anti-diagonal of O sets status won + winner O', () => {
    const store = createGameStore()
    // X:0 O:2 X:1 O:4 X:8 O:6  -> O wins anti-diagonal 2,4,6
    for (const i of [0, 2, 1, 4, 8, 6]) store.dispatch({ type: 'play', index: i })
    const s = store.getState()
    expect(s.status).toBe('won')
    expect(s.winner).toBe('O')
  })
})
"""
        _assert_passed(_run_driver(body), "diagonal win")

    def test_no_op_after_win(self):
        """L2: once won, further play actions are no-ops until reset."""
        body = _PRELUDE + """
describe('bench-noop-after-win', () => {
  it('play after a win does nothing', () => {
    const store = createGameStore()
    for (const i of [0, 3, 1, 4, 2]) store.dispatch({ type: 'play', index: i })
    const won = store.getState()
    expect(won.status).toBe('won')
    const boardSnapshot = won.board.slice()
    // remaining empty cells: 5,6,7,8 -> try to play one
    store.dispatch({ type: 'play', index: 5 })
    const after = store.getState()
    expect(after.status).toBe('won')
    expect(after.winner).toBe('X')
    expect(after.board).toEqual(boardSnapshot)
    expect(after.board[5]).toBe(null)
  })
})
"""
        _assert_passed(_run_driver(body), "no-op after win")

    def test_draw_detection(self):
        """L2: a full board with no line completed sets status draw, winner null."""
        body = _PRELUDE + """
describe('bench-draw', () => {
  it('a full no-winner board becomes a draw', () => {
    const store = createGameStore()
    // Classic draw layout. Sequence of moves (alternating X/O) ending full:
    // board target:
    //  X O X
    //  X O O
    //  O X X
    // move order chosen so each placement is legal & no early win:
    // X:0 O:1 X:2 O:4 X:3 O:5 X:7 O:6 X:8
    for (const i of [0, 1, 2, 4, 3, 5, 7, 6, 8]) {
      store.dispatch({ type: 'play', index: i })
    }
    const s = store.getState()
    expect(s.board.every((c: any) => c !== null)).toBe(true)
    expect(s.status).toBe('draw')
    expect(s.winner).toBe(null)
    // play after draw is a no-op
    const snap = s.board.slice()
    store.dispatch({ type: 'play', index: 0 })
    expect(store.getState().board).toEqual(snap)
    expect(store.getState().status).toBe('draw')
  })
})
"""
        _assert_passed(_run_driver(body), "draw detection")

    def test_reset_restores_initial(self):
        """L2: reset returns to the canonical empty initial state."""
        body = _PRELUDE + """
describe('bench-reset', () => {
  it('reset restores empty board, player X, playing, no winner', () => {
    const store = createGameStore()
    for (const i of [0, 3, 1, 4, 2]) store.dispatch({ type: 'play', index: i })
    expect(store.getState().status).toBe('won')
    store.dispatch({ type: 'reset' })
    const s = store.getState()
    expect(s.board.length).toBe(9)
    expect(s.board.every((c: any) => c === null)).toBe(true)
    expect(s.currentPlayer).toBe('X')
    expect(s.status).toBe('playing')
    expect(s.winner).toBe(null)
    // after reset, play resumes normally
    store.dispatch({ type: 'play', index: 0 })
    expect(store.getState().board[0]).toBe('X')
    expect(store.getState().currentPlayer).toBe('O')
  })
})
"""
        _assert_passed(_run_driver(body), "reset restores initial")

    def test_reducer_purity_no_mutation(self):
        """L2: gameReducer never mutates its inputs (accepted + rejected)."""
        body = _PRELUDE + """
describe('bench-purity', () => {
  it('does not mutate input state/board for an accepted play', () => {
    const prev = initialState()
    const boardBefore = prev.board.slice()
    const playerBefore = prev.currentPlayer
    const statusBefore = prev.status
    const winnerBefore = prev.winner
    const next = gameReducer(prev, { type: 'play', index: 0 })
    // input object untouched
    expect(prev.board).toEqual(boardBefore)
    expect(prev.currentPlayer).toBe(playerBefore)
    expect(prev.status).toBe(statusBefore)
    expect(prev.winner).toBe(winnerBefore)
    // and the returned next is a distinct object with the change
    expect(next).not.toBe(prev)
    expect(next.board).not.toBe(prev.board)
    expect(next.board[0]).toBe('X')
    expect(prev.board[0]).toBe(null)
  })

  it('does not mutate input for a rejected (occupied) play', () => {
    let st = initialState()
    st = gameReducer(st, { type: 'play', index: 4 })  // X at 4
    const boardBefore = st.board.slice()
    const playerBefore = st.currentPlayer
    const rejected = gameReducer(st, { type: 'play', index: 4 })
    expect(st.board).toEqual(boardBefore)
    expect(st.currentPlayer).toBe(playerBefore)
    // rejected returns an equal (unchanged) state value
    expect(rejected.board).toEqual(st.board)
    expect(rejected.currentPlayer).toBe(st.currentPlayer)
    expect(rejected.status).toBe(st.status)
  })

  it('is deterministic: equal inputs yield equal outputs', () => {
    const a = gameReducer(initialState(), { type: 'play', index: 5 })
    const b = gameReducer(initialState(), { type: 'play', index: 5 })
    expect(a.board).toEqual(b.board)
    expect(a.currentPlayer).toBe(b.currentPlayer)
    expect(a.status).toBe(b.status)
    expect(a.winner).toBe(b.winner)
  })
})
"""
        _assert_passed(_run_driver(body), "reducer purity / no mutation")
