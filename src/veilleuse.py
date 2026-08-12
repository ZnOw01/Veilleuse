#!/usr/bin/python3
"""Unified Veilleuse application and command-line service layer.

The native command adapters are intentionally not part of this branch.  This
module imports them only when a real application or CLI operation needs them,
and keeps the rest of the behavior testable with small injected doubles.
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from schedule_utils import (
        DAY_TEMP,
        DAY_TEMP_MAX,
        DAY_TEMP_MIN,
        DEFAULT_TEMP,
        HYPRSUNSET_CONFIG,
        NIGHT_TEMP_MAX,
        NIGHT_TEMP_MIN,
        STATE_LOCK,
        atomic_write_text,
        default_schedule,
        exclusive_lock,
        iter_profile_blocks,
        normalize_clock,
        parse_schedule_text,
        profile_info,
        profile_kind,
        validate_schedule,
    )
except ModuleNotFoundError as error:
    if error.name != "schedule_utils":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from schedule_utils import (
        DAY_TEMP,
        DAY_TEMP_MAX,
        DAY_TEMP_MIN,
        DEFAULT_TEMP,
        HYPRSUNSET_CONFIG,
        NIGHT_TEMP_MAX,
        NIGHT_TEMP_MIN,
        STATE_LOCK,
        atomic_write_text,
        default_schedule,
        exclusive_lock,
        iter_profile_blocks,
        normalize_clock,
        parse_schedule_text,
        profile_info,
        profile_kind,
        validate_schedule,
    )


APP_ID = "io.github.ZnOw01.Veilleuse"
SCHEDULE_PATH = HYPRSUNSET_CONFIG
GAMMA_MIN = 0
GAMMA_MAX = 100
BRIGHTNESS_MIN = 1
BRIGHTNESS_MAX = 100
CONTROL_DEADLINE = 2.0


class OperationError(RuntimeError):
    """An operation could not be confirmed and can be shown to a user."""


@dataclass(frozen=True)
class BackendBundle:
    """The only application dependency on the native adapters."""

    brightness: Any
    night_light: Any


def load_backends() -> BackendBundle:
    """Construct the native adapters lazily from their documented contract."""
    try:
        from native_backends import OmarchyBrightnessBackend, OmarchyNightLightBackend
    except ModuleNotFoundError as error:
        if error.name != "native_backends":
            raise
        raise OperationError("El backend nativo no está disponible") from error
    return BackendBundle(OmarchyBrightnessBackend(), OmarchyNightLightBackend())


def _state_mapping(state: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if dataclasses.is_dataclass(state):
        result = dataclasses.asdict(state)
    else:
        result = {field: getattr(state, field, None) for field in fields}
    return {field: result.get(field) for field in fields}


def _require_available(state: Any, name: str) -> None:
    if not getattr(state, "available", False):
        raise OperationError(f"{name} no está disponible")


def _confirmed_state(
    result: Any,
    reader: Callable[[], Any],
    name: str,
    *,
    deadline: float | None = None,
) -> Any:
    state = result if result is not None else _call_backend(reader, deadline=deadline)
    _require_available(state, name)
    if getattr(state, "error", None):
        raise OperationError(str(state.error))
    return state


def status_snapshot(backends: BackendBundle) -> dict[str, dict[str, Any]]:
    """Read a coherent, JSON-safe snapshot from both injected adapters."""
    brightness = backends.brightness.read_state()
    night_light = backends.night_light.read_state()
    return {
        "brightness": _state_mapping(
            brightness, ("available", "percent", "monitor", "error")
        ),
        "night_light": _state_mapping(
            night_light,
            ("available", "enabled", "temperature", "identity", "gamma", "error"),
        ),
    }


def toggle_night_light(
    backends: BackendBundle, fallback_temperature: int = DEFAULT_TEMP
) -> dict[str, Any]:
    """Toggle between warm light and natural color using observed state."""
    current = backends.night_light.read_state()
    _require_available(current, "La luz nocturna")
    identity = getattr(current, "identity", None)
    is_warm = (
        not identity
        if identity is not None
        else getattr(current, "enabled", None) is True
    )
    if is_warm:
        result = backends.night_light.set_natural()
    else:
        temperature = getattr(current, "temperature", None) or fallback_temperature
        result = backends.night_light.set_temperature(int(temperature))
    confirmed = _confirmed_state(result, backends.night_light.read_state, "La luz nocturna")
    return _state_mapping(
        confirmed,
        ("available", "enabled", "temperature", "identity", "gamma", "error"),
    )


def _bounded_integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError) as error:
        raise OperationError(f"{label} no es válido") from error
    if integer < minimum or integer > maximum:
        raise OperationError(f"{label} debe estar entre {minimum} y {maximum}")
    return integer


def apply_cli_operation(backends: BackendBundle, args: argparse.Namespace) -> Any:
    """Apply one CLI operation through the same adapters used by the window."""
    if args.status:
        return status_snapshot(backends)
    if args.toggle:
        return {"night_light": toggle_night_light(backends)}

    if args.natural:
        current = backends.night_light.read_state()
        _require_available(current, "La luz nocturna")
        result = backends.night_light.set_natural()
        confirmed = _confirmed_state(result, backends.night_light.read_state, "La luz nocturna")
        return {"night_light": _state_mapping(
            confirmed, ("available", "enabled", "temperature", "identity", "gamma", "error")
        )}
    if args.temperature is not None:
        temperature = _bounded_integer(
            args.temperature, NIGHT_TEMP_MIN, DAY_TEMP_MAX, "La temperatura"
        )
        current = backends.night_light.read_state()
        _require_available(current, "La luz nocturna")
        result = backends.night_light.set_temperature(temperature)
        confirmed = _confirmed_state(result, backends.night_light.read_state, "La luz nocturna")
        return {"night_light": _state_mapping(
            confirmed, ("available", "enabled", "temperature", "identity", "gamma", "error")
        )}
    if args.gamma is not None:
        gamma = _bounded_integer(args.gamma, GAMMA_MIN, GAMMA_MAX, "La gamma")
        current = backends.night_light.read_state()
        _require_available(current, "La luz nocturna")
        result = backends.night_light.set_gamma(gamma)
        confirmed = _confirmed_state(result, backends.night_light.read_state, "La luz nocturna")
        return {"night_light": _state_mapping(
            confirmed, ("available", "enabled", "temperature", "identity", "gamma", "error")
        )}
    if args.brightness is not None:
        brightness = _bounded_integer(
            args.brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX, "El brillo"
        )
        current = backends.brightness.read_state()
        _require_available(current, "La pantalla")
        result = backends.brightness.set_percent(brightness)
        confirmed = _confirmed_state(result, backends.brightness.read_state, "La pantalla")
        return {"brightness": _state_mapping(
            confirmed, ("available", "percent", "monitor", "error")
        )}
    raise OperationError("Selecciona una operación")


def _mask_for_assignments(text: str) -> str:
    """Mask comments and quoted strings while retaining all offsets."""
    chars = list(text)
    quote = False
    escaped = False
    comment = False
    for index, char in enumerate(chars):
        if comment:
            if char == "\n":
                comment = False
            elif char != "\r":
                chars[index] = " "
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
            if char not in "\r\n":
                chars[index] = " "
            continue
        if char == '"':
            quote = True
            chars[index] = " "
        elif char == "#":
            comment = True
            chars[index] = " "
    return "".join(chars)


def _replace_assignment(block: str, name: str, value: Any) -> str:
    masked = _mask_for_assignments(block)
    assignment = re.search(
        rf"(?mi)(?<![A-Za-z0-9_]){re.escape(name)}[ \t]*=", masked
    )
    if assignment is None:
        return block
    value_match = re.match(r"\s*([^\s{}]+)", masked[assignment.end():])
    if value_match is None:
        return block
    value_start = assignment.end() + value_match.start(1)
    value_end = assignment.end() + value_match.end(1)
    return block[:value_start] + str(value) + block[value_end:]


def _insert_assignment(block: str, name: str, value: Any) -> str:
    closing = block.rfind("}")
    if closing < 0:
        return block
    newline = "\r\n" if "\r\n" in block else "\n"
    return block[:closing] + f"    {name} = {value}{newline}" + block[closing:]


def _update_profile(profile: str, time_value: str, temperature: int | None) -> str:
    updated = _replace_assignment(profile, "time", time_value)
    if temperature is not None:
        updated = _replace_assignment(updated, "temperature", temperature)
        if "temperature" not in _mask_for_assignments(updated):
            updated = _insert_assignment(updated, "temperature", temperature)
    return updated


def update_schedule_text(existing: str, schedule: dict[str, Any]) -> str:
    """Update the primary day/night profiles without deleting user content."""
    values = validate_schedule(schedule, clamp=False)
    replacements = []
    found_day = False
    found_night = False
    for start, end, profile in iter_profile_blocks(existing):
        info = profile_info(profile)
        kind = profile_kind(info)
        if kind == "day" and not found_day:
            replacements.append((
                start, end, _update_profile(profile, values["day_time"],
                                             None if info.get("identity") is True else values["day_temp"]),
            ))
            found_day = True
        elif kind == "night" and not found_night:
            replacements.append((
                start, end, _update_profile(profile, values["night_time"], values["night_temp"]),
            ))
            found_night = True

    if not found_day or not found_night:
        raise ValueError("La configuración no contiene perfiles de día y noche válidos")
    updated = existing
    for start, end, replacement in reversed(replacements):
        updated = updated[:start] + replacement + updated[end:]
    parse_schedule_text(updated, strict=True)
    return updated


def render_schedule(schedule: dict[str, Any]) -> str:
    values = validate_schedule(schedule, clamp=False)
    return (
        "# Generated by Veilleuse. Times use the system timezone.\n"
        "profile {\n"
        f"    time = {values['day_time']}\n"
        "    identity = true\n"
        "}\n\n"
        "profile {\n"
        f"    time = {values['night_time']}\n"
        f"    temperature = {values['night_temp']}\n"
        "}\n"
    )


def load_schedule(path: Path | str | None = None) -> dict[str, Any]:
    """Load a valid schedule, retaining defaults only as a display fallback."""
    target = SCHEDULE_PATH if path is None else Path(path)
    try:
        return parse_schedule_text(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_schedule()


def write_schedule(path: Path | str, schedule: dict[str, Any]) -> None:
    """Atomically update a valid existing schedule, or create a missing one."""
    target = Path(path)
    values = validate_schedule(schedule, clamp=False)
    with exclusive_lock(STATE_LOCK):
        mode = target.stat().st_mode & 0o7777 if target.exists() else 0o644
        if target.exists():
            if target.is_symlink():
                raise ValueError("No se puede guardar sobre un enlace simbólico")
            existing = target.read_text(encoding="utf-8")
            if not existing.strip():
                raise ValueError("El horario existente está vacío")
            updated = update_schedule_text(existing, values)
        else:
            updated = render_schedule(values)
        atomic_write_text(target, updated, mode)


def safe_error_message(error: BaseException) -> str:
    if isinstance(error, OperationError):
        return str(error)
    return "No se pudo confirmar la operación"


class DisplayControlState:
    """Keep confirmed display values separate from transient widget values."""

    _FIELDS = {
        "brightness": ("brightness", "percent"),
        "temperature": ("night_light", "temperature"),
        "gamma": ("night_light", "gamma"),
    }

    def __init__(self):
        self._confirmed: dict[str, int | None] = {
            channel: None for channel in self._FIELDS
        }
        self._requested: dict[str, int | None] = {
            channel: None for channel in self._FIELDS
        }
        self._syncing = False
        self._refresh_pending = False

    @property
    def accepts_user_input(self) -> bool:
        return not self._syncing

    def synchronize(self, apply: Callable[[], Any]) -> Any:
        previous = self._syncing
        self._syncing = True
        try:
            return apply()
        finally:
            self._syncing = previous

    def confirmed(self, channel: str) -> int | None:
        return self._confirmed[channel]

    def request(self, channel: str, value: int) -> int:
        self._requested[channel] = value
        return value

    def step_brightness(self, direction: int) -> int:
        base = self._requested["brightness"]
        if base is None:
            base = self._confirmed["brightness"] or BRIGHTNESS_MIN
        return self.request(
            "brightness",
            max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, base + direction)),
        )

    def confirm(
        self,
        channel: str,
        state: Any,
        *,
        obsolete: bool = False,
        apply: Callable[[int], Any] | None = None,
    ) -> int | None:
        if obsolete:
            return None
        _section, field = self._FIELDS[channel]
        value = getattr(state, field, None)
        if value is None:
            return None
        self._confirmed[channel] = value
        self._requested[channel] = value
        if apply is not None:
            self.synchronize(lambda: apply(value))
        return value

    def apply_snapshot(
        self,
        snapshot: dict[str, Any],
        idle_channels: set[str],
        *,
        apply: Callable[[dict[str, int]], Any] | None = None,
    ) -> dict[str, int]:
        updates: dict[str, int] = {}
        for channel, (section, field) in self._FIELDS.items():
            if channel not in idle_channels:
                continue
            values = snapshot.get(section, {})
            value = values.get(field)
            if value is None:
                continue
            self._confirmed[channel] = value
            self._requested[channel] = value
            updates[channel] = value
        if apply is not None and updates:
            self.synchronize(lambda: apply(updates))
        return updates

    def request_refresh(self, *, controls_idle: bool) -> bool:
        if not controls_idle:
            self._refresh_pending = True
            return False
        self._refresh_pending = False
        return True

    def take_deferred_refresh(self, *, controls_idle: bool) -> bool:
        if not controls_idle or not self._refresh_pending:
            return False
        self._refresh_pending = False
        return True


_MISSING = object()


class LatestValueQueue:
    """Serialize a control's work while retaining only its newest request."""

    def __init__(
        self,
        start: Callable[[Any, threading.Event, Callable[[Any], Any]], Any],
        on_result: Callable[[Any, Any, bool], Any],
        *,
        cancel_active: bool = False,
    ):
        self._start = start
        self._on_result = on_result
        self._cancel_active = cancel_active
        self._lock = threading.Lock()
        self._active_value = _MISSING
        self._active_token = None
        self._active_cancel: threading.Event | None = None
        self._pending = _MISSING

    def submit(self, value: Any) -> bool:
        with self._lock:
            if self._active_value is not _MISSING:
                self._pending = value
                if self._cancel_active and self._active_cancel is not None:
                    self._active_cancel.set()
                return False
            cancel_event = threading.Event()
            request_token = object()
            self._active_value = value
            self._active_token = request_token
            self._active_cancel = cancel_event
        self._start(
            value,
            cancel_event,
            lambda result: self._complete(request_token, result),
        )
        return True

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active_value is not _MISSING

    def _complete(self, request_token: object, result: Any) -> None:
        with self._lock:
            if request_token is not self._active_token:
                return
            value = self._active_value
            pending = self._pending
            self._pending = _MISSING
            if pending is _MISSING:
                self._active_value = _MISSING
                self._active_token = None
                self._active_cancel = None
            else:
                next_cancel = threading.Event()
                next_token = object()
                self._active_value = pending
                self._active_token = next_token
                self._active_cancel = next_cancel
        obsolete = pending is not _MISSING
        self._on_result(value, result, obsolete)
        if pending is not _MISSING:
            self._start(
                pending,
                next_cancel,
                lambda next_result: self._complete(next_token, next_result),
            )


