# Night Light Control Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reliable, accessible and visually polished GTK 4/Libadwaita night-light and brightness app, with a consistent hyprsunset backend, safe installation lifecycle, and the verified build installed in the user's Omarchy session.

**Architecture:** Keep `hyprsunset_backend.py` as the deep backend module for bounded IPC, state readback and service startup; keep schedule parsing/writes in `schedule_utils.py`; keep GTK presentation and interaction in the two existing windows. Share only small, explicit accessibility helpers between the two GTK applications and include every runtime module in installer and uninstaller manifests.

**Tech Stack:** Python 3.11+, GTK 4, Libadwaita, PyGObject, hyprctl/hyprsunset IPC, systemd user service, Waybar JSONC, unittest, shell checks.

## Global Constraints

- Preserve the pre-existing local working-tree implementation; do not reset, clean, stash destructively, or overwrite unrelated files.
- The existing pending implementation is the starting material and must remain covered by `./scripts/check.sh`.
- Do not use `shell=True`; all subprocess calls remain argument-vector based and bounded by timeouts.
- Serialize related state/config mutations with the existing `STATE_LOCK`; preserve atomic writes, symlinks, file modes and backups.
- Manual UI temperature selection remains 2500–5000 K; scheduled non-identity daytime temperatures remain 5900–6500 K; `identity = true` is the natural-color daytime mode.
- Every production behavior change gets a test written and observed failing before its implementation; run the focused test and the full check after each task.
- Do not add network, telemetry, elevated privileges, new runtime dependencies or destructive installation behavior.
- Commit and push each completed phase to `origin/main` only after fresh verification and independent review; do not install the app until all code phases are verified.
- When changing user Hyprland/Waybar files, use the Omarchy safety rules: preserve backups, reload/validate Hyprland, and restart Waybar only after the project install succeeds.

---

### Task 1: Consolidate backend contracts and complete package lifecycle

**Files:**
- Modify: `src/hyprsunset_backend.py`
- Modify: `src/night_light_control.py`
- Modify: `bin/night-light-toggle`
- Modify: `bin/night-light-status`
- Modify: `scripts/install.py`
- Modify: `scripts/uninstall.py`
- Modify: `tests/test_hyprsunset_backend.py`
- Modify: `tests/test_night_light.py`
- Modify: `tests/test_uninstall.py`
- Include and review the already-dirty related files: `src/schedule_utils.py`, `src/brightness_control.py`, `src/brightness_utils.py`, `bin/brightness-step`, `tests/test_schedule_utils.py`, `tests/test_brightness.py`, `data/hyprsunset.conf`, `scripts/check.sh`, and `README.md`.

**Interfaces:**
- `hyprsunset_backend.set_temperature(value)` accepts both the manual/night range 2500–5000 K and valid scheduled daytime values 5900–6500 K, and confirms the readback without treating `identity = true` as a temperature success.
- `hyprsunset_backend.clamp_temperature(value)` continues clamping persisted manual-selection settings to 2500–5000 K.
- `night_light_control.backend_state()` preserves the old `(active, temperature)` compatibility result while the GTK UI and command tools use the richer `BackendState` returned by `read_state()`.
- Installer and uninstaller payload manifests both include `hyprsunset_backend.py`.

- [x] **Step 1: Add failing regression tests for the backend range and compatibility contract**

```python
def test_scheduled_day_temperature_is_accepted_and_confirmed(self):
    command = subprocess.CompletedProcess([], 0, "", "")
    matching = backend.BackendState(True, False, False, 6200)
    with (
        patch.object(backend, "run_command", return_value=command) as run,
        patch.object(backend, "read_state", return_value=matching),
    ):
        result = backend.set_temperature(6200)

    self.assertEqual(result.returncode, 0)
    run.assert_called_once()
```

```python
def test_legacy_backend_state_keeps_tuple_shape_for_callers(self):
    with patch.object(
        night_light, "read_backend_state",
        return_value=night_light.BackendState(True, False, True, 3500),
    ):
        self.assertEqual(night_light.backend_state(), (False, night_light.DAY_TEMP))
```

