"""Google Health como fuente de datos (para quien no tiene Garmin).

La persona conecta su cuenta con OAuth (scopes de solo lectura) y aquí se leen sus datos de la Google Health API v4
(https://health.googleapis.com). Lo descargado se guarda en el mismo almacén y con la misma forma que los datos de
Garmin (daily_summary, sleep, hrv, weight, activity, heart_rate), así el informe y la web no cambian.

Qué se lee: entrenos, pasos, distancia, calorías, minutos en zona activa, pulso en reposo, HRV, sueño, peso, VO2max
y el pulso de los últimos días. Lo que Google no tiene (Body Battery, estrés, FIT con series y ruta) se queda vacío,
igual que con un reloj que no lo mide. Cada bloque es opcional: un permiso que no se dio se salta sin fallar.
Solo usa la librería estándar.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger(__name__)

API = "https://health.googleapis.com/v4/users/me"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPE_BASE = "https://www.googleapis.com/auth/googlehealth."
SCOPES = [SCOPE_BASE + s for s in ("activity_and_fitness.readonly", "health_metrics_and_measurements.readonly",
                                     "sleep.readonly")]
LINK_URL = "https://fitbit.google.com/auth/signup"  # alta en Google Health si la cuenta aún no está enlazada

HISTORY_DAYS = 730   # la primera vez se bajan 2 años
REFRESH_DAYS = 3     # días que se vuelven a pedir siempre (el reloj sincroniza tarde)
INTRADAY_DAYS = 7    # pulso a lo largo del día: solo la última semana
CHUNK_DAYS = 90      # tramo máximo de los resúmenes diarios (dailyRollUp)
CAL_CHUNK_DAYS = 14  # total-calories admite como mucho 14 días por petición
RETRY_STATUS = {429, 500, 502, 503, 504}
DAILY_TYPES = {"steps", "distance", "active-energy-burned", "active-zone-minutes", "total-calories",
               "daily-resting-heart-rate"}

TZ_NAME = "Europe/Madrid"  # "hoy" de la app (Lambda va en UTC)


def today_local() -> date:
    """Fecha de hoy en Madrid. Sin base de zonas horarias, la hora local del sistema (la Lambda fija TZ a Madrid)."""
    try:
        return datetime.now(ZoneInfo(TZ_NAME)).date()
    except ZoneInfoNotFoundError:
        return date.today()


# Resultado de la última sincronización: True si se cortó por tiempo y queda historial por bajar.
LAST_PARTIAL = False


# ------------------------------------------------------------------ errores
class GoogleError(Exception):
    def __init__(self, status: int, msg: str = "") -> None:
        super().__init__(f"Google Health HTTP {status}: {msg}"[:300])
        self.status = status


class Reauth(GoogleError):
    """Google ya no acepta el permiso (revocado o caducado): hay que volver a conectar."""


class NotLinked(GoogleError):
    """La cuenta de Google no tiene Google Health enlazado (falta entrar en la app de Google Health)."""

    def __init__(self, link_url: str | None = None) -> None:
        super().__init__(400, "ACCOUNT_NOT_LINKED")
        self.link_url = link_url or LINK_URL


class ScopeMissing(GoogleError):
    """La persona no dio ese permiso: el bloque se salta."""


# ------------------------------------------------------------------ HTTP
def _default_open(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)  # solo URLs fijas de Google


OPENER = _default_open  # las pruebas lo cambian por uno falso (sin red)


def _read_error(e: urllib.error.HTTPError) -> dict:
    try:
        body = json.loads(e.read() or b"{}")
    except (ValueError, OSError):
        return {}
    return body if isinstance(body, dict) else {}


def _not_linked(status: int, body: dict) -> str | None:
    """Si el error es "cuenta sin enlazar", devuelve la dirección para enlazarla."""
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    for d in err.get("details") or []:
        if isinstance(d, dict) and d.get("reason") == "ACCOUNT_NOT_LINKED":
            return (d.get("metadata") or {}).get("redirect_uri") or LINK_URL
    if status == 412:  # perfil de Google Health a medio crear
        return LINK_URL
    return None


def _form(url: str, fields: dict, opener=None) -> dict:
    """POST de formulario a los servidores OAuth de Google."""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with (opener or OPENER)(req, 15) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = _read_error(e)
        code = body.get("error") if isinstance(body.get("error"), str) else ""
        # Solo es "vuelve a conectar" si el permiso de la persona ya no vale. invalid_client (cliente OAuth mal
        # configurado o borrado) es cosa del dueño: error normal, para que salte el aviso.
        if code in ("invalid_grant", "unauthorized_client"):
            raise Reauth(e.code, code) from None
        raise GoogleError(e.code, code or "token") from None


# ------------------------------------------------------------------ OAuth
def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def pkce() -> tuple[str, str]:
    """(verificador, reto S256) para el flujo con PKCE."""
    verifier = b64url(secrets.token_bytes(32))
    return verifier, b64url(hashlib.sha256(verifier.encode()).digest())


def auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    q = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES),
         "access_type": "offline", "prompt": "consent", "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256"}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange(client_id: str, client_secret: str, code: str, verifier: str, redirect_uri: str, opener=None) -> dict:
    """Cambia el código de la vuelta por los tokens. Sin refresh_token no sirve (no se podría sincronizar)."""
    tok = _form(TOKEN_URL, {"code": code, "client_id": client_id, "client_secret": client_secret,
                            "code_verifier": verifier, "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
                opener)
    if not tok.get("refresh_token") or not tok.get("access_token"):
        raise GoogleError(502, "sin refresh_token")
    return tok


def granted(scope: str | None) -> list[str]:
    """Permisos de salud concedidos, en corto (activity_and_fitness, sleep...)."""
    return sorted(s[len(SCOPE_BASE):].removesuffix(".readonly") for s in (scope or "").split() if s.startswith(SCOPE_BASE))


def revoke(token: str, opener=None) -> bool:
    """Retira el permiso en Google. Si falla (ya estaba retirado), no pasa nada."""
    try:
        _form(REVOKE_URL, {"token": token}, opener)
        return True
    except GoogleError:
        return False
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


# ------------------------------------------------------------------ cliente de la API
class Client:
    """Peticiones a la Google Health API con pausa, reintentos, renovación del token y paginación."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, access_token: str | None = None,
                 opener=None, sleep=time.sleep, gap: float = 0.4, retries: int = 4) -> None:
        self._id, self._secret, self._refresh = client_id, client_secret, refresh_token
        self._access = access_token
        self._open = opener or OPENER
        self._sleep, self.gap, self.retries = sleep, gap, retries
        self._last = 0.0
        self.calls = 0

    def _token(self) -> str:
        if not self._access:
            tok = _form(TOKEN_URL, {"client_id": self._id, "client_secret": self._secret,
                                    "refresh_token": self._refresh, "grant_type": "refresh_token"}, self._open)
            if not tok.get("access_token"):
                raise GoogleError(502, "sin access_token")
            self._access = tok["access_token"]
        return self._access

    def call(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        delay, refreshed = 2.0, False
        for attempt in range(self.retries + 1):
            wait = self.gap - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}
            data = None
            if body is not None:
                data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            self.calls += 1
            try:
                with self._open(req, 40) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                err = _read_error(e)
                if e.code == 401 and not refreshed:  # el token de acceso caducó: se pide otro una vez
                    self._access, refreshed = None, True
                    continue
                if e.code == 401:
                    raise Reauth(401, "token rechazado") from None
                link = _not_linked(e.code, err)
                if link:
                    raise NotLinked(link) from None
                if e.code == 403:
                    raise ScopeMissing(403, path) from None
                if e.code in RETRY_STATUS and attempt < self.retries:
                    log.warning("Google Health HTTP %s en %s, reintento en %.0fs", e.code, path, delay)
                    self._sleep(delay)
                    delay *= 2
                    continue
                msg = (err.get("error") or {}).get("message", "") if isinstance(err.get("error"), dict) else ""
                raise GoogleError(e.code, msg or path) from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt >= self.retries:
                    raise GoogleError(503, f"red: {e}") from None
                self._sleep(delay)
                delay *= 2
        raise GoogleError(503, f"sin respuesta en {path}")

    def identity(self) -> dict:
        return self.call("GET", "/identity")

    def list(self, data_type: str, filter: str | None = None, page_size: int = 10000, max_pages: int = 200) -> list[dict]:
        """Todos los puntos de un tipo. Google sigue dando token tras la última página: se para si llega vacío o repetido."""
        out: list[dict] = []
        token = None
        for _ in range(max_pages):
            params = {"pageSize": page_size}
            if filter:
                params["filter"] = filter
            if token:
                params["pageToken"] = token
            r = self.call("GET", f"/dataTypes/{data_type}/dataPoints", params)
            pts = r.get("dataPoints") or []
            out += pts
            nxt = r.get("nextPageToken")
            if not pts or not nxt or nxt == token:
                break
            token = nxt
        return out

    def daily(self, data_type: str, start: date, end: date, page_size: int = 90) -> list[dict]:
        """Resumen por día (dailyRollUp) de [start, end), en hora local de la persona."""
        body = {"range": {"start": {"date": _gdate(start)}, "end": {"date": _gdate(end)}},
                "windowSizeDays": 1, "pageSize": page_size}
        out: list[dict] = []
        token = None
        for _ in range(20):
            r = self.call("POST", f"/dataTypes/{data_type}/dataPoints:dailyRollUp",
                          body=body | ({"pageToken": token} if token else {}))
            pts = r.get("rollupDataPoints") or []
            out += pts
            nxt = r.get("nextPageToken")
            if not pts or not nxt or nxt == token:
                break
            token = nxt
        return out


