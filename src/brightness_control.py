#!/usr/bin/python3
"""Safe, native brightness control for Omarchy/Hyprland."""
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

try:
  from ui_accessibility import set_range, set_status
except ModuleNotFoundError as error:
  if error.name != "ui_accessibility":
    raise
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from ui_accessibility import set_range, set_status

try:
  from brightness_utils import (
    apply_verified_step,
    clamp_percent,
    is_safe_brightness_change,
    limit_change,
    parse_brightness_info,
    plan_brightness_change,
  )
  from schedule_utils import STATE_LOCK, exclusive_lock
except ModuleNotFoundError as error:
  if error.name not in {"brightness_utils", "schedule_utils"}:
    raise
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from brightness_utils import (
    apply_verified_step,
    clamp_percent,
    is_safe_brightness_change,
    limit_change,
    parse_brightness_info,
    plan_brightness_change,
  )
  from schedule_utils import STATE_LOCK, exclusive_lock

APP_ID = "com.snowflake.Brightness"
COMMAND_TIMEOUT = 2.0
READ_ATTEMPTS = 2
RETRY_DELAY = 0.08


class BrightnessError(RuntimeError):
  """Raised when the brightness device cannot complete a safe operation."""

CSS = """
/* Design tokens — shared language with Night Light Control.
 * Surfaces and state colors follow the system theme; the amber ramp is
 * semantic (it represents emitted light) and works in light/dark modes. */
@define-color br_glow        #f2b25e;
@define-color br_glow_strong #e89a3f;
@define-color br_glow_soft   rgba(242, 178, 94, 0.15);
@define-color br_glow_line   rgba(242, 178, 94, 0.30);
@define-color br_glow_text   #ffd08f;
@define-color br_knob        #fff7ec;

window { background: @window_bg_color; }

.brightness-hero {
  background: linear-gradient(140deg,
    rgba(242, 178, 94, 0.20),
    rgba(242, 178, 94, 0.09) 48%,
    rgba(143, 184, 216, 0.07));
  border: 1px solid @br_glow_line;
  border-radius: 24px;
  padding: 24px;
}

.brightness-icon-wrap {
  background: @br_glow_soft;
  border: 1px solid @br_glow_line;
  border-radius: 999px;
  padding: 15px;
}

.brightness-icon { color: @br_glow_text; }

.brightness-value {
  font-size: 40px;
  font-weight: 800;
  transition: color 250ms ease;
}

.brightness-value.pending { color: @br_glow_text; }
.brightness-value.success { color: @success_color; }
.brightness-unit { font-size: 16px; opacity: 0.65; }

.control-card {
  background: @card_bg_color;
  border: 1px solid alpha(@borders, 0.65);
  border-radius: 18px;
  padding: 20px;
}

/* Ramp from near-dark to full glow — it reads as emitted light. */
.brightness-scale trough {
  min-height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg,
    rgba(242, 178, 94, 0.16),
    rgba(242, 178, 94, 0.45) 45%,
    @br_glow);
  outline: 1px solid alpha(@theme_fg_color, 0.06);
  outline-offset: -1px;
}

.brightness-scale slider {
  min-width: 22px;
  min-height: 22px;
  border-radius: 999px;
  background: @br_knob;
  border: 1px solid rgba(60, 40, 20, 0.22);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
  transition: box-shadow 200ms ease;
}

.brightness-scale slider:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45), 0 0 0 6px rgba(242, 178, 94, 0.18);
}

.brightness-level trough {
  min-height: 7px;
  border-radius: 999px;
  background: alpha(@theme_fg_color, 0.08);
}

.brightness-level progress {
  min-height: 7px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ffdca8, @br_glow);
}

.dim { opacity: 0.66; }
.feedback { font-size: 13px; }

.safety-note {
  background: alpha(@accent_color, 0.09);
  border: 1px solid alpha(@accent_color, 0.20);
  border-radius: 14px;
  padding: 12px 14px;
}
"""


