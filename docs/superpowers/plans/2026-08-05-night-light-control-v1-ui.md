# Night Light Control V1 UI Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove confusing/debug UI copy and redundant controls, make the selected-filter intensity truthful, and make the manual-versus-schedule temperature ranges explicit without changing the safe backend contract.

**Architecture:** Keep `identity` as an internal hyprsunset/config concept, but expose only human copy such as “Color natural” and “Sin filtro añadido”. Keep the manual filter at 2500–5000 K so it always represents an active warm filter; document scheduled daytime 5900–6500 K as a separate daytime reference used only when natural color is disabled. Make the selected temperature the sole source for the intensity card and remove preset buttons rather than maintaining a second selection state.

**Tech Stack:** Python 3.11+, GTK 4, Libadwaita, PyGObject, unittest, existing hyprsunset backend and installer.

## Global Constraints

- Preserve the existing backend IPC, locks, atomic schedule writes, identity semantics and install safety.
- `identity` may remain in config/parser/backend code and technical documentation, but must not appear in user-facing GTK labels, subtitles, status messages, timeline text or notifications.
- Manual filter range remains 2500–5000 K; scheduled daytime reference remains 5900–6500 K; copy must label them as different controls.
- Relative selected-filter intensity is 100% at 2500 K, 0% at 5000 K, and is explicitly a comparative UI scale—not a physical measurement.
- The selected temperature and displayed intensity must update together; applied backend state must not overwrite the selected-filter metric with a separate “current” value.
- Remove the five preset buttons and their synchronization callbacks from the GTK window; the continuous slider is the only temperature selector in this V1.
- Remove the generic hero tagline and legal-style intensity disclaimer; retain only actionable labels, state, range and next-step feedback.
- Every behavior change gets a failing test before production code, followed by focused tests, `./scripts/check.sh`, `git diff --check`, review, commit and push.
- Do not add network, telemetry, privileges or runtime dependencies; after the phase is pushed, reinstall through `./install.sh` and validate the system app.

---

### Task 1: Human copy, truthful intensity and single temperature selector

**Files:**
- Modify: `src/night_light_control.py`
- Modify: `tests/test_night_light.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-05-night-light-control-v1-ui.md`

**Interfaces:**
- `temperature_description(temperature, identity=True)` returns human copy without the token `identity`.
- `relative_filter_intensity(2500) == 100` and `relative_filter_intensity(5000) == 0` remain the pure metric contract.
- Add a small pure presentation helper if needed to return selected-filter display data (`temperature`, `intensity`, `fraction`, `label`) so tests can verify the UI source of truth without constructing a display.

- [x] **Step 1: Add failing tests for the observed UI bugs**

```python
def test_natural_color_copy_does_not_expose_internal_identity_name(self):
    copy = night_light.temperature_description(3500, identity=True)
    self.assertNotIn("identity", copy.lower())
    self.assertIn("natural", copy.lower())


def test_selected_filter_intensity_has_correct_extremes(self):
    self.assertEqual(night_light.relative_filter_intensity(2500), 100)
    self.assertEqual(night_light.relative_filter_intensity(5000), 0)
```

Add a pure assertion for the selected display contract that the value used by the intensity card at 2500 K is `100%`/fraction `1.0`, and a source/copy regression that no user-facing UI string contains `identity`, `medición física`, `no sustituye`, `Tu luz, a tu ritmo`, or the old preset labels.

Run the focused tests before implementation. Expected: the copy/source and selected-display assertions fail against the current UI.

- [x] **Step 2: Implement human copy and separate range language**

Change the hero to an actionable title such as “Filtro de luz azul” with a concise subtitle about manual control and automatic schedule. Rename the manual switch to “Activar filtro ahora” and explain that it does not alter the automatic schedule. Label the card as manual 2500–5000 K. Rename the daytime option to “Usar color natural” with “Sin filtro añadido durante el día”; describe the disabled daytime spin row as a 5900–6500 K reference used only when natural color is disabled. In timeline and state copy use “Color natural”, “Sin filtro añadido”, “Filtro activo · N K”, “Filtro desactivado” and “Backend no disponible”; never expose `identity`.

- [x] **Step 3: Make the selected filter the only intensity source**

Keep the existing correct comparative formula, but make `_update_selected_temperature()` update the intensity label and progress fraction from `self.selected_temp`. Stop `_apply_backend_state()` from replacing that selected metric with the applied backend state. Keep the applied state visible in the “Ahora” panel/status, so selected versus applied state is clear without two competing intensity values. Remove the redundant selected-panel intensity label if the intensity row below already displays it. Copy must say “Intensidad del filtro seleccionado” and `2500 K = más cálido · 5000 K = más natural`.

- [x] **Step 4: Remove preset controls and associated state synchronization**

Delete the five `Gtk.ToggleButton` preset creation loop, `.preset` styling, sensitivity loop, `sync_presets()` and `on_preset()` callbacks. Keep only the continuous slider and its two range labels. This makes an intermediate value unable to leave a stale preset highlighted.

- [x] **Step 5: Remove non-actionable filler**

Delete the generic tagline and the legal-style disclaimer/callout. Do not remove operational errors, range explanations, backend status, schedule instructions or accessibility labels.

- [x] **Step 6: Update tests and README, then verify**

Update tests for the human copy, selected intensity display, absence of preset UI strings, and preserved internal parser/backend behavior. Update README to describe the manual 2500–5000 K range separately from the 5900–6500 K daytime reference and stop presenting five presets as a feature.

Run:

```bash
/usr/bin/python3 -m unittest tests.test_night_light -v
./scripts/check.sh
git diff --check
```

Expected: all tests pass, no user-facing forbidden strings remain in the GTK source, and all project checks exit 0.

- [x] **Step 7: Review and commit locally (push/install intentionally deferred by task scope)**

After independent review:

```bash
git add src/night_light_control.py tests/test_night_light.py README.md docs/superpowers/plans/2026-08-05-night-light-control-v1-ui.md
git commit -m "fix: simplify night light controls and intensity display"
git push origin main
./install.sh
```

Then verify `HEAD == origin/main`, installed source files match with `cmp`, `hyprctl configerrors` is empty after reload, Waybar restarts, and bounded GTK smoke emits no stderr warnings.