# ------------------------------------------------------------------ conversión a la forma de Garmin
def _gdate(d: date) -> dict:
    return {"year": d.year, "month": d.month, "day": d.day}


def civil(d: dict | None) -> str | None:
    """{"year", "month", "day"} → "YYYY-MM-DD"."""
    if not isinstance(d, dict) or not d.get("year"):
        return None
    return f"{d['year']:04d}-{d.get('month', 1):02d}-{d.get('day', 1):02d}"


def seconds(v) -> float:
    """Duración de Google ("2587.598s") en segundos."""
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).rstrip("s"))
    except ValueError:
        return 0.0


def _num(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def instant(ts: str | None) -> datetime | None:
    """Instante RFC 3339 (con hasta 9 decimales) en UTC."""
    if not ts:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$", ts)
    if not m:
        return None
    frac = (m.group(2) or "")[:7]  # como mucho microsegundos
    tz = m.group(3) or "Z"
    dt = datetime.fromisoformat(m.group(1) + frac + ("+00:00" if tz == "Z" else tz))
    return dt.astimezone(UTC)


def local(ts: str | None, offset) -> datetime | None:
    """Hora local (sin zona) = instante UTC + desfase que da Google."""
    t = instant(ts)
    return None if t is None else (t + timedelta(seconds=seconds(offset))).replace(tzinfo=None)


def _local_ms(ts: str | None, offset) -> int | None:
    """Como los "...TimestampLocal" de Garmin: la hora local escrita como si fuera UTC, en milisegundos."""
    t = local(ts, offset)
    return None if t is None else int(t.replace(tzinfo=UTC).timestamp() * 1000)


def activity_id(google_id: str) -> int:
    """Id numérico estable para un entreno de Google (el informe usa ids enteros, como los de Garmin).
    Cabe en un número de JavaScript sin perder precisión (< 2^53)."""
    return int(hashlib.sha256(google_id.encode()).hexdigest()[:13], 16)


# Tipos de Google → tipo de Garmin (el que agrupa el informe: Correr, Bici, Natación...)
TYPE_KEY = {
    "RUNNING": "running", "INCLINE_RUN": "running", "WATER_JOGGING": "running", "TRAIL_RUN": "trail_running",
    "TRACK_AND_FIELD": "track_running", "TREADMILL": "treadmill_running",
    "BIKING": "cycling", "OUTDOOR_BIKE": "cycling", "ELECTRIC_BIKE": "cycling", "HAND_CYCLING": "cycling",
    "MOUNTAIN_BIKE": "mountain_biking", "STATIONARY_BIKE": "indoor_cycling", "SPINNING": "indoor_cycling",
    "ASSAULT_BIKE": "indoor_cycling",
    "SWIMMING": "lap_swimming", "SWIMMING_POOL": "lap_swimming", "SWIMMING_OPEN_WATER": "open_water_swimming",
    "WALKING": "walking", "POWER_WALKING": "walking", "NORDIC_WALKING": "walking", "TREADMILL_WALK": "walking",
    "INCLINE_WALK": "walking", "STROLLER_WALK": "walking", "WALK_WITH_WEIGHTS": "walking",
    "HIKING": "hiking", "BACKPACKING": "hiking", "RUCKING": "hiking", "SNOWSHOEING": "hiking",
    "STRENGTH_TRAINING": "strength_training", "WEIGHTLIFTING": "strength_training", "WEIGHTS": "strength_training",
    "FREE_WEIGHTS": "strength_training", "WEIGHT_MACHINES": "strength_training", "POWERLIFTING": "strength_training",
    "FUNCTIONAL_STRENGTH_TRAINING": "strength_training", "BODY_WEIGHT": "strength_training",
    "CALISTHENICS": "strength_training", "CORE_TRAINING": "strength_training", "RESISTANCE_BANDS": "strength_training",
    "TRX": "strength_training", "CROSSFIT": "strength_training", "CIRCUIT_TRAINING": "strength_training",
    "HIIT": "hiit", "TABATA_WORKOUT": "hiit", "INTERVAL_WORKOUT": "hiit", "BOOTCAMP": "hiit",
    "YOGA": "yoga", "YOGA_BIKRAM": "yoga", "YOGA_HATHA": "yoga", "YOGA_POWER": "yoga", "YOGA_VINYASA": "yoga",
    "PILATES": "pilates", "ELLIPTICAL": "elliptical", "STAIRCLIMBER": "stair_climbing",
    "ROWING_MACHINE": "indoor_rowing", "ROWING": "rowing", "TENNIS": "tennis", "PADEL": "padel",
    "SOCCER": "soccer", "BASKETBALL": "basketball", "CROSS_COUNTRY_SKI": "cross_country_skiing",
    "SKIING": "resort_skiing", "SNOWBOARDING": "resort_snowboarding", "CLIMBING": "rock_climbing",
    "ROCK_CLIMBING": "rock_climbing", "INDOOR_CLIMBING": "indoor_climbing",
}
RUN_KEYS = {"running", "trail_running", "track_running", "treadmill_running"}


def to_activity(p: dict) -> tuple[str, dict] | None:
    """Un entreno de Google → (clave, actividad con los campos de Garmin que usa el informe)."""
    e = p.get("exercise") or {}
    iv = e.get("interval") or {}
    start, end = instant(iv.get("startTime")), instant(iv.get("endTime"))
    if not start or not end:
        return None
    gid = str(p.get("name") or "").rsplit("/", 1)[-1] or f"{iv['startTime']}-{e.get('exerciseType')}"
    aid = activity_id(gid)
    m = e.get("metricsSummary") or {}
    elapsed = max(0.0, (end - start).total_seconds())
    moving = seconds(e.get("activeDuration")) or elapsed
    dist = (_num(m.get("distanceMillimeters")) or 0) / 1000
    speed = (_num(m.get("averageSpeedMillimetersPerSecond")) or 0) / 1000
    pace = _num(m.get("averagePaceSecondsPerMeter")) or 0
    if not speed:
        speed = 1 / pace if pace > 0 else (dist / moving if dist and moving else 0)
    gtype = str(e.get("exerciseType") or "OTHER")
    key = TYPE_KEY.get(gtype, "other")
    loc = local(iv.get("startTime"), iv.get("startUtcOffset"))
    hr = _num(m.get("averageHeartRateBeatsPerMinute"))
    elev = _num(m.get("elevationGainMillimeters"))
    act = {
        "activityId": aid, "googleId": gid, "source": "google",
        "activityName": e.get("displayName") or gtype.replace("_", " ").capitalize(),
        "activityType": {"typeKey": key, "googleType": gtype},
        "startTimeLocal": loc.strftime("%Y-%m-%d %H:%M:%S"),
        "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S"),
        "distance": dist, "duration": elapsed, "movingDuration": moving,
        "averageHR": round(hr) if hr else None, "maxHR": None,  # Google no da el pico de un entreno
        "averageSpeed": speed or None, "calories": _num(m.get("caloriesKcal")),
        "elevationGain": elev / 1000 if elev is not None else None,
        "steps": int(_num(m.get("steps")) or 0) or None,
        "vO2MaxValue": _num(m.get("runVo2Max")),
    }
    if key in RUN_KEYS and act["steps"] and moving:
        act["averageRunningCadenceInStepsPerMinute"] = round(act["steps"] / (moving / 60), 1)
    pool = _num((e.get("exerciseMetadata") or {}).get("poolLengthMillimeters"))
    if pool:
        act["poolLength"] = pool / 10  # Garmin lo da en cm
    return str(aid), act


