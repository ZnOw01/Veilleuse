# Veilleuse

Plugin de **Omarchy Quattro** para controlar brillo, luz nocturna y horarios desde la barra.

![Veilleuse](preview.png)

## Funciones

- Brillo del monitor enfocado, limitado a un punto por operación y confirmado mediante readback.
- Luz nocturna de 2500 a 5000 K y gamma de 0 a 100 %.
- Horario día/noche con actualización atómica de `~/.config/hypr/hyprsunset.conf`; preserva comentarios, permisos, perfiles ajenos y una copia `.bak`.
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

## Desarrollo

```bash
git clone https://github.com/ZnOw01/veilleuse.git
cd veilleuse
omarchy plugin validate .
./scripts/check.sh
```

## Licencia

MIT © 2026 ZnOw01.