def _callable_accepts(method: Callable[..., Any], name: str) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    if name in signature.parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _call_backend(
    method: Callable[..., Any],
    *args: Any,
    deadline: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Any:
    """Call current or future backend methods without assuming new kwargs."""
    kwargs: dict[str, Any] = {}
    if deadline is not None and _callable_accepts(method, "deadline"):
        kwargs["deadline"] = deadline
    if should_stop is not None:
        if _callable_accepts(method, "should_stop"):
            kwargs["should_stop"] = should_stop
        if _callable_accepts(method, "cancel_event"):
            kwargs["cancel_event"] = getattr(should_stop, "__self__", should_stop)
    return method(*args, **kwargs)


def _dispatch_to_main(callback: Callable[[], Any]) -> Any:
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
        GLib.idle_add(callback)
    except (ImportError, ValueError):
        callback()
    return None


def run_worker(
    work: Callable[[], Any],
    on_success: Callable[[Any], Any],
    on_error: Callable[[str], Any],
    *,
    dispatch: Callable[[Callable[[], Any]], Any] | None = None,
) -> threading.Thread:
    """Run blocking work away from GTK and marshal its result back."""
    post = _dispatch_to_main if dispatch is None else dispatch

    def target() -> None:
        try:
            result = work()
        except Exception as error:  # UI boundary: convert all worker failures.
            post(lambda: on_error(safe_error_message(error)))
        else:
            post(lambda: on_success(result))

    thread = threading.Thread(target=target, name="veilleuse-worker", daemon=True)
    thread.start()
    return thread


def _gtk_modules():
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib, Gtk
    return Adw, Gio, GLib, Gtk


def _accessible_range(widget: Any, label: str, minimum: int, maximum: int, value: int, text: str) -> None:
    try:
        Adw, _Gio, _GLib, Gtk = _gtk_modules()
        del Adw
        widget.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.VALUE_MIN,
             Gtk.AccessibleProperty.VALUE_MAX, Gtk.AccessibleProperty.VALUE_NOW,
             Gtk.AccessibleProperty.VALUE_TEXT],
            [label, float(minimum), float(maximum), float(value), text],
        )
    except (AttributeError, ImportError, ValueError):
        pass


