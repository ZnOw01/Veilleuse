# Veilleuse

Plugin nativo de **Omarchy Quattro (Omarchy 4)** para controlar brillo, luz nocturna y horarios desde la barra de Omarchy Shell.

Veilleuse no abre una aplicación GTK ni reemplaza bindings, OSD o servicios del sistema. Su interfaz está escrita en QML/Quickshell y reutiliza las superficies nativas de Omarchy para elegir el monitor enfocado, operar pantallas internas/DDC/Apple y refrescar el estado de Nightlight.

## Funciones

- Widget compacto en la barra con popup integrado al diseño de Omarchy Shell.
- Brillo del monitor enfocado con readback real.
- Cada solicitud de brillo aplica **como máximo un punto porcentual** (`+1%` o `1%-`), aunque el deslizador se arrastre mucho más lejos.
- Luz nocturna mediante el IPC real de `hyprsunset`.
- Temperatura de 2500 a 6500 K y gamma de 0 a 100 %.
- Edición conservadora del horario día/noche.
- Escritura atómica de `~/.config/hypr/hyprsunset.conf`, preservando comentarios, permisos, perfiles ajenos y una copia `.bak`.
- Navegación con ratón y teclado (`j/k`, flechas y `h/l`).
- Estado fail-closed: la interfaz no confirma valores que el backend no haya releído.
- Sin telemetría, cuentas ni red en tiempo de ejecución.

## Requisitos

- Omarchy Quattro / Omarchy 4.
- Omarchy Shell con soporte de plugins `bar-widget`.
- `hyprsunset` configurado por Omarchy.
- Python del sistema (`/usr/bin/python3`, solo biblioteca estándar).

No se mantiene compatibilidad con Omarchy 3, Waybar ni otros escritorios.

## Instalación

> Los plugins de Omarchy se ejecutan sin sandbox dentro del shell. Revisa el código antes de habilitar repositorios de terceros.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

El plugin queda en `~/.config/omarchy/plugins/io.github.ZnOw01.veilleuse/` y aparece en la sección derecha de la barra. No instala servicios ni modifica archivos propiedad de Omarchy.

Para una copia local de desarrollo:

```bash
git clone https://github.com/ZnOw01/veilleuse.git
omarchy plugin validate ./veilleuse
omarchy plugin add "file://$PWD/veilleuse" --enable --yes
```

## Actualizar

```bash
omarchy plugin update io.github.ZnOw01.veilleuse --yes
```

## Deshabilitar o eliminar

```bash
omarchy plugin disable io.github.ZnOw01.veilleuse
omarchy plugin remove io.github.ZnOw01.veilleuse --yes
```

La eliminación del plugin **no borra** `~/.config/hypr/hyprsunset.conf` ni su copia de seguridad.

## Seguridad del brillo

El valor del slider representa intención. Antes de escribir, el helper relee el brillo físico del monitor enfocado y elige un único token relativo permitido. Después relee el dispositivo y rechaza cualquier transición observada mayor de un punto. De esta forma, una UI desactualizada o un arrastre amplio no se convierten en un salto físico grande.

## Desarrollo

En Omarchy:

```bash
./scripts/check.sh
```

El gate ejecuta pruebas Python y Node, validación del manifest, `qmllint` cuando está disponible y comprobaciones de empaquetado limpio.

## Marketplace

El repositorio cumple el formato requerido por [Omarchy Plugin Marketplace](https://omarchyplugins.com/publish.html): `manifest.json` en raíz, ID estable, entrypoint `bar-widget`, licencia y README. Para publicar en el catálogo se crea un issue **Submit Plugin** en `HANCORE-linux/omarchy-plugin-marketplace` después de que el repositorio y CI estén disponibles públicamente.

## Licencia

MIT © 2026 ZnOw01.