def command(args):
  try:
    return subprocess.run(
      args, text=True, capture_output=True, check=False, timeout=COMMAND_TIMEOUT
    )
  except subprocess.TimeoutExpired as error:
    return subprocess.CompletedProcess(args, 124, error.stdout or "", str(error))
  except OSError as error:
    return subprocess.CompletedProcess(args, 127, "", str(error))


def get_brightness_info(device=None):
  args = ["brightnessctl", "-c", "backlight"]
  if device:
    args.extend(["-d", device])
  args.append("-m")
  result = command(args)
  if result.returncode != 0:
    raise RuntimeError(result.stderr.strip() or "No se pudo leer el brillo")
  return parse_brightness_info(result.stdout)


def set_brightness_step(device, adjustment):
  if adjustment not in {"1%+", "1%-"}:
    raise ValueError("Ajuste de brillo no permitido")
  if not device:
    raise ValueError("Dispositivo de brillo no válido")
  return command(["brightnessctl", "-c", "backlight", "-d", device, "set", adjustment])


def read_brightness_with_retry(device=None, allow_redetect=True):
  """Read a device, retrying transient failures and optionally re-detecting it."""
  candidates = [device]
  if device and allow_redetect:
    candidates.append(None)
  last_error = None
  for candidate in candidates:
    for attempt in range(READ_ATTEMPTS):
      try:
        return get_brightness_info(candidate)
      except (RuntimeError, ValueError) as error:
        last_error = error
        if attempt + 1 < READ_ATTEMPTS:
          time.sleep(RETRY_DELAY)
  message = str(last_error) if last_error else "No se encontró un dispositivo de brillo"
  raise BrightnessError(message)


def detect_brightness():
  """Detect the panel while sharing the lock with all other brightness clients."""
  with exclusive_lock(STATE_LOCK):
    return read_brightness_with_retry()


def perform_brightness_step(device, direction):
  """Serialize read -> step -> verification for one requested direction."""
  with exclusive_lock(STATE_LOCK):
    info = read_brightness_with_retry(device)

    def verify(candidate):
      try:
        return read_brightness_with_retry(candidate, allow_redetect=False)
      except BrightnessError:
        # A panel can briefly disappear after the write; re-detect without
        # writing again so a successful step can never be duplicated.
        return read_brightness_with_retry()

    return apply_verified_step(info, direction, set_brightness_step, verify)