def _accessible_label(widget: Any, label: str) -> None:
    try:
        _Adw, _Gio, _GLib, Gtk = _gtk_modules()
        widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    except (AttributeError, ImportError, ValueError):
        pass


def create_application(backends: BackendBundle | None = None):
    """Create the single adaptive Libadwaita application window."""
    Adw, Gio, GLib, Gtk = _gtk_modules()

    class VeilleuseWindow(Adw.ApplicationWindow):
        def __init__(self, application):
            super().__init__(application=application, title="Veilleuse")
            self.backends = backends
            self._busy = False
            self._control_state = DisplayControlState()
            self._control_queues: dict[str, LatestValueQueue] = {}
            self._schedule = default_schedule()
            self._build_ui()
            self._refresh(include_schedule=True)

        def _build_ui(self):
            toolbar = Adw.ToolbarView()
            header = Adw.HeaderBar()
            header.set_title_widget(Adw.WindowTitle(
                title="Veilleuse", subtitle="Pantalla y descanso visual"
            ))
            toolbar.add_top_bar(header)
            self.toast_overlay = Adw.ToastOverlay()
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            clamp = Adw.Clamp(maximum_size=820, tightening_threshold=600)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            for side in ("top", "bottom", "start", "end"):
                getattr(content, f"set_margin_{side}")(20 if side != "bottom" else 28)
            clamp.set_child(content)
            scroll.set_child(clamp)
            self.toast_overlay.set_child(scroll)
            toolbar.set_content(self.toast_overlay)
            self.set_content(toolbar)

            intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            intro.append(Gtk.Label(label="VEILLEUSE", xalign=0, css_classes=["dim-label"]))
            intro.append(Gtk.Label(label="Luz tranquila, en un solo lugar", xalign=0,
                                   css_classes=["title-1"]))
            self.status_label = Gtk.Label(label="Comprobando pantalla y luz nocturna…",
                                          xalign=0, wrap=True)
            intro.append(self.status_label)
            content.append(intro)

            content.append(self._build_brightness_section())
            content.append(self._build_night_section())
            content.append(self._build_schedule_section())

        def _section(self, title: str, subtitle: str):
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                            css_classes=["card"])
            group.append(Gtk.Label(label=title, xalign=0, css_classes=["title-3"]))
            group.append(Gtk.Label(label=subtitle, xalign=0, wrap=True,
                                   css_classes=["dim-label"]))
            return group

        def _build_brightness_section(self):
            group = self._section("Pantalla", "Ajusta el brillo real del monitor seleccionado.")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            self.brightness_value = Gtk.Label(label="—", width_chars=5, xalign=1)
            self.brightness_scale = Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL, BRIGHTNESS_MIN, BRIGHTNESS_MAX, 1
            )
            self.brightness_scale.set_draw_value(False)
            self.brightness_scale.set_hexpand(True)
            self.brightness_scale.set_tooltip_text("Brillo de la pantalla, de 1 a 100 por ciento")
            _accessible_range(self.brightness_scale, "Brillo de la pantalla",
                              BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_MIN,
                              f"{BRIGHTNESS_MIN} %")
            self.brightness_scale.connect("value-changed", self._brightness_changed)
            minus = Gtk.Button.new_from_icon_name("list-remove-symbolic")
            minus.set_tooltip_text("Reducir brillo un punto")
            _accessible_label(minus, "Reducir brillo")
            minus.connect("clicked", lambda *_: self._step_brightness(-1))
            plus = Gtk.Button.new_from_icon_name("list-add-symbolic")
            plus.set_tooltip_text("Aumentar brillo un punto")
            _accessible_label(plus, "Aumentar brillo")
            plus.connect("clicked", lambda *_: self._step_brightness(1))
            row.append(minus)
            row.append(self.brightness_scale)
            row.append(plus)
            row.append(self.brightness_value)
            group.append(row)
            return group

        def _build_night_section(self):
            group = self._section("Luz nocturna", "Calidez, color natural y ajuste fino para la noche.")
            toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            toggle_row.append(Gtk.Label(label="Activar luz nocturna", xalign=0, hexpand=True))
            self.night_switch = Gtk.Switch()
            self.night_switch.set_tooltip_text("Activa o desactiva la luz nocturna")
            _accessible_label(self.night_switch, "Activar o desactivar la luz nocturna")
            self.night_switch.connect("state-set", self._night_toggled)
            toggle_row.append(self.night_switch)
            natural = Gtk.Button(label="Color natural")
            natural.connect("clicked", lambda *_: self._start_backend("natural"))
            toggle_row.append(natural)
            group.append(toggle_row)

            self.temperature_value = Gtk.Label(label="—", xalign=0)
            group.append(self.temperature_value)
            self.temperature_scale = Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL, NIGHT_TEMP_MIN, 5000, 100
            )
            self.temperature_scale.set_draw_value(False)
            self.temperature_scale.set_hexpand(True)
            _accessible_range(self.temperature_scale, "Temperatura de la luz nocturna",
                              NIGHT_TEMP_MIN, 5000, DEFAULT_TEMP, f"{DEFAULT_TEMP} K")
            self.temperature_scale.connect("value-changed", self._temperature_changed)
            group.append(self.temperature_scale)

            self.gamma_value = Gtk.Label(label="Gamma —", xalign=0)
            group.append(self.gamma_value)
            self.gamma_scale = Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL, GAMMA_MIN, GAMMA_MAX, 1
            )
            self.gamma_scale.set_value(100)
            self.gamma_scale.set_draw_value(False)
            self.gamma_scale.set_hexpand(True)
            _accessible_range(self.gamma_scale, "Gamma de color", 0, 100, 100, "100 %")
            self.gamma_scale.connect("value-changed", self._gamma_changed)
            group.append(self.gamma_scale)
            return group

        def _build_schedule_section(self):
            group = self._section("Horario", "Guarda cuándo empieza el día, la noche y su temperatura cálida.")
            grid = Gtk.Grid(column_spacing=12, row_spacing=8)
            self.day_entry = Gtk.Entry(text=self._schedule["day_time"])
            self.night_entry = Gtk.Entry(text=self._schedule["night_time"])
            self.night_temp_spin = Gtk.SpinButton.new_with_range(NIGHT_TEMP_MIN, NIGHT_TEMP_MAX, 100)
            self.night_temp_spin.set_value(self._schedule["night_temp"])
            for row, label, widget in (
                (0, "Empieza el día", self.day_entry),
                (1, "Empieza la noche", self.night_entry),
                (2, "Temperatura nocturna", self.night_temp_spin),
            ):
                grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
                grid.attach(widget, 1, row, 1, 1)
            group.append(grid)
            save = Gtk.Button(label="Guardar horario", css_classes=["suggested-action"])
            save.connect("clicked", self._save_schedule)
            group.append(save)
            return group

        def _refresh(self, *, include_schedule=False):
            if not self._control_state.request_refresh(
                controls_idle=self._all_controls_idle()
            ):
                return
            self._set_busy(True)
            def read():
                bundle = self.backends or load_backends()
                schedule = load_schedule() if include_schedule else None
                return bundle, status_snapshot(bundle), schedule
            run_worker(read, self._apply_snapshot, self._show_error)

        def _apply_snapshot(self, result):
            self.backends, snapshot, schedule = result
            if schedule is not None:
                self._schedule = schedule
                self.day_entry.set_text(schedule["day_time"])
                self.night_entry.set_text(schedule["night_time"])
                self.night_temp_spin.set_value(schedule["night_temp"])
            brightness = snapshot["brightness"]
            night = snapshot["night_light"]
            idle_channels = {
                channel for channel in self._control_state._FIELDS
                if self._control_idle(channel)
            }
            self._control_state.apply_snapshot(snapshot, idle_channels)
            def update_widgets():
                if "brightness" in idle_channels:
                    if brightness["percent"] is not None:
                        self.brightness_scale.set_value(brightness["percent"])
                    self.brightness_value.set_text(
                        "—" if brightness["percent"] is None else f"{brightness['percent']} %"
                    )
                self.night_switch.set_active(night["enabled"] is True)
                if "temperature" in idle_channels and night["temperature"] is not None:
                    self.temperature_scale.set_value(night["temperature"])
                    self.temperature_value.set_text(f"{night['temperature']} K")
                if "gamma" in idle_channels and night["gamma"] is not None:
                    self.gamma_scale.set_value(night["gamma"])
                    self.gamma_value.set_text(f"Gamma {night['gamma']} %")
            self._control_state.synchronize(update_widgets)
            self.status_label.set_text("Todo listo" if brightness["available"] and night["available"]
                                       else "Algún control no está disponible")
            self._set_busy(False)

        def _set_busy(self, busy):
            self._busy = busy

        def _control_idle(self, channel):
            queue = self._control_queues.get(channel)
            return queue is None or not queue.active

        def _all_controls_idle(self):
            return all(self._control_idle(channel) for channel in self._control_state._FIELDS)

        def _queue_control(self, channel, value):
            if self.backends is None:
                return
            if channel not in self._control_queues:
                self._control_queues[channel] = LatestValueQueue(
                    lambda item, cancel_event, complete: self._launch_control(
                        channel, item, cancel_event, complete
                    ),
                    lambda item, outcome, obsolete: self._finish_control(
                        channel, item, outcome, obsolete
                    ),
                    cancel_active=channel == "brightness",
                )
            self._control_queues[channel].submit(value)

        def _launch_control(self, channel, value, cancel_event, complete):
            messages = {
                "brightness": f"Aplicando brillo al {value}%…",
                "temperature": f"Aplicando temperatura a {value} K…",
                "gamma": f"Aplicando gamma al {value}%…",
            }
            self.status_label.set_text(messages[channel])
            backend_bundle = self.backends

            def work():
                if backend_bundle is None:
                    raise OperationError("El backend no está disponible")
                deadline = time.monotonic() + CONTROL_DEADLINE
                if channel == "brightness":
                    result = _call_backend(
                        backend_bundle.brightness.set_percent,
                        value,
                        deadline=deadline,
                        should_stop=cancel_event.is_set,
                    )
                    return _confirmed_state(
                        result, backend_bundle.brightness.read_state, "La pantalla",
                        deadline=deadline,
                    )
                if channel == "temperature":
                    result = _call_backend(
                        backend_bundle.night_light.set_temperature,
                        value,
                        deadline=deadline,
                    )
                    return _confirmed_state(
                        result, backend_bundle.night_light.read_state, "La luz nocturna",
                        deadline=deadline,
                    )
                if channel == "gamma":
                    result = _call_backend(
                        backend_bundle.night_light.set_gamma,
                        value,
                        deadline=deadline,
                    )
                    return _confirmed_state(
                        result, backend_bundle.night_light.read_state, "La luz nocturna",
                        deadline=deadline,
                    )
                raise OperationError("Operación no disponible")

            run_worker(
                work,
                lambda result: complete(("success", result)),
                lambda error: complete(("error", error)),
            )

        def _finish_control(self, channel, _value, outcome, obsolete):
            if obsolete:
                self.status_label.set_text("Aplicando el último valor solicitado…")
                return
            kind, result = outcome
            if kind == "error":
                self._show_error(result)
                self._maybe_refresh_after_controls_idle()
                return
            self._control_state.confirm(
                channel,
                result,
                apply=lambda value: self._apply_confirmed_control(channel, value),
            )
            messages = {
                "brightness": "Brillo confirmado",
                "temperature": "Temperatura confirmada",
                "gamma": "Gamma confirmado",
            }
            self._show_toast(messages[channel])
            self._maybe_refresh_after_controls_idle()

        def _apply_confirmed_control(self, channel, value):
            if channel == "brightness":
                self.brightness_scale.set_value(value)
                self.brightness_value.set_text(f"{value} %")
            elif channel == "temperature":
                self.temperature_scale.set_value(value)
                self.temperature_value.set_text(f"{value} K")
            elif channel == "gamma":
                self.gamma_scale.set_value(value)
                self.gamma_value.set_text(f"Gamma {value} %")

        def _maybe_refresh_after_controls_idle(self):
            if self._control_state.take_deferred_refresh(
                controls_idle=self._all_controls_idle()
            ):
                self._refresh()

        def _show_toast(self, message):
            self.toast_overlay.add_toast(Adw.Toast.new(message))

        def _show_error(self, message):
            self._set_busy(False)
            self._show_toast(message)
            self.status_label.set_text(message)

        def _confirmed_operation(self, message):
            self._show_toast(message)
            self._refresh()

        def _start_backend(self, operation, value=None):
            if self.backends is None:
                return
            if operation in {"temperature", "gamma"}:
                self._queue_control(operation, value)
                return
            if self._busy:
                return
            self._set_busy(True)
            def work():
                if operation == "natural":
                    result = self.backends.night_light.set_natural()
                    return _confirmed_state(
                        result, self.backends.night_light.read_state, "La luz nocturna"
                    )
                raise OperationError("Operación no disponible")
            run_worker(work, lambda _result: self._confirmed_operation("Cambio confirmado"),
                       self._show_error)

        def _brightness_changed(self, scale):
            if not self._control_state.accepts_user_input:
                return
            target = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, round(scale.get_value())))
            self.brightness_value.set_text(f"{target} %")
            self._control_state.request("brightness", target)
            self._queue_control("brightness", target)

        def _step_brightness(self, direction):
            if self.backends is None:
                return
            target = self._control_state.step_brightness(direction)
            self._control_state.synchronize(
                lambda: self.brightness_scale.set_value(target)
            )
            self.brightness_value.set_text(f"{target} %")
            self._queue_control("brightness", target)

        def _night_toggled(self, _switch, _state):
            if not self._control_state.accepts_user_input:
                return False
            if not self._busy and self.backends is not None:
                self._set_busy(True)
                run_worker(lambda: toggle_night_light(self.backends),
                           lambda _result: self._confirmed_operation("Luz nocturna confirmada"),
                           self._show_error)
            return False

        def _temperature_changed(self, scale):
            if not self._control_state.accepts_user_input:
                return
            value = round(scale.get_value())
            self.temperature_value.set_text(f"{value} K")
            self._control_state.request("temperature", value)
            self._start_backend("temperature", value)

        def _gamma_changed(self, scale):
            if not self._control_state.accepts_user_input:
                return
            value = round(scale.get_value())
            self.gamma_value.set_text(f"Gamma {value} %")
            self._control_state.request("gamma", value)
            self._start_backend("gamma", value)

        def _save_schedule(self, _button):
            try:
                values = validate_schedule({
                    "day_time": self.day_entry.get_text(),
                    "day_temp": DAY_TEMP,
                    "night_time": self.night_entry.get_text(),
                    "night_temp": round(self.night_temp_spin.get_value()),
                }, clamp=False)
            except ValueError as error:
                self._show_error(str(error))
                return
            self._set_busy(True)
            run_worker(lambda: write_schedule(SCHEDULE_PATH, values),
                       lambda _result: (self._set_busy(False), self._show_toast("Horario guardado")),
                       self._show_error)

    globals()["VeilleuseWindow"] = VeilleuseWindow
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def on_activate(application):
        if not getattr(application, "window", None):
            application.window = VeilleuseWindow(application)
        application.window.present()

    app.connect("activate", on_activate)
    return app


def run_gui() -> int:
    app = create_application()
    return int(app.run([]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veilleuse")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--status", action="store_true")
    operations.add_argument("--toggle", action="store_true")
    operations.add_argument("--natural", action="store_true")
    operations.add_argument("--temperature", type=int, metavar="K")
    operations.add_argument("--gamma", type=int, metavar="PERCENT")
    operations.add_argument("--brightness", type=int, metavar="PERCENT")
    return parser


def cli_main(argv: list[str] | None = None, backends: BackendBundle | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if not any((args.status, args.toggle, args.natural, args.temperature is not None,
                args.gamma is not None, args.brightness is not None)):
        return run_gui()
    try:
        result = apply_cli_operation(backends or load_backends(), args)
    except (OperationError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(safe_error_message(error), file=sys.stderr)
        return 1
    if args.status:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
