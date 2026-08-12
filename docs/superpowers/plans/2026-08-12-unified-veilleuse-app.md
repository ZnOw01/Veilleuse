# Unified Veilleuse Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one adaptive GTK4/Libadwaita Veilleuse application and one CLI using the `native_backends.py` contract, while preserving accessible controls, non-blocking workers, toasts, and non-destructive schedule writes.

**Architecture:** `src/veilleuse.py` owns a backend-neutral application service layer, schedule persistence helpers, CLI behavior, and the lazily imported GTK view. The CLI launcher delegates to the same service functions as the GUI and accepts an injected backend bundle in tests. The native backend is deliberately not created in this branch.

**Tech Stack:** Python 3, GTK4, Libadwaita, GLib idle callbacks, `unittest`, existing `schedule_utils.py` parser/lock/atomic writer, SVG desktop icon.

## Global Constraints

- APP_ID is exactly `io.github.ZnOw01.Veilleuse`.
- Use command adapters from `src/native_backends.py` only through lazy imports or injection; do not implement that backend here.
- GTK work must remain on GTK's main thread; hardware and filesystem operations run in workers.
- Schedule updates preserve unrelated/custom content and use atomic writes; existing schedule files are never replaced by defaults.
- Keep all legacy files and installer/uninstaller untouched.
- Do not use `shell=True`, telemetry, network, sudo, `eval`, or `exec`.
- Verify red tests before production code, focused tests, the complete test suite, compile checks, shell syntax, and desktop-file validation.

---

### Task 1: Define the application/service contract with failing tests

**Files:**
- Create: `tests/test_veilleuse.py`
- Create: `tests/test_veilleuse_cli.py`
- Create: `src/veilleuse.py`
- Create: `bin/veilleuse`

**Interfaces:**
- `BackendBundle(brightness, night_light)` groups the two injected adapters.
- `status_snapshot(backends)` returns JSON-safe `brightness` and `night_light` state mappings.
- `toggle_night_light(backends, fallback_temperature=3500)` observes state, then writes natural mode or the observed/fallback warm temperature.
- `apply_cli_operation(backends, args)` handles one validated CLI operation and returns a JSON-safe result or raises `OperationError`.
- `update_schedule_text(text, values)` updates only recognized managed fields in the first day/night profiles and preserves all other text.
- `write_schedule(path, values)` validates existing content, updates it non-destructively, and writes with `schedule_utils.atomic_write_text` under `schedule_utils.exclusive_lock`.

- [x] **Step 1: Write failing tests for identity, lazy backend loading, CLI operations, schedule preservation, and worker isolation.**
- [x] **Step 2:** Run `python3 -m unittest tests.test_veilleuse tests.test_veilleuse_cli -v` and confirm failures are caused by missing `src/veilleuse.py`/`bin/veilleuse` behavior.
- [x] **Step 3:** Implement the minimal backend-neutral service layer and schedule adapter.
- [x] **Step 4:** Re-run the focused tests until green, then refactor only while green.

### Task 2: Add the unified GTK4/Libadwaita window

**Files:**
- Modify: `src/veilleuse.py`
- Modify: `tests/test_veilleuse.py`

**Interfaces:**
- `create_application(backends=None)` lazily imports GTK/Adwaita and returns an `Adw.Application` with the exact app ID.
- `VeilleuseWindow` presents compact status, Pantalla, Luz nocturna, and Horario sections.
- `run_worker(start, on_success, on_error)` starts a daemon worker and schedules UI callbacks with GLib.

- [x] **Step 1:** Add failing source-contract tests for exact APP_ID, no legacy UI implementation terms, lazy GTK imports, accessible range controls, and worker callback scheduling.
- [x] **Step 2:** Run the focused GTK-contract tests and confirm they fail before the view exists.
- [x] **Step 3:** Implement the adaptive `Adw.ApplicationWindow` with `Adw.ToolbarView`, `Adw.Clamp`, scrollable content, semantic labels, keyboard-focusable controls, and `Adw.ToastOverlay`.
- [x] **Step 4:** Wire brightness, night-light, and schedule saves through daemon workers; refresh confirmed state on the GTK thread and show success/actionable failure toasts.
- [x] **Step 5:** Run focused tests and compile checks; keep the suite green.

### Task 3: Add the unified CLI and packaging metadata

**Files:**
- Modify: `bin/veilleuse`
- Create: `data/io.github.ZnOw01.Veilleuse.desktop.in`
- Create: `data/io.github.ZnOw01.Veilleuse.svg`
- Modify: `tests/test_veilleuse_cli.py`

**Interfaces:**
- CLI supports mutually exclusive `--status`, `--toggle`, `--natural`, `--temperature K`, `--gamma PERCENT`, and `--brightness PERCENT`; no operation launches the GUI.
- CLI status and successful mutations use the same backend-neutral service functions as the GUI.
- Desktop metadata uses `io.github.ZnOw01.Veilleuse` as icon and startup class.

- [x] **Step 1:** Add failing subprocess/parser tests for every CLI operation, invalid combinations, JSON status, and desktop metadata.
- [x] **Step 2:** Run the CLI tests and observe the expected failures.
- [x] **Step 3:** Implement the executable launcher with source-path bootstrapping and the CLI parser/dispatch.
- [x] **Step 4:** Add the unified warm-sun/moon SVG and desktop entry without changing installer/uninstaller code.
- [x] **Step 5:** Run focused tests, all historical tests, `python3 -m compileall`, `bash -n`, and `desktop-file-validate`.

### Task 4: Final verification and commit

**Files:**
- Review: all files created by Tasks 1–3

- [x] **Step 1:** Run the specific new tests and record output.
- [x] **Step 2:** Run the complete applicable suite and resolve regressions without modifying legacy behavior.
- [x] **Step 3:** Inspect the diff for forbidden installer/uninstaller/legacy changes.
- [ ] **Step 4:** Commit exactly with `feat: add unified Veilleuse application` (blocked: worktree Git metadata is read-only).
- [ ] **Step 5:** Report the commit SHA and verification commands/results after the Git metadata becomes writable.
