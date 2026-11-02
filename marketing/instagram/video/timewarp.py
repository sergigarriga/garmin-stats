"""Hace que la animación siga a la voz.

Cada escena de la animación empieza en un segundo fijo (tiempo de animación). La voz dice cada parte del guion en su
propio momento (tiempo real). Con unos "anclajes" [(tiempo real, tiempo de animación), ...]:
- si la voz tarda más que la escena, la escena se reproduce a velocidad normal, se queda quieta (lo ya animado sigue en
  pantalla) y hace su salida justo antes de que empiece la parte siguiente;
- si la voz tarda menos, la escena se acelera un poco.
Las animaciones de ambiente (manchas, latidos, cintas) usan el tiempo real, así nunca se ven congeladas.
"""

from __future__ import annotations

EXIT = 0.4  # segundos de la salida de cada escena, que siempre se reproducen enteros


def warp(t: float, anchors: list[tuple[float, float]]) -> float:
    """Tiempo de animación para el tiempo real t. anchors: [(real, animación), ...] crecientes, el primero (0, 0)."""
    if t <= anchors[0][0]:
        return anchors[0][1]
    for (r0, a0), (r1, a1) in zip(anchors, anchors[1:]):
        if t <= r1:
            real, anim = r1 - r0, a1 - a0
            if real <= 0:
                return a1
            if real < anim:  # la voz va más rápida que la escena: se acelera
                return a0 + (t - r0) * anim / real
            x = min(EXIT, anim * 0.3)
            if t - r0 <= anim - x:
                return a0 + (t - r0)
            if t >= r1 - x:
                return a1 - (r1 - t)
            return a0 + anim - x  # pausa: la escena ya está entera en pantalla
    return anchors[-1][1] + (t - anchors[-1][0])


def unwarp(a: float, anchors: list[tuple[float, float]]) -> float:
    """Tiempo real en el que la animación llega al instante a (para colocar los efectos de sonido)."""
    lo, hi = 0.0, anchors[-1][0] + 60
    for _ in range(60):
        mid = (lo + hi) / 2
        if warp(mid, anchors) < a:
            lo = mid
        else:
            hi = mid
    return hi