Run: `/usr/bin/python3 -m unittest tests.test_hyprsunset_backend.CommandTests.test_scheduled_day_temperature_is_accepted_and_confirmed tests.test_night_light.BackendOperationTests.test_legacy_backend_state_keeps_tuple_shape_for_callers -v`
Expected: FAIL because the current backend rejects 6200 K and the compatibility name is currently an alias returning `BackendState`.

- [x] **Step 2: Add a failing uninstall regression test**

```python
def test_uninstall_manifest_includes_hyprsunset_backend(self):
    destination = uninstall.BIN / "hyprsunset_backend.py"
    self.assertEqual(
        uninstall.expected_payload(destination),
        uninstall.ROOT / "src/hyprsunset_backend.py",
    )
```

Run: `/usr/bin/python3 -m unittest tests.test_uninstall.InstallerIntegrationTests.test_uninstall_manifest_includes_hyprsunset_backend -v`
Expected: FAIL because the uninstaller does not yet list the installed backend module.

- [x] **Step 3: Implement the smallest backend and lifecycle changes**

Use one backend range constant for IPC validation (`2500–6500 K`), retain the narrower persisted manual-setting clamp, expose an explicit `read_backend_state` path for modern callers, and implement the legacy tuple wrapper in `night_light_control.py`. Add the backend module to every install/uninstall payload list and update the related integration test.

- [x] **Step 4: Run focused tests and the complete project check**

Run: `/usr/bin/python3 -m unittest tests.test_hyprsunset_backend tests.test_night_light tests.test_uninstall -v`
Expected: all focused tests pass.

Run: `./scripts/check.sh`
Expected: syntax, 95+ unit tests, shell, desktop, safety, schedule and runtime checks all pass with exit code 0.

- [x] **Step 5: Review, commit and push Phase 1**

Before committing, run `git diff --check`, inspect the complete diff against `866c597`, and confirm no unrelated file was removed. Commit all coherent pending implementation plus this task with:

```bash
git add README.md bin data scripts src tests
git commit -m "feat: harden night light backend and packaging"
git push origin main
```

Record the commit and push output in the SDD ledger.

---

### Task 2: Improve GTK accessibility, narrow-window layout and invalid-schedule feedback

**Files:**
- Create: `src/ui_accessibility.py`
- Modify: `src/night_light_control.py`
- Modify: `src/brightness_control.py`
- Modify: `scripts/install.py`
- Modify: `scripts/uninstall.py`
- Modify: `tests/test_night_light.py`
- Modify: `tests/test_brightness.py`
- Modify: `tests/test_uninstall.py`

**Interfaces:**
- `ui_accessibility.set_range(widget, label, minimum, maximum, value, value_text)` updates GTK accessible label/range/value properties.
- `ui_accessibility.set_description(widget, description, invalid=False)` updates a field's accessible description and invalid state.
- `ui_accessibility.set_status(widget, text, busy=False)` gives dynamic operation/feedback labels the `STATUS` role and updates busy state.
- `night_light_control.load_schedule_config(path)` returns `(schedule, uses_identity, error_message)` so malformed user config is visible instead of silently looking healthy.

- [x] **Step 1: Add failing pure/helper tests**

```python
def test_schedule_loader_reports_malformed_config_without_hiding_it(self):
    with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
        path = Path(td) / "hyprsunset.conf"
        path.write_text("profile { time = 99:99 temperature = 3500 }", encoding="utf-8")
        schedule, identity, error = night_light.load_schedule_config(path)

    self.assertEqual(schedule, night_light.default_schedule())
    self.assertFalse(identity)
    self.assertIn("No se pudo validar", error)
```

```python
def test_range_accessibility_sets_label_and_current_value(self):
    calls = []

    class Widget:
        def update_property(self, properties, values):
            calls.append((properties, values))

    accessibility.set_range(Widget(), "Brillo de pantalla", 1, 100, 42, "42 %")
    self.assertEqual(calls[0][1], ["Brillo de pantalla", 1.0, 100.0, 42.0, "42 %"])
```

Run the focused tests and expect them to fail because the loader/helper do not yet exist.

- [x] **Step 2: Implement the shared accessibility helper**

Use `Gtk.AccessibleProperty.LABEL`, `DESCRIPTION`, `VALUE_MIN`, `VALUE_MAX`, `VALUE_NOW`, `VALUE_TEXT`, `Gtk.AccessibleState.INVALID/BUSY`, and `Gtk.AccessibleRole.STATUS`; keep the helper dependency-free apart from GTK and do not create display-dependent test setup.

