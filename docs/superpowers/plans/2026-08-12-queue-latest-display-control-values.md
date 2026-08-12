# Queue Latest Display Control Values Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the unified GTK display controls retain and apply the latest requested brightness, temperature, and gamma values without blocking GTK or reporting unconfirmed success.

**Architecture:** Keep blocking backend calls inside the existing `run_worker` thread boundary. Add a small, testable latest-value queue in `src/veilleuse.py`; brightness queues signal cancellation to the active long-running request, while temperature and gamma keep the active operation and start the latest pending value after its confirmed result. Invoke optional backend `deadline` and cancellation parameters only when the installed backend accepts them, preserving compatibility with both current and later backend branches.

**Tech Stack:** Python 3, `unittest`, GTK 4/Libadwaita, injected backend doubles, `threading.Event`, `inspect.signature`.

## Global Constraints

- Work only in this worktree.
- Modify `src/veilleuse.py` and tests; do not touch the installer.
- Brightness UI and service validation use a minimum of 1%.
- Keep all blocking backend work off GTK's main thread.
- Only show success after the backend result has been confirmed.
- Commit with message `fix: queue latest display control values`.

---

### Task 1: Specify latest-value scheduling and compatible backend invocation

**Files:**
- Modify: `tests/test_veilleuse.py`
- Modify: `src/veilleuse.py`

**Interfaces:**
- Produce `LatestValueQueue`, whose `submit(value)` starts the first value immediately, retains only the newest value while active, optionally signals cancellation for the active value, and starts the retained value after completion.
- Produce `_call_backend(method, *args, deadline=None, should_stop=None)`, which passes only supported optional keyword arguments and supports both `should_stop` and future `cancel_event` cancellation shapes.
- Produce `BRIGHTNESS_MIN = 1`.

- [x] **Step 1: Write failing tests for queue retention and cancellation**

Add tests that submit 20, then 40, then 60 before completing 20; assert only 20 starts first, the cancellation event is set, and 60 starts after completion. Add a non-cancellable queue case asserting 40 is replaced by 60 and starts after 20.

- [x] **Step 2: Run the focused tests and verify the expected missing-symbol failure**

Run: `/usr/bin/python3 -m unittest discover -s tests -p 'test_veilleuse.py' -v`

Expected: FAIL because `LatestValueQueue` is not defined.

- [x] **Step 3: Write the minimal queue and backend adapter**

Implement the queue with a lock, a single pending slot, per-request cancellation event, and completion callback. Implement signature-based optional kwarg filtering and the current/future cancellation aliases. Do not change backend files.

- [x] **Step 4: Run focused tests and verify green**

Run the same focused unittest command and confirm the new queue and adapter tests pass.

---

### Task 2: Make the GTK controls latest-wins and non-blocking

**Files:**
- Modify: `tests/test_veilleuse.py`
- Modify: `src/veilleuse.py`

**Interfaces:**
- Per-control queue channels: `brightness`, `temperature`, and `gamma`.
- Queued workers use a monotonic operation deadline and the compatible backend adapter.
- Obsolete results are ignored for user feedback; the latest request is started after the active worker completes.

- [x] **Step 1: Write failing behavioral tests**

Test that a queued operation's completion callback does not produce a success notification for an obsolete value and that the latest value is launched. Test that the brightness worker receives a cancellation predicate/event while preserving the latest request. Test that a backend accepting `deadline` and `cancel_event` receives both, while a legacy backend receives neither.

- [x] **Step 2: Run focused tests and verify they fail for the missing queue integration**

Run: `/usr/bin/python3 -m unittest discover -s tests -p 'test_veilleuse.py' -v`

Expected: FAIL in the new integration tests because the current GUI callbacks drop requests while `_busy` is true.

- [x] **Step 3: Implement queued GTK operation handling**

Create per-channel queues in the window, keep display controls usable while a worker runs, and route slider callbacks through the queue. Keep backend work in `run_worker`. Treat obsolete/cancelled outcomes as internal when a newer value is pending, and display success only for a confirmed final result. Guard snapshot synchronization so programmatic scale updates do not enqueue writes.

- [x] **Step 4: Run focused tests and verify green**

Run the focused unittest command and confirm the queue integration tests pass.

---

### Task 3: Align brightness range and accessibility names

**Files:**
- Modify: `tests/test_veilleuse.py`
- Modify: `src/veilleuse.py`

**Interfaces:**
- Range controls expose explicit accessible labels, min/max/current/value text.
- Icon-only decrement/increment buttons expose explicit accessible labels in addition to tooltips.
- The night-light switch exposes an explicit accessible label in addition to its tooltip.
- Brightness labels and tooltip state 1–100%, matching the backend.

- [x] **Step 1: Write failing tests**

Assert `veilleuse.BRIGHTNESS_MIN == 1`, the brightness accessible range starts at 1, and the accessible-label helper writes a GTK accessible label for icon-only controls and the switch.

- [x] **Step 2: Run focused tests and verify the expected failures**

Run: `/usr/bin/python3 -m unittest discover -s tests -p 'test_veilleuse.py' -v`

Expected: FAIL because the current range starts at 0 and icon-only/switch labels are tooltip-only.

- [x] **Step 3: Implement the accessible labels and range correction**

Add a small `_accessible_label` helper, call it for both icon-only buttons and the switch, update the brightness range and copy to 1–100, and keep tooltips unchanged as supplemental guidance.

- [x] **Step 4: Run focused tests and verify green**

Run the focused unittest command.

---

### Task 4: Full verification and requested commit

**Files:**
- Modify: `src/veilleuse.py`
- Modify: `tests/test_veilleuse.py`

- [x] **Step 1: Run the focused suite**

Run: `/usr/bin/python3 -m unittest discover -s tests -p 'test_veilleuse.py' -v`

- [x] **Step 2: Run the complete repository check**

Run: `./scripts/check.sh`

- [x] **Step 3: Inspect the final diff and verify installer files are untouched**

Run: `git diff --check` and `git status --short`; confirm no installer file is modified.

- [ ] **Step 4: Commit the implementation**

Run: `git add src/veilleuse.py tests/test_veilleuse.py && git commit -m "fix: queue latest display control values"`

- [ ] **Step 5: Verify the commit SHA and clean requested paths**

Run: `git rev-parse HEAD` and `git show --stat --oneline --summary HEAD`.
