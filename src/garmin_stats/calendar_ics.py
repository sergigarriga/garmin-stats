"""El plan como calendario (iCalendar, RFC 5545) para suscribirse desde Google Calendar, el iPhone u Outlook.

Cada sesión es un evento de día completo con lo que hay que hacer: distancia, ritmos (calculados con tus ritmos
de referencia actuales) y los pasos del entreno. Los días de descanso no se publican.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from .training import mmss, resolve_step_pace

TYPE_LABEL = {"easy": "Suave", "long": "Tirada larga", "tempo": "Ritmo", "intervals": "Series", "race": "Carrera",
              "strength": "Gimnasio", "cross": "Cruzado", "swim": "Natación", "rest": "Descanso"}
KIND = {"warmup": "Calentamiento", "active": "", "recovery": "Recuperación", "cooldown": "Vuelta a la calma", "rest": "Descanso"}


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Líneas de 75 bytes como mucho; las siguientes empiezan con un espacio (sin partir caracteres UTF-8)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode())
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def step_text(st: dict, refs: dict | None) -> str:
    d = st.get("duration")
    v = st.get("value")
    if d == "distance" and v:
        what = f"{_num(v)} km" if v >= 1 else f"{round(v * 1000)} m"
    elif d == "time" and v:
        what = f"{_num(v)} min"
    else:
        what = "hasta pulsar vuelta"
    bits = []
    rng = resolve_step_pace(st, refs) if st.get("target") == "pace" else None
    if rng:
        bits.append(f"{mmss(rng[0])}-{mmss(rng[1])} /km")
    elif st.get("target") == "hr" and st.get("hr_low") and st.get("hr_high"):
        bits.append(f"{st['hr_low']}-{st['hr_high']} lpm")
    name = st.get("name") or KIND.get(st.get("kind"), "")
    return f"{name}: {what}" + (f" a {bits[0]}" if bits else "")


def workout_lines(workout: list | None, refs: dict | None) -> list[str]:
    out = []
    for b in workout or []:
        steps = [step_text(s, refs) for s in b.get("steps") or []]
        if (b.get("repeat") or 1) > 1:
            out.append(f"{b['repeat']} x [" + " + ".join(steps) + "]")
        else:
            out += steps
    return out


def strength_lines(items: list | None) -> list[str]:
    out = []
    for it in items or []:
        reps = f"{it['seconds']} s" if it.get("seconds") else f"{it.get('reps')} rep."
        kg = f" con {_num(it['weight_kg'])} kg" if it.get("weight_kg") else ""
        out.append(f"{it.get('label')}: {it.get('sets')} x {reps}{kg}, descanso {it.get('rest_s')} s")
    return out


def build(plan: dict | None, refs: dict | None = None, name: str = "Plan de entreno") -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//garmin-stats//plan//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc(name)}", "X-WR-TIMEZONE:Europe/Madrid",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    seen: dict[str, int] = {}
    for w in (plan or {}).get("weeks") or []:
        for s in w.get("sessions") or []:
            if s.get("type") == "rest":
                continue
            d = date.fromisoformat(s["date"])
            key = f"{s['date']}-{s.get('type')}"
            seen[key] = seen.get(key, 0) + 1
            uid = hashlib.sha1(f"{key}-{seen[key]}".encode()).hexdigest()[:20] + "@garmin-stats"
            planned = " · ".join(x for x in (
                f"{_num(s['distance_km'])} km" if s.get("distance_km") else "",
                f"{s['duration_min']} min" if s.get("duration_min") else "", s.get("target") or "") if x)
            body = [x for x in (planned, s.get("description") or "") if x]
            steps = workout_lines(s.get("workout"), refs) or strength_lines(s.get("strength"))
            if steps:
                body += ["", "Entreno:"] + [f"• {x}" for x in steps]
            summary = f"{TYPE_LABEL.get(s.get('type'), 'Entreno')}: {s.get('title', '')}"
            for ln in ("BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
                       f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                       f"SUMMARY:{_esc(summary)}", f"DESCRIPTION:{_esc(chr(10).join(body))}",
                       "TRANSP:TRANSPARENT", "END:VEVENT"):
                lines += _fold(ln)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
