# Veilleuse

Plugin nativo de **Omarchy Quattro (Omarchy 4)** para controlar brillo, luz nocturna y horarios desde la barra de Omarchy Shell.

La interfaz QML/Quickshell reutiliza las superficies nativas de Omarchy para el monitor enfocado, pantallas internas/DDC/Apple y Nightlight. No abre una aplicación GTK ni reemplaza bindings, OSD o servicios del sistema.

## Funciones

- Widget de barra con popup integrado a Omarchy Shell.
- Brillo del monitor enfocado con readback real; cada solicitud aplica como máximo un punto porcentual (`+1%` o `1%-`).
- Luz nocturna mediante el IPC de `hyprsunset`, con temperatura de 2500 a 6500 K y gamma de 0 a 100 %.
- Horario día/noche con escritura atómica de `~/.config/hypr/hyprsunset.conf`; preserva comentarios, permisos, perfiles ajenos y una copia `.bak`.
- Navegación con ratón, `j/k`, flechas y `h/l`.
- Estado fail-closed: la interfaz solo confirma valores releídos del backend.
- Sin telemetría, cuentas ni red en tiempo de ejecución.

## Requisitos

- Omarchy Quattro (Omarchy 4) con soporte para plugins `bar-widget`.
- `hyprsunset` configurado por Omarchy.
- `/usr/bin/python3` (solo biblioteca estándar).

No es compatible con Omarchy 3, Waybar ni otros escritorios.

## Instalación

> Los plugins de Omarchy se ejecutan sin sandbox dentro del shell. Revisa el código antes de habilitar repositorios de terceros.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

Se instala en `~/.config/omarchy/plugins/io.github.znow01.veilleuse/`, aparece en la sección derecha de la barra y no instala servicios ni modifica archivos de Omarchy.

Para desarrollo local:

```bash
git clone https://github.com/ZnOw01/veilleuse.git
omarchy plugin validate ./veilleuse
omarchy plugin add "file://$PWD/veilleuse" --enable --yes
```

## Mantenimiento

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy plugin disable io.github.znow01.veilleuse
omarchy plugin remove io.github.znow01.veilleuse --yes
```

La eliminación no borra `~/.config/hypr/hyprsunset.conf` ni su copia de seguridad.

## Seguridad del brillo

El slider expresa intención. Antes de escribir, el helper relee el brillo físico y elige un único token relativo permitido; después vuelve a leer y rechaza transiciones mayores de un punto. Así, una UI desactualizada o un arrastre amplio no provoca un salto físico grande.

## Desarrollo

```bash
./scripts/check.sh
```

El gate ejecuta pruebas Python y Node, valida el manifest, ejecuta `qmllint` cuando está disponible y comprueba que el paquete esté limpio.

## Licencia

MIT © 2026 ZnOw01.
