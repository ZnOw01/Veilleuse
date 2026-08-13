# Veilleuse

Plugin de **Omarchy Quattro** para controlar brillo, luz nocturna y horarios desde la barra.

![Veilleuse](preview.png)

## Funciones

- Brillo del monitor enfocado, limitado a un punto por operación y confirmado mediante readback.
- Luz nocturna de 2500 a 6500 K y gamma de 0 a 100 %.
- Horario día/noche con actualización atómica de `~/.config/hypr/hyprsunset.conf`; preserva comentarios, permisos, perfiles ajenos y una copia `.bak`.
- Atajo de teclado opcional y reversible en `bindings.lua` (instalación manual, nunca automática).
- Navegación con ratón, flechas y `j/k/h/l`.

## Requisitos

- `hyprsunset` configurado por Omarchy.
- `/usr/bin/python3`.

## Instalación

> Los plugins se ejecutan sin sandbox dentro de Omarchy Shell. Revisa el código antes de habilitarlos.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

## Mantenimiento

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy plugin disable io.github.znow01.veilleuse
omarchy plugin remove io.github.znow01.veilleuse --yes
```

La eliminación preserva `~/.config/hypr/hyprsunset.conf` y su copia de seguridad.

## Atajos de teclado (opcional)

Veilleuse **nunca instala atajos automáticamente**. Solo se toca
`~/.config/hypr/bindings.lua` con un comando explícito:

```bash
./scripts/veilleuse-control shortcut install --keys "SUPER, V"
./scripts/veilleuse-control shortcut status
./scripts/veilleuse-control shortcut remove
```

La instalación valida las teclas, detecta colisiones con otros enlaces y edita
únicamente un bloque marcado `-- >>> Veilleuse shortcut >>>`. Como
`bindings.lua` se ejecuta como Lua en Omarchy 4, el bloque usa la sintaxis
`o.bind` del shell:

```lua
-- >>> Veilleuse shortcut >>>
o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
-- <<< Veilleuse shortcut <<<
```

El comando es fijo (`omarchy-shell -q io.github.znow01.veilleuse toggleNightlight`).
La instalación guarda una única copia `bindings.lua.bak` del original y preserva el modo del archivo.
La eliminación revierte el archivo a su contenido previo sin tocar nada más y, si queda vacío, elimina el archivo.
Ambos intentan recargar `hyprctl` cuando está disponible.

## Desarrollo

```bash
git clone https://github.com/ZnOw01/veilleuse.git
cd veilleuse
omarchy plugin validate .
./scripts/check.sh
```

## Licencia

MIT © 2026 ZnOw01.
