"""Small GTK accessibility adapters shared by the application windows."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def set_range(widget, label, minimum, maximum, value, value_text):
  """Expose a slider/spin control's name, range and current value."""
  widget.update_property(
    [
      Gtk.AccessibleProperty.LABEL,
      Gtk.AccessibleProperty.VALUE_MIN,
      Gtk.AccessibleProperty.VALUE_MAX,
      Gtk.AccessibleProperty.VALUE_NOW,
      Gtk.AccessibleProperty.VALUE_TEXT,
    ],
    [str(label), float(minimum), float(maximum), float(value), str(value_text)],
  )


def set_description(widget, description, invalid=False):
  """Expose supporting validation text and whether a field is invalid."""
  widget.update_property(
    [Gtk.AccessibleProperty.DESCRIPTION],
    [str(description)],
  )
  widget.update_state([Gtk.AccessibleState.INVALID], [int(bool(invalid))])


def set_status(widget, text, busy=False):
  """Mark dynamic feedback as a status region and update its busy state."""
  widget.set_accessible_role(Gtk.AccessibleRole.STATUS)
  widget.update_property(
    [Gtk.AccessibleProperty.LABEL],
    [str(text)],
  )
  widget.update_state([Gtk.AccessibleState.BUSY], [bool(busy)])