def _stage_minutes(sl: dict) -> dict:
    out: dict = {}
    for s in (sl.get("summary") or {}).get("stagesSummary") or []:
        t = s.get("type")
        out[t] = out.get(t, 0) + (_num(s.get("minutes")) or 0)
        out[t + "_count"] = out.get(t + "_count", 0) + int(_num(s.get("count")) or 0)
    return out


def asleep(sl: dict) -> float:
    return _num((sl.get("summary") or {}).get("minutesAsleep")) or 0


def to_sleep(points: list[dict]) -> dict[str, dict]:
    """Noches de Google → un registro por día (el día en que te despiertas), como el sueño de Garmin."""
    by_day: dict[str, list[dict]] = {}
    for p in points:
        sl = p.get("sleep") or {}
        iv = sl.get("interval") or {}
        end = local(iv.get("endTime"), iv.get("endUtcOffset"))
        if not end:
            continue
        wake = civil((iv.get("civilEndTime") or {}).get("date")) or end.date().isoformat()
        by_day.setdefault(wake, []).append(sl)
    out = {}
    for day, sleeps in by_day.items():
        naps = [s for s in sleeps if (s.get("metadata") or {}).get("nap")]
        mains = [s for s in sleeps if s not in naps]
        flagged = [s for s in mains if (s.get("metadata") or {}).get("mainSleep")]
        main = max(flagged or mains, key=asleep) if mains else None
        if main is None or not asleep(main):
            continue
        iv = main["interval"]
        st = _stage_minutes(main)
        has_stages = any(st.get(k) for k in ("DEEP", "LIGHT", "REM"))
        light = st.get("LIGHT", 0) + (0 if has_stages else st.get("ASLEEP", 0) + st.get("RESTLESS", 0))
        out[day] = {
            "calendarDate": day, "source": "google",
            "sleepTimeSeconds": int(asleep(main) * 60),
            "sleepStartTimestampLocal": _local_ms(iv.get("startTime"), iv.get("startUtcOffset")),
            "sleepEndTimestampLocal": _local_ms(iv.get("endTime"), iv.get("endUtcOffset")),
            "deepSleepSeconds": int(st.get("DEEP", 0) * 60) if has_stages else None,
            "lightSleepSeconds": int(light * 60),
            "remSleepSeconds": int(st.get("REM", 0) * 60) if has_stages else None,
            "awakeSleepSeconds": int((_num((main.get("summary") or {}).get("minutesAwake")) or st.get("AWAKE", 0)) * 60),
            "awakeCount": st.get("AWAKE_count") or None,
            "napTimeSeconds": int(sum(asleep(s) for s in naps) * 60),
            "deviceRemCapable": has_stages,
        }
    return out