class BrightnessWindow(Adw.ApplicationWindow):
  def __init__(self, app):
    super().__init__(application=app, title="Brillo")
    self.set_default_size(540, 470)
    self.set_size_request(300, 300)
    self.apply_timeout = None
    self.closed = False
    self.detection_in_flight = False
    self.worker_in_flight = False
    self.updating = False
    self.device = None
    self.pending_directions = []
    self.confirmed_percent = None

    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(
      self.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(title="Brillo", subtitle="Control seguro de pantalla"))
    self.recover_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    self.recover_button.set_tooltip_text("Volver a detectar el panel")
    self.recover_button.update_property(
      [Gtk.AccessibleProperty.LABEL], ["Volver a detectar el panel"]
    )
    self.recover_button.connect("clicked", self.on_recover_clicked)
    header.pack_end(self.recover_button)
    toolbar.add_top_bar(header)

    self.toast_overlay = Adw.ToastOverlay()
    scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    clamp = Adw.Clamp(maximum_size=620, tightening_threshold=500)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    content.set_margin_top(14)
    content.set_margin_bottom(18)
    content.set_margin_start(14)
    content.set_margin_end(14)
    clamp.set_child(content)
    scroll.set_child(clamp)
    self.toast_overlay.set_child(scroll)
    toolbar.set_content(self.toast_overlay)
    self.set_content(toolbar)

    hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                   css_classes=["brightness-hero"])
    hero_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
    icon_wrap = Gtk.Box(css_classes=["brightness-icon-wrap"], valign=Gtk.Align.CENTER)
    self.icon = Gtk.Image.new_from_icon_name("display-brightness-symbolic")
    self.icon.set_pixel_size(38)
    self.icon.add_css_class("brightness-icon")
    icon_wrap.append(self.icon)
    hero_top.append(icon_wrap)
    titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                     valign=Gtk.Align.CENTER, hexpand=True)
    titles.append(Gtk.Label(label="Encuentra tu punto cómodo", xalign=0,
                            css_classes=["title-1"]))
    titles.append(Gtk.Label(label="Ajusta la luz de forma gradual, sin saltos bruscos",
                            xalign=0, wrap=True, css_classes=["dim"]))
    hero_top.append(titles)
    hero.append(hero_top)
    value_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3,
                        valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
    self.value_label = Gtk.Label(label="—", css_classes=["brightness-value"])
    value_box.append(self.value_label)
    value_box.append(Gtk.Label(label="%", css_classes=["brightness-unit"],
                               valign=Gtk.Align.END))
    hero.append(value_box)
    content.append(hero)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13,
                   css_classes=["control-card"])
    card.append(Gtk.Label(label="Nivel de brillo", xalign=0, css_classes=["title-3"]))
    card.append(Gtk.Label(label="Arrastra el control. Cada tecla, rueda o clic avanza solo 1 %.",
                          xalign=0, wrap=True, css_classes=["dim"]))
    adjustment = Gtk.Adjustment(value=1, lower=1, upper=100,
                                step_increment=1, page_increment=1, page_size=0)
    self.scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                           adjustment=adjustment, draw_value=False, hexpand=True)
    self.scale.add_css_class("brightness-scale")
    self.scale.set_digits(0)
    set_range(self.scale, "Brillo de pantalla", 1, 100, 1, "1 %")
    self.scale.connect("change-value", self.on_change_request)
    self.scale.set_sensitive(False)
    card.append(self.scale)
    self.level = Gtk.ProgressBar(hexpand=True)
    self.level.add_css_class("brightness-level")
    self.level.set_fraction(0)
    card.append(self.level)
    limits = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    limits.append(Gtk.Label(label="1 %", xalign=0, hexpand=True, css_classes=["dim"]))
    limits.append(Gtk.Label(label="100 %", xalign=1, css_classes=["dim"]))
    card.append(limits)
    self.feedback_label = Gtk.Label(
      label="Buscando un panel de retroiluminación...",
      xalign=0,
      wrap=True,
      css_classes=["feedback", "dim"],
    )
    set_status(self.feedback_label, self.feedback_label.get_label(), busy=True)
    card.append(self.feedback_label)
    content.append(card)

    note = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                   css_classes=["safety-note"])
    note.append(Gtk.Image.new_from_icon_name("security-high-symbolic"))
    note_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    note_text.append(Gtk.Label(label="Ajuste protegido", xalign=0, css_classes=["heading"]))
    note_text.append(Gtk.Label(label="No hay botones de 25 %, 50 % o 100 % ni cambios instantáneos.",
                               xalign=0, wrap=True, css_classes=["dim"]))
    note.append(note_text)
    content.append(note)

    self.device_row = Adw.ActionRow(title="Panel interno", subtitle="Detectando dispositivo...")
    self.device_row.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
    self.backend_status = Gtk.Label(
      label="Buscando...",
      css_classes=["warning", "caption"],
    )
    self.device_row.add_suffix(self.backend_status)
    self._set_backend_status("Buscando...", "warning")
    device_group = Adw.PreferencesGroup()
    device_group.add(self.device_row)
    content.append(device_group)

    GLib.idle_add(self.start_detection)

  def toast(self, text):
    self.toast_overlay.add_toast(Adw.Toast.new(text))

  def _set_backend_status(self, text, style):
    self.backend_status.set_label(text)
    set_status(
      self.backend_status,
      text,
      busy=text.startswith(("Buscando", "Aplicando")),
    )
    for css_class in ("success", "error", "warning"):
      self.backend_status.remove_css_class(css_class)
    self.backend_status.add_css_class(style)

  def _set_feedback(self, text, style=None):
    self.feedback_label.set_label(text)
    set_status(self.feedback_label, text, busy=style == "pending")
    for css_class in ("success", "error", "pending"):
      self.feedback_label.remove_css_class(css_class)
    if style:
      self.feedback_label.add_css_class(style)

  def _set_busy(self, busy):
    self.recover_button.set_sensitive(not busy and not self.detection_in_flight)
    if busy:
      self._set_backend_status("Aplicando...", "warning")
      self._set_feedback("Aplicando un paso confirmado de 1 %...", "pending")
      self.value_label.add_css_class("pending")
      self.value_label.remove_css_class("success")
    elif self.device is not None:
      self._set_backend_status("Activo", "success")
      self.value_label.remove_css_class("pending")

  def on_change_request(self, scale, _scroll_type, requested):
    if self.closed or self.updating or self.detection_in_flight:
      return True
    current = scale.get_value()
    direction = 1 if requested > current else -1 if requested < current else 0
    if direction == 0 or self.device is None:
      return True
    safe_next = limit_change(current, requested)
    if safe_next == clamp_percent(current):
      return True
    self.updating = True
    scale.set_value(safe_next)
    self.updating = False
    self.value_label.set_label(str(clamp_percent(safe_next)))
    set_range(self.scale, "Brillo de pantalla", 1, 100, safe_next,
              f"{clamp_percent(safe_next)} %")
    self.value_label.add_css_class("pending")
    self.value_label.remove_css_class("success")
    self._set_feedback(
      f"Pendiente: {'subir' if direction > 0 else 'bajar'} 1 %",
      "pending",
    )
    self.pending_directions.append(direction)
    if self.apply_timeout is None and not self.worker_in_flight:
      self.apply_timeout = GLib.timeout_add(70, self.start_apply_worker)
    return True

  def sync_value(self, percent, confirmed=True):
    self.updating = True
    if percent is None:
      self.value_label.set_label("—")
      self.level.set_fraction(0)
    else:
      percent = clamp_percent(percent)
      self.scale.set_value(percent)
      self.value_label.set_label(str(percent))
      set_range(self.scale, "Brillo de pantalla", 1, 100, percent, f"{percent} %")
      self.level.set_fraction(percent / 100)
      if confirmed:
        self.confirmed_percent = percent
    self.updating = False
    if confirmed:
      self.value_label.remove_css_class("pending")
      self.value_label.add_css_class("success")
      self._set_feedback(f"Confirmado por el dispositivo: {percent} %", "success")
    else:
      self.value_label.remove_css_class("success")

  def mark_unavailable(self):
    self.device = None
    self.pending_directions.clear()
    self.scale.set_sensitive(False)
    self.device_row.set_subtitle("Dispositivo no disponible")
    self._set_backend_status("No disponible", "error")
    self._set_feedback("No se encontró el panel. Pulsa actualizar para reintentar.", "error")
    self.recover_button.set_sensitive(not self.closed)

  def mark_available(self, info):
    self.device = info["device"]
    self.device_row.set_subtitle(info["device"])
    self.scale.set_sensitive(True)
    self._set_backend_status("Activo", "success")

  def schedule_next_value(self):
    self.apply_timeout = None
    if self.pending_directions and self.device is not None and not self.worker_in_flight:
      self.apply_timeout = GLib.timeout_add(70, self.start_apply_worker)

  def on_recover_clicked(self, _button):
    if self.worker_in_flight:
      self.toast("Espera a que termine el ajuste actual")
      return
    self.start_detection()

  def start_detection(self, *_args):
    if self.closed or self.detection_in_flight or self.worker_in_flight:
      return GLib.SOURCE_REMOVE
    if self.apply_timeout:
      GLib.source_remove(self.apply_timeout)
      self.apply_timeout = None
    self.pending_directions.clear()
    self.detection_in_flight = True
    self.scale.set_sensitive(False)
    self.recover_button.set_sensitive(False)
    self._set_backend_status("Buscando...", "warning")
    self._set_feedback("Buscando un panel de retroiluminación...", "pending")
    threading.Thread(target=self._detection_worker, daemon=True).start()
    return GLib.SOURCE_REMOVE

  def _detection_worker(self):
    try:
      info = detect_brightness()
      error = None
    except (BrightnessError, RuntimeError, ValueError, OSError) as caught:
      info = None
      error = str(caught)
    GLib.idle_add(self._finish_detection, info, error)

  def _finish_detection(self, info, error):
    if self.closed:
      return GLib.SOURCE_REMOVE
    self.detection_in_flight = False
    self.recover_button.set_sensitive(True)
    if info is None:
      self.mark_unavailable()
      self.sync_value(self.confirmed_percent, confirmed=False)
      self.toast("No se encontró un dispositivo de brillo")
      return GLib.SOURCE_REMOVE
    self.mark_available(info)
    self.sync_value(info["percent"])
    if error:
      self.toast("Dispositivo recuperado")
    return GLib.SOURCE_REMOVE

  def start_apply_worker(self, *_args):
    self.apply_timeout = None
    if self.closed or self.worker_in_flight or self.detection_in_flight:
      return GLib.SOURCE_REMOVE
    if not self.pending_directions or self.device is None:
      return GLib.SOURCE_REMOVE
    direction = self.pending_directions.pop(0)
    device = self.device
    self.worker_in_flight = True
    self._set_busy(True)
    threading.Thread(
      target=self._apply_worker,
      args=(device, direction),
      daemon=True,
    ).start()
    return GLib.SOURCE_REMOVE

  def _apply_worker(self, device, direction):
    try:
      result = perform_brightness_step(device, direction)
      error = None
    except (BrightnessError, RuntimeError, ValueError, OSError) as caught:
      result = None
      error = str(caught)
    GLib.idle_add(self._finish_apply, result, error)

  def _finish_apply(self, result, error):
    if self.closed:
      return GLib.SOURCE_REMOVE
    self.worker_in_flight = False
    if result is None:
      self.pending_directions.clear()
      self.mark_unavailable()
      self.sync_value(self.confirmed_percent, confirmed=False)
      self.toast(error or "No se pudo verificar el brillo")
      return GLib.SOURCE_REMOVE

    self.mark_available(result)
    self._set_busy(False)
    self.sync_value(result["percent"])
    if not result["changed"]:
      self._set_feedback(f"Límite alcanzado: {result['percent']} %", "success")
    self.schedule_next_value()
    return GLib.SOURCE_REMOVE

  def apply_value(self, direction=None):
    """Dispatch the real window to a worker and retain the old test hook."""
    if hasattr(self, "worker_in_flight"):
      return self.start_apply_worker()
    return BrightnessWindow._apply_value_compat(self, direction)

  def _apply_value_compat(self, direction=None):
    """Synchronous compatibility path for callers using the old callback."""
    queued = direction is None
    if queued:
      if not self.pending_directions:
        self.apply_timeout = None
        return GLib.SOURCE_REMOVE
      direction = self.pending_directions.pop(0)
    if not self.device:
      self.apply_timeout = None
      return GLib.SOURCE_REMOVE
    try:
      result = perform_brightness_step(self.device, direction)
    except (BrightnessError, RuntimeError, ValueError, OSError) as error:
      self.toast(str(error))
      if hasattr(self, "mark_unavailable"):
        self.mark_unavailable()
      if hasattr(self, "confirmed_percent"):
        self.sync_value(self.confirmed_percent, confirmed=False)
      self.apply_timeout = None
      return GLib.SOURCE_REMOVE
    self.sync_value(result["percent"])
    if queued:
      self.schedule_next_value()
    else:
      self.apply_timeout = None
    return GLib.SOURCE_REMOVE

  def stop_timers(self):
    self.closed = True
    if self.apply_timeout:
      GLib.source_remove(self.apply_timeout)
      self.apply_timeout = None
    self.pending_directions.clear()


class BrightnessApp(Adw.Application):
  def __init__(self):
    super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

  def do_activate(self):
    if not getattr(self, "window", None):
      self.window = BrightnessWindow(self)
      self.window.connect("close-request", self.on_window_close)
    self.window.present()

  def on_window_close(self, _window):
    self.window.stop_timers()
    self.window = None
    return False


if __name__ == "__main__":
  raise SystemExit(BrightnessApp().run())
