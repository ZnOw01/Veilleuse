# Night Light Control V2 Operator Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose real hyprsunset gamma control and a scriptable CLI mirror, then make the Waybar status useful without duplicating backend state.

**Architecture:** Extend `BackendState` additively with an optional gamma percentage and keep all IPC/readback logic in `hyprsunset_backend.py`. The GTK window presents gamma as a separate perceived-brightness control with an explicit color-accuracy warning; the CLI and Waybar consume the same backend module and `STATE_LOCK`, never reimplementing state parsing or using shell commands.

**Tech Stack:** Python 3.11+, GTK 4/Libadwaita, hyprctl/hyprsunset IPC, Waybar JSONC, unittest.

## Global Constraints

- Follow the official hyprsunset IPC contract: `gamma <percent>`, `gamma` readback, `reset gamma`, `temperature`, `identity`, and no shell interpolation.
- Gamma is perceived display brightness, not blue-light intensity; label it separately and warn that gamma can reduce color accuracy.
- Preserve the existing four-argument `BackendState` construction compatibility by adding gamma as an optional trailing field.
- Every mutating gamma/temperature/identity action requires bounded timeout, shared lock where multiple operations compose, and readback confirmation.
- Keep the V1 UI copy clean: no internal parser/debug terminology, no raw exceptions, no redundant temperature preset buttons.
- No geolocation, network, sensor, multi-monitor promises or parallel daemon in this phase.
- Each task uses TDD, passes `./scripts/check.sh`, receives independent review, commits and pushes before the next task.

---

### Task 1: Gamma backend contract and GTK control

**Files:**
- Modify: `src/hyprsunset_backend.py`
- Modify: `src/night_light_control.py`
- Modify: `tests/test_hyprsunset_backend.py`
- Modify: `tests/test_night_light.py`
- Modify: `README.md`

**Interfaces:**
- `BackendState.gamma: int | None` is an additive observed percentage field.
- `read_gamma(*, timeout=..., deadline=...) -> int | None` parses the integer percentage returned by `hyprctl hyprsunset gamma`.
- `gamma_applied(gamma, *, deadline=None) -> bool` confirms readback within a small integer tolerance.
- `set_gamma(gamma, *, timeout=...) -> CompletedProcess` validates a safe 0–200 IPC range, sends `gamma <value>`, and confirms readback.
- `reset_gamma(*, timeout=...) -> CompletedProcess` sends `reset gamma` and confirms the observed default/profile gamma when possible; if the installed IPC cannot provide a deterministic reset readback, return a clear failure rather than claiming success.

- [ ] **Step 1: Add failing backend tests**

```python
def test_reads_gamma_percentage(self):
    result = subprocess.CompletedProcess([], 0, "75\n", "")
    with patch.object(backend, "run_command", return_value=result):
        self.assertEqual(backend.read_gamma(), 75)


def test_gamma_request_requires_matching_readback(self):
    command = subprocess.CompletedProcess([], 0, "", "")
    with (
        patch.object(backend, "run_command", return_value=command) as run,
        patch.object(backend, "read_gamma", return_value=75),
    ):
        result = backend.set_gamma(75)
    self.assertEqual(result.returncode, 0)
    self.assertEqual(run.call_args.args[0][-2:], ["gamma", "75"])
```

Run before production code and expect failure because gamma functions/field do not exist.

- [ ] **Step 2: Implement bounded gamma IPC and additive state reads**

Read gamma under the same deadline as identity/temperature, tolerate a missing gamma read without making an otherwise valid state unavailable, and keep old positional `BackendState(...)` callers valid. Add exact tests for malformed/out-of-range output, timeout, delayed readback and no false success.

- [ ] **Step 3: Add the GTK perceived-brightness control**

Add a separate gamma slider (50–100% in the UI, with the backend retaining 0–200% validation), human labels such as “Brillo percibido” and a concise warning “Puede reducir la precisión del color.” Persist the preference only if it is clearly separate from temperature; apply changes through the locked worker/readback path. Do not label gamma as a blue-light or physical brightness percentage.

- [ ] **Step 4: Verify and commit/push V2 Task 1**

Run focused backend/UI tests, `./scripts/check.sh`, `git diff --check`, independent review, then:

```bash
git add src tests README.md
git commit -m "feat: expose hyprsunset gamma control"
git push origin main
```

Reinstall and verify installed payload and GTK smoke before Task 2.

---

### Task 2: Scriptable CLI mirror and useful Waybar status

**Files:**
- Create: `bin/night-light`
- Modify: `bin/night-light-status`
- Modify: `scripts/install.py`
- Modify: `scripts/uninstall.py`
- Modify: `tests/test_hyprsunset_backend.py`
- Modify: `tests/test_uninstall.py`
- Modify: `README.md`

**Interfaces:**
- `night-light --status` prints one JSON payload using the shared backend.
- `night-light --temperature 2700` applies and confirms that temperature.
- `night-light --gamma 75` applies and confirms perceived gamma.
- `night-light --natural` applies and confirms natural color.
- `night-light --reset-gamma` requests the official gamma reset and returns nonzero if confirmation is unavailable.
- `night-light --cycle` advances through the CLI quick modes (2700 K, 3500 K, 4200 K, natural) using observed backend state; it does not recreate preset buttons in the GTK window.
- Invalid combinations return exit 2 without invoking IPC; all commands use the shared `STATE_LOCK` and fixed user-facing stderr.
- Waybar text includes the applied temperature when a filter is active, distinguishes natural color from inactive, and uses left click for `--cycle` plus middle click for the full GUI while preserving unrelated user actions/backward-compatible JSON keys.

- [ ] **Step 1: Add failing CLI and Waybar payload tests**

```python
def test_cli_temperature_uses_shared_backend(self):
    result = cli.main(["--temperature", "2700"])
    self.assertEqual(result, 0)
    setter.assert_called_once_with(2700)


def test_waybar_active_payload_includes_temperature(self):
    payload = status.build_payload(
        BackendState(True, True, False, 2700, 100),
        ServiceState(True, True), "15:30", "06:00",
    )
    self.assertIn("2700 K", payload["text"] + payload["tooltip"])


def test_cli_cycle_uses_observed_state_to_choose_next_mode(self):
    result = cli.main(["--cycle"])
    self.assertEqual(result, 0)
    setter.assert_called_once_with(3500)
```

Run red before adding the CLI/fields.

- [ ] **Step 2: Implement the CLI as a thin adapter**

Use `argparse` with mutually exclusive temperature/natural/status operations, shared backend functions, `exclusive_lock`, and no duplicate subprocess parsing. Add install/uninstall manifests and executable mode tests. Keep errors concise and never leak exception text.

- [ ] **Step 3: Update Waybar without reintroducing presets**

Use observed backend state for the text/tooltip. Add a concise current K only for an active temperature filter; use “Natural” for identity and “Off”/“No disponible” for the other states. Migrate only the app-owned module so left click runs `~/.local/bin/night-light --cycle`, middle click opens `~/.local/bin/night-light-control`, and unrelated user actions remain untouched. Test all three payload variants and the managed click migration.

- [ ] **Step 4: Verify and commit/push V2 Task 2**

Run full checks, independent review, install, `cmp` the CLI/runtime payload, validate JSON, `hyprctl configerrors`, restart Waybar, confirm `git rev-parse HEAD == git rev-parse origin/main`, and remove only internal subagent artifacts.