def to_hrv(points: list[dict]) -> dict[str, dict]:
    out = {}
    for p in points:
        h = p.get("dailyHeartRateVariability") or {}
        day, v = civil(h.get("date")), _num(h.get("averageHeartRateVariabilityMilliseconds"))
        if day and v:
            out[day] = {"calendarDate": day, "lastNightAvg": round(v), "source": "google"}
    return out


def to_weight(points: list[dict]) -> dict[str, dict]:
    """La última pesada de cada día (en gramos, como Garmin)."""
    best: dict[str, tuple[datetime, float]] = {}
    for p in points:
        w = p.get("weight") or {}
        st = w.get("sampleTime") or {}
        g = _num(w.get("weightGrams"))
        t = instant(st.get("physicalTime"))
        day = civil((st.get("civilTime") or {}).get("date")) or (
            local(st.get("physicalTime"), st.get("utcOffset")).date().isoformat() if t else None)
        if not day or not g or t is None:
            continue
        if day not in best or t > best[day][0]:
            best[day] = (t, g)
    return {d: {"summaryDate": d, "source": "google", "latestWeight": {"weight": g, "sourceType": "GOOGLE_HEALTH"}}
            for d, (_, g) in best.items()}


def to_daily(day: str, v: dict) -> dict:
    """Valores de un día (pasos, calorías, pulso en reposo...) → resumen diario de Garmin."""
    steps, rhr = v.get("steps"), v.get("rhr")
    rec = {
        "calendarDate": day, "source": "google",
        "includesWellnessData": bool(steps) or rhr is not None,
        "movement": {"steps": {"value": steps, "distanceInMeters": v.get("distance_m")}},
        "calories": {"burnedTotal": v.get("cal_total"), "burnedActive": v.get("cal_active")},
        "heartRate": {"restingValue": rhr},
    }
    if v.get("azm_low") is not None or v.get("azm_high") is not None:
        # Google da 2 minutos en zona por cada minuto en cardio o pico: aquí se guardan minutos reales
        rec["intensityMinutes"] = {"moderate": int(v.get("azm_low") or 0), "vigorous": int((v.get("azm_high") or 0) // 2)}
    return rec


def to_heart_rate(points: list[dict], bucket_s: int = 120) -> list[list[int]]:
    """Pulso del día en tramos de 2 minutos (como Garmin): [[instante en ms, ppm], ...]."""
    acc: dict[int, list[float]] = {}
    for p in points:
        h = p.get("heartRate") or {}
        t, bpm = instant((h.get("sampleTime") or {}).get("physicalTime")), _num(h.get("beatsPerMinute"))
        if t is None or not bpm or not 25 <= bpm <= 240:
            continue
        b = int(t.timestamp()) // bucket_s * bucket_s
        acc.setdefault(b, []).append(bpm)
    return [[b * 1000, round(sum(v) / len(v))] for b, v in sorted(acc.items())]


# ------------------------------------------------------------------ sincronización
def _days(start: date, end: date, step: int):
    """Tramos [a, b) de como mucho `step` días entre start (incluido) y end (excluido)."""
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=step), end)
        yield cur, nxt
        cur = nxt