- [x] **Step 3: Wire accessible names, values and validation state into both windows**

Give both sliders explicit labels, ranges, units and live values; give the brightness icon refresh button an accessible label; associate schedule-entry errors through accessible descriptions and invalid state; mark operation/feedback labels as status regions and update busy state during work.

- [x] **Step 4: Make the hero headers survive 300–360 px widths**

Keep the icon and title in one row, move the numeric metric/value into its own aligned row below it, preserve the established warm amber visual identity, and keep keyboard focus indicators and reduced-motion-safe CSS. Do not add a JavaScript-like resize loop or a new dependency.

- [x] **Step 5: Surface malformed schedule state in the UI**

Use `load_schedule_config()` during bootstrap. Preserve the safe default controls, but show a clear Spanish warning in the schedule feedback/status area explaining that the file could not be validated and that saving is an explicit repair action; never silently claim that the default is the user's active schedule.

- [x] **Step 6: Run focused tests, GTK syntax checks and the full check**

Run: `/usr/bin/python3 -m unittest tests.test_night_light tests.test_brightness tests.test_uninstall -v`
Expected: all pass.

Run: `./scripts/check.sh`
Expected: exit 0 with no Python, shell, desktop or packaging errors.

If the Wayland session is available, launch each installed-from-repo entry under a bounded smoke command and verify it initializes without a traceback; do not leave extra processes running.

- [x] **Step 7: Review, commit and push Phase 2**

```bash
git diff --check
git add src scripts tests
git commit -m "feat: improve GTK accessibility and responsive feedback"
git push origin main
```

Record commit and push evidence.

---

### Task 3: Verify real integrations and update the installed Omarchy app

**Files:**
- Modify only if verification finds a real defect: `scripts/check.sh`, `README.md`, or the affected runtime file.
- User configuration targets, only through the existing installer: `~/.local/bin/`, `~/.local/share/applications/`, `~/.local/share/icons/`, `~/.config/hypr/`, `~/.config/waybar/`.

**Interfaces:**
- `./install.sh` remains the only project entry point used to update the system app.
- The installer must preserve existing user schedule/config files and existing unrelated Waybar/Hyprland actions.
- After installation, the copied runtime files must match the Phase 2 repository files byte-for-byte and the user service/UI integrations must be observable.

- [x] **Step 1: Run the complete pre-install verification**

Run:

```bash
./scripts/check.sh
git status --short --branch
git log --oneline -3
```

Expected: all checks pass, the two phase commits are pushed, and no unexplained generated files exist.

- [x] **Step 2: Capture system state before installation**

Record, without editing:

```bash
systemctl --user is-enabled hyprsunset.service || true
systemctl --user is-active hyprsunset.service || true
hyprctl configerrors || true
sha256sum src/night_light_control.py src/brightness_control.py src/hyprsunset_backend.py
```

- [x] **Step 3: Update the app through the project installer**

Run: `./install.sh`

Expected: exit 0, both launchers/modules installed, existing personal `~/.config/hypr/hyprsunset.conf` preserved, and any optional reload warnings reported explicitly rather than hidden.

- [x] **Step 4: Validate the installed payload and desktop integrations**

Run:

```bash
cmp src/night_light_control.py ~/.local/bin/night-light-control
cmp src/brightness_control.py ~/.local/bin/brightness-control
cmp src/hyprsunset_backend.py ~/.local/bin/hyprsunset_backend.py
systemctl --user is-active hyprsunset.service
hyprctl reload
hyprctl configerrors
omarchy restart waybar
```

Expected: `cmp` and service/config commands succeed; `hyprctl configerrors` reports no new errors; Waybar restarts using the preserved/custom config.

- [x] **Step 5: Run bounded smoke checks and final review**

Run the status helper once, capture valid JSON, run `brightness-step` with no argument to confirm it rejects invalid input without changing hardware, and inspect `git diff`/status after installation to ensure only intended user-state files changed outside the repository.

- [x] **Step 6: Finish with a final whole-branch review and report**

Use the final review package against the branch start, resolve any load-bearing finding before claiming completion, and report exact commits, test counts, install result, runtime validation and any environment-limited checks.
