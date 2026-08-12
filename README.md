# Luz nocturna para Omarchy

Control gráfico nativo y personalizable para **hyprsunset** en Omarchy/Hyprland.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![GTK](https://img.shields.io/badge/GTK-4-7FE719?logo=gtk&logoColor=black)
![Wayland](https://img.shields.io/badge/Wayland-Hyprland-58E1FF)
![License](https://img.shields.io/badge/license-MIT-green)

## Características

- Interruptor manual para activar o desactivar la luz cálida.
- Selector visual manual con gradiente entre 2500 K y 5000 K y previsualización en vivo.
- Referencia diurna independiente de 5900 K a 6500 K, usada solo si se desactiva el color natural.
- Estado natural autoritativo mediante `identity = true`, sin confundir una lectura térmica antigua con el color actual.
- Escala de intensidad relativa para comparar el filtro seleccionado, separada de una medición física del panel.
- Control separado de **brillo percibido** de 50–100% mediante la API de gamma de hyprsunset.
- El gamma afecta al brillo percibido y puede reducir la precisión del color; no representa intensidad de luz azul.
- Horario totalmente editable desde la app: comienzo, fin y temperaturas nocturna/diurna.
- Escritura atómica del horario con copia de respaldo y validación `HH:MM`.
- Resumen visual de estado, temperatura actual y línea temporal diaria.
- Restauración inmediata del perfil correspondiente a la hora actual.
- Estado de Waybar con temperatura activa, color natural, apagado o indisponible.
- CLI `night-light` con estado, temperatura, gamma, color natural, reset y ciclo rápido.
- Atajo global `Super + Ctrl + N`.
- Diseño GTK 4/Libadwaita adaptable, con iconos simbólicos, tarjetas y estados accesibles.
- Aplicación **Brillo** con deslizador nativo y cambios estrictamente limitados a 1 % por evento.
- Detección automática del dispositivo de clase `backlight`; el control se deshabilita si no está disponible.
- Sin botones ni acciones de un clic que salten a 25 %, 50 % o 100 %.
- Integración de Brillo con el módulo `backlight` de Waybar: clic abre el control y la rueda ajusta 1 % mediante un helper seguro.
- En equipos con varios backlights puede fijarse el dispositivo con `NIGHT_LIGHT_BACKLIGHT_DEVICE`.
- Sin telemetría, red, cuentas ni privilegios administrativos.

## Horario incluido

La plantilla incluida activa **3500 K a las 15:30** y usa `identity = true` a las **06:00** para recuperar el color natural real. La interfaz conserva una referencia diurna configurable de **5900–6500 K**, pero con color natural activo no la envía a `hyprsunset`, por lo que no aplica un filtro durante el día. Todo puede editarse desde la aplicación y los horarios siguen la zona horaria configurada en el sistema. Un `hyprsunset.conf` existente no se reemplaza.

## Estado e intensidad

`identity = true` es el estado autoritativo para el color natural. Cuando está activo, una temperatura que `hyprsunset` aún reporte puede ser una lectura residual y no debe ganar a `identity`.

Los valores en **K** son parámetros de temperatura de color para `hyprsunset`, no porcentajes físicos ni una medición de luz azul. La aplicación muestra una escala comparativa relativa del filtro manual de 2500 K a 5000 K: una temperatura más baja representa más filtro en esa escala, mientras que `identity` siempre representa 0 % de filtro añadido. La referencia diurna de 5900–6500 K es independiente de esta selección manual.

El control de gamma usa la lectura y confirmación de `hyprctl hyprsunset gamma`, con el rango visible de 50–100% y un máximo backend de 200%. Se conserva en una preferencia separada de la temperatura y no modifica el horario personal de `hyprsunset`.

## Requisitos

- Omarchy o Arch Linux con Hyprland
- `hyprsunset`, `brightnessctl` y `desktop-file-validate`
- Python 3.11+ con PyGObject en el mismo intérprete
- GTK 4 y Libadwaita
- Waybar (opcional para el botón superior)

En Arch/Omarchy normalmente ya están disponibles como `hyprsunset`, `brightnessctl`, `python-gobject`, `gtk4` y `libadwaita`.

## Instalación

```bash
./install.sh
```

El instalador copia las dos aplicaciones y sus módulos, incluido `hyprsunset_backend.py`, al perfil del usuario, registra los lanzadores gráficos y habilita `hyprsunset.service`. No necesita `sudo`. La integración de Waybar e Hyprland se aplica de forma idempotente cuando detecta la configuración de Omarchy.

## Uso

- Busca **Luz nocturna** en el lanzador de aplicaciones.
- Busca **Brillo** para abrir el deslizador seguro de la pantalla.
- El módulo de Waybar muestra los K activos, `Natural`, `Off` o `No disponible`.
- Haz clic en el módulo de Waybar para recorrer 2700 → 3500 → 4200 K → natural; clic central abre la app.
- Pulsa el porcentaje de brillo en Waybar para abrir **Brillo**; usa la rueda para ajustar 1 %.
- Usa `~/.local/bin/night-light --status` para consultar JSON o `--temperature 3500`, `--gamma 75`, `--natural`, `--reset-gamma` y `--cycle` para operar.
- Pulsa `Super + Ctrl + N` desde cualquier aplicación.

## Desarrollo y comprobación

```bash
./scripts/check.sh
```

## Desinstalación

```bash
./uninstall.sh
```

El desinstalador elimina los binarios, el lanzador y las integraciones de Waybar/Hyprland creadas por la app. Por seguridad no borra tu horario personal de `~/.config/hypr/hyprsunset.conf`.

## Privacidad

Los componentes solo usan herramientas locales (`hyprctl`, `systemctl --user`, `brightnessctl`, `notify-send`, la base de lanzadores y el reinicio de Waybar). No realizan conexiones de red ni recopilan información.

## Licencia

MIT.
