#!/usr/bin/python3
"""Pure brightness-device parsing shared by GTK and Waybar helpers."""

from __future__ import annotations

import os


def clamp_percent(value):
    return max(1, min(100, int(round(value))))


def parse_brightness_info(text):
    devices = []
    preferred = os.environ.get("NIGHT_LIGHT_BACKLIGHT_DEVICE", "")
    for line in text.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 5 or fields[1] != "backlight" or not fields[3].endswith("%"):
            continue
        try:
            current = int(fields[2])
            maximum = int(fields[4])
            percent = int(fields[3][:-1])
        except ValueError:
            continue
        if not fields[0] or maximum <= 0 or current < 0:
            continue
        devices.append({
            "device": fields[0],
            "class": fields[1],
            "current": current,
            "percent": clamp_percent(percent),
            "maximum": maximum,
        })
    if not devices:
        raise ValueError("Salida de brightnessctl no reconocida")
    return max(
        devices,
        key=lambda info: (
            info["device"] == preferred if preferred else False,
            info["percent"] > 0,
            info["maximum"],
            info["current"],
        ),
    )


def plan_brightness_change(info, direction):
    current = clamp_percent(info["percent"])
    if direction > 0 and current < 100:
        return current + 1, "1%+"
    if direction < 0 and current > 1:
        return current - 1, "1%-"
    return current, None


def is_safe_brightness_change(before, after, direction):
    """Return whether verification observed at most the requested 1% step."""
    before_percent = clamp_percent(before["percent"])
    after_percent = clamp_percent(after["percent"])
    delta = after_percent - before_percent
    if direction > 0:
        return 0 <= delta <= 1
    if direction < 0:
        return -1 <= delta <= 0
    return delta == 0


def apply_verified_step(info, direction, apply, verify):
    """Apply one relative step through injected I/O and return verified data."""
    target, adjustment = plan_brightness_change(info, direction)
    if adjustment is None:
        return {
            "device": info["device"],
            "percent": target,
            "changed": False,
        }

    result = apply(info["device"], adjustment)
    if result is None or result.returncode != 0:
        raise RuntimeError("No se pudo cambiar el brillo")
    verified = verify(info["device"])
    if verified["device"] != info["device"]:
        raise RuntimeError("El dispositivo de brillo cambió durante el ajuste")
    if not is_safe_brightness_change(info, verified, direction):
        raise RuntimeError("La verificación detectó un salto de brillo mayor de 1 %")
    return {
        "device": verified["device"],
        "percent": clamp_percent(verified["percent"]),
        "changed": True,
    }


def limit_change(current, requested):
    current = clamp_percent(current)
    requested = clamp_percent(requested)
    if requested > current:
        return min(requested, current + 1)
    if requested < current:
        return max(requested, current - 1)
    return current