class Syncer:
    """Baja lo nuevo de Google Health al almacén local, con la forma de los datos de Garmin."""

    def __init__(self, client: Client, store, today: date | None = None, deadline: float | None = None) -> None:
        self.client = client
        self.store = store
        self.today = today or today_local()
        self.deadline = float(os.environ.get("GARMIN_STATS_DEADLINE") or 0) if deadline is None else deadline
        self.partial = False
        self.skipped: list[str] = []
        self._no_scope: set[str] = set()

    def _late(self) -> bool:
        if self.deadline and time.time() > self.deadline:
            if not self.partial:
                log.warning("Tiempo agotado: sigo en la próxima ejecución")
            self.partial = True
        return self.partial

    def _start(self, name: str) -> date:
        """Desde dónde pedir: todo el historial la primera vez; luego lo hecho menos unos días."""
        first = self.today - timedelta(days=HISTORY_DAYS)
        done = self.store.state(f"gh_done:{name}")
        return first if not done else max(first, date.fromisoformat(done) - timedelta(days=REFRESH_DAYS))

    def _done(self, name: str, upto: date) -> None:
        self.store.set_state(f"gh_done:{name}", upto.isoformat())
        self.store.commit()

    # ---------- bloques ----------
    def sync_exercises(self) -> int:
        start = self._start("exercise")
        pts = self.client.list("exercise", f'exercise.interval.civil_start_time >= "{start.isoformat()}"', page_size=25)
        n = 0
        for p in pts:
            r = to_activity(p)
            if not r:
                continue
            key, act = r
            self.store.put("activity", key, act)
            if act["activityType"]["typeKey"] == "strength_training" and not self.store.has("strength_sets", key):
                self.store.put("strength_sets", key, [])  # sin FIT no hay series: no se buscan
            n += 1
        self._done("exercise", self.today)
        return n

    def _rollup(self, data_type: str, a: date, b: date, page_size: int = 90) -> list[dict]:
        """Resumen diario de un tipo; sin permiso para ese tipo devuelve [] (y no lo vuelve a pedir)."""
        if data_type in self._no_scope:
            return []
        try:
            return self.client.daily(data_type, a, b, page_size)
        except ScopeMissing:
            self._no_scope.add(data_type)
            return []

    def sync_daily(self) -> int:
        """Pasos, distancia, calorías, minutos en zona y pulso en reposo → un resumen diario por fecha."""
        start, end = self._start("daily"), self.today + timedelta(days=1)
        n = 0
        for a, b in _days(start, end, CHUNK_DAYS):
            if self._late():
                break
            vals: dict[str, dict] = {}
            put = _putter(vals)
            for p in self._rollup("steps", a, b):
                put(_day_of(p), "steps", int(_num((p.get("steps") or {}).get("countSum")) or 0))
            for p in self._rollup("distance", a, b):
                put(_day_of(p), "distance_m", (_num((p.get("distance") or {}).get("millimetersSum")) or 0) / 1000)
            for p in self._rollup("active-energy-burned", a, b):
                put(_day_of(p), "cal_active", _round((p.get("activeEnergyBurned") or {}).get("kcalSum")))
            for p in self._rollup("active-zone-minutes", a, b):
                z = p.get("activeZoneMinutes") or {}
                put(_day_of(p), "azm_low", int(_num(z.get("sumInFatBurnHeartZone")) or 0))
                put(_day_of(p), "azm_high",
                    int((_num(z.get("sumInCardioHeartZone")) or 0) + (_num(z.get("sumInPeakHeartZone")) or 0)))
            for ca, cb in _days(a, b, CAL_CHUNK_DAYS):
                for p in self._rollup("total-calories", ca, cb, CAL_CHUNK_DAYS):
                    put(_day_of(p), "cal_total", _round((p.get("totalCalories") or {}).get("kcalSum")))
            if "daily-resting-heart-rate" not in self._no_scope:
                flt = (f'daily_resting_heart_rate.date >= "{a.isoformat()}" AND '
                       f'daily_resting_heart_rate.date < "{b.isoformat()}"')
                try:
                    for p in self.client.list("daily-resting-heart-rate", flt):
                        r = p.get("dailyRestingHeartRate") or {}
                        put(civil(r.get("date")), "rhr", int(_num(r.get("beatsPerMinute")) or 0) or None)
                except ScopeMissing:  # otro permiso (métricas de salud)
                    self._no_scope.add("daily-resting-heart-rate")
            if self._no_scope >= DAILY_TYPES:
                raise ScopeMissing(403, "daily")  # sin ningún permiso para este bloque
            for day, v in vals.items():
                if any(v.get(k) for k in ("steps", "rhr", "cal_active", "azm_low", "azm_high")):
                    self.store.put("daily_summary", day, to_daily(day, v))
                    n += 1
            self._done("daily", min(b, self.today))
        return n

    def sync_sleep(self) -> int:
        start = self._start("sleep")
        pts = self.client.list("sleep", f'sleep.interval.civil_end_time >= "{start.isoformat()}"', page_size=25)
        recs = to_sleep(pts)
        for day, r in recs.items():
            self.store.put("sleep", day, r)
        self._done("sleep", self.today)
        return len(recs)

    def sync_hrv(self) -> int:
        start = self._start("hrv")
        recs = to_hrv(self.client.list("daily-heart-rate-variability",
                                       f'daily_heart_rate_variability.date >= "{start.isoformat()}"'))
        for day, r in recs.items():
            self.store.put("hrv", day, r)
        self._done("hrv", self.today)
        return len(recs)

    def sync_weight(self) -> int:
        start = self._start("weight")
        recs = to_weight(self.client.list("weight", f'weight.sample_time.civil_time >= "{start.isoformat()}"'))
        for day, r in recs.items():
            self.store.put("weight", day, r)
        self._done("weight", self.today)
        return len(recs)

    def sync_vo2max(self) -> int:
        """VO2max del día → el de cada carrera de ese día (el informe lo lee del resumen del FIT)."""
        start = self._start("vo2max")
        daily = {}
        for p in self.client.list("daily-vo2-max", f'daily_vo2_max.date >= "{start.isoformat()}"'):
            v = p.get("dailyVo2Max") or {}
            if civil(v.get("date")) and _num(v.get("vo2Max")):
                daily[civil(v.get("date"))] = round(float(v["vo2Max"]), 1)
        for day, v in daily.items():
            self.store.put("vo2max", day, {"calendarDate": day, "vo2Max": v})
        self._done("vo2max", self.today)
        return len(daily)

    def apply_vo2max(self) -> int:
        """Para cada carrera: el VO2max que trae el entreno o, si no, el del día."""
        daily = {k: v.get("vo2Max") for k, v in self.store.items("vo2max")}
        n = 0
        for key, a in self.store.items("activity"):
            if a.get("source") != "google" or (a.get("activityType") or {}).get("typeKey") not in RUN_KEYS:
                continue
            v = a.get("vO2MaxValue") or daily.get(str(a.get("startTimeLocal", ""))[:10])
            if v:
                self.store.put("fit_summary", key, {"vo2max_fit": round(float(v), 1), "n_records": 0, "source": "google"})
                n += 1
        return n

    def sync_heart_rate(self) -> int:
        """Pulso a lo largo del día, solo la última semana (un día por petición)."""
        have = self.store.keys("heart_rate")
        n = 0
        for i in range(INTRADAY_DAYS):
            d = self.today - timedelta(days=i)
            if (d.isoformat() in have and i >= REFRESH_DAYS) or self._late():
                continue
            nxt = d + timedelta(days=1)
            flt = (f'heart_rate.sample_time.civil_time >= "{d.isoformat()}" AND '
                   f'heart_rate.sample_time.civil_time < "{nxt.isoformat()}"')
            vals = to_heart_rate(self.client.list("heart-rate", flt, max_pages=5))
            if vals:
                self.store.put("heart_rate", d.isoformat(), {"calendarDate": d.isoformat(), "heartRateValues": vals,
                                                             "source": "google"})
                n += 1
        self.store.commit()
        return n

    def sync_profile(self) -> None:
        """Pulso en reposo de referencia (mediana de la última semana) para las zonas y el TRIMP."""
        rhr = [v["heartRate"]["restingValue"] for _, v in sorted(self.store.items("daily_summary"))[-14:]
               if (v.get("heartRate") or {}).get("restingValue")]
        zone = {"sport": "DEFAULT", "restingHeartRateUsed": round(statistics.median(rhr[-7:])) if rhr else None,
                "maxHeartRateUsed": None}
        self.store.put("profile", "hr_zones", [zone])
        self.store.put("profile", "settings", {"displayName": None, "source": "google"})

    def run(self) -> dict:
        self.client.identity()  # si la cuenta no tiene Google Health enlazado, falla aquí (NotLinked)
        counts: dict[str, int] = {}
        for name, fn in (("exercise", self.sync_exercises), ("daily", self.sync_daily), ("sleep", self.sync_sleep),
                         ("hrv", self.sync_hrv), ("weight", self.sync_weight), ("vo2max", self.sync_vo2max),
                         ("heart_rate", self.sync_heart_rate)):
            if self._late():
                break
            try:
                counts[name] = fn()
            except ScopeMissing:
                log.info("Google Health: sin permiso para %s, lo salto", name)
                self.skipped.append(name)
            except GoogleError as e:
                if isinstance(e, (Reauth, NotLinked)):
                    raise
                log.warning("Google Health %s: %s", name, e)  # un bloque que falla no tumba el resto
                self.skipped.append(name)
        self.apply_vo2max()
        self.sync_profile()
        global LAST_PARTIAL
        LAST_PARTIAL = self.partial
        self.store.set_state("last_sync", self.today.isoformat())
        self.store.commit()
        log.info("Google Health %s: %s, %d peticiones%s", "parcial" if self.partial else "terminada", counts,
                 self.client.calls, f", sin permiso: {self.skipped}" if self.skipped else "")
        return {"counts": counts, "skipped": self.skipped, "partial": self.partial}


def _putter(vals: dict):
    """Apunta un valor de un día (si lo hay) en vals[día][campo]."""
    def put(day, field, value):
        if day and value is not None:
            vals.setdefault(day, {})[field] = value
    return put


def _day_of(p: dict) -> str | None:
    return civil((p.get("civilStartTime") or {}).get("date"))


def _round(v):
    n = _num(v)
    return round(n) if n is not None else None


def sync(client: Client) -> bool:
    """Como `garmin-stats sync`, pero de Google Health. Devuelve True si queda historial por bajar."""
    from . import DB_PATH
    from .store import Store

    store = Store(DB_PATH)
    try:
        return Syncer(client, store).run()["partial"]
    finally:
        store.close()
