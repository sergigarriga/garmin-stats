"""Google Health como fuente de datos: OAuth, cliente, conversión a la forma de Garmin, sincronización, API y
sincronización en AWS. Sin red: Google se simula con respuestas grabadas (tests/fixtures/google_health) o generadas."""
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import sys
import time
import types
import urllib.error
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from garmin_stats import analysis as R
from garmin_stats import export as X
from garmin_stats import extras
from garmin_stats import google_health as GH
from garmin_stats import metrics as M
from garmin_stats import tables as T
from garmin_stats.store import Store

FIX = Path(__file__).parent / "fixtures" / "google_health"
TODAY = date(2026, 11, 8)


def fx(name: str):
    return json.loads((FIX / name).read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Ninguna prueba sale a internet: si algo llama a Google sin simular, falla."""
    monkeypatch.setattr(GH, "OPENER", lambda req, timeout: pytest.fail(f"llamada de red sin simular: {req.full_url}"))


# ---------------------------------------------------------------- Google simulado
class Err(Exception):
    def __init__(self, code: int, body: dict | None = None) -> None:
        super().__init__(code)
        self.code, self.body = code, body or {}


class _Resp:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


class FakeGoogle:
    """Hace de Google: `route(method, path, query, body)` devuelve un dict o lanza Err(código, cuerpo)."""

    def __init__(self, route) -> None:
        self.route = route
        self.calls: list[tuple] = []

    def __call__(self, req, timeout):
        u = urllib.parse.urlparse(req.full_url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        body = None
        if req.data:
            ctype = req.get_header("Content-type") or ""
            body = json.loads(req.data) if "json" in ctype else {k: v[0] for k, v in urllib.parse.parse_qs(req.data.decode()).items()}
        call = (req.get_method(), u.netloc + u.path, q, body, req.get_header("Authorization"))
        self.calls.append(call)
        try:
            out = self.route(*call[:4])
        except Err as e:
            raise urllib.error.HTTPError(req.full_url, e.code, "error", {}, io.BytesIO(json.dumps(e.body).encode())) from None
        return _Resp(json.dumps(out).encode())

    def paths(self):
        return [c[1].split("/v4/users/me")[-1] for c in self.calls]


API_HOST = "health.googleapis.com/v4/users/me"
ROLLUPS = {"steps": "rollup_steps.json", "distance": "rollup_distance.json",
           "active-energy-burned": "rollup_active_energy_burned.json", "total-calories": "rollup_total_calories.json",
           "active-zone-minutes": "rollup_active_zone_minutes.json"}
LISTS = {"daily-resting-heart-rate": "daily_resting_heart_rate.json", "sleep": "sleep.json",
         "daily-heart-rate-variability": "daily_heart_rate_variability.json", "weight": "weight.json",
         "daily-vo2-max": "daily_vo2_max.json", "heart-rate": "heart_rate.json"}


def recorded(deny: set | None = None):
    """Rutas con las respuestas grabadas. `deny`: tipos sin permiso (403)."""
    deny = deny or set()

    def route(method, path, q, body):
        if path == "oauth2.googleapis.com/token":
            return {"access_token": "ya29.nuevo", "expires_in": 3599}
        if path == API_HOST + "/identity":
            return fx("identity.json")
        dtype = path.split("/dataTypes/")[1].split("/")[0] if "/dataTypes/" in path else None
        if dtype in deny:
            raise Err(403, fx("error_permission.json"))
        if path.endswith(":dailyRollUp"):
            a, b = date(**body["range"]["start"]["date"]), date(**body["range"]["end"]["date"])
            return fx(ROLLUPS[dtype]) if a <= date(2026, 11, 7) < b else {"rollupDataPoints": []}
        if dtype == "exercise":
            return fx("exercise_p2.json") if q.get("pageToken") == "pagina-2" else fx("exercise_p1.json")
        if dtype == "heart-rate":
            return fx("heart_rate.json") if '"2026-11-08"' in q.get("filter", "").split(" AND ")[0] else {}
        if dtype in LISTS:
            return fx(LISTS[dtype])
        raise Err(404, {"error": {"code": 404}})
    return route


def client(route, **kw) -> tuple[GH.Client, FakeGoogle]:
    fake = FakeGoogle(route)
    return GH.Client("id", "secreto", "1//refresco", opener=fake, sleep=lambda s: None, gap=0, **kw), fake


# ---------------------------------------------------------------- OAuth
def test_auth_url_pkce_offline_and_readonly_scopes():
    verifier, challenge = GH.pkce()
    assert challenge == GH.b64url(hashlib.sha256(verifier.encode()).digest())
    url = GH.auth_url("cid", "https://runch.example/api/google/callback", "st", challenge)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"] and q["state"] == ["st"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"] == [challenge]
    scopes = q["scope"][0].split()
    assert len(scopes) == 3 and all(s.endswith(".readonly") for s in scopes)
    assert not any("location" in s for s in scopes)  # nunca la ruta GPS


def test_exchange_needs_refresh_token_and_maps_invalid_grant():
    fake = FakeGoogle(lambda *a: fx("token.json"))
    tok = GH.exchange("cid", "sec", "codigo", "verif", "https://x/api/google/callback", opener=fake)
    assert tok["refresh_token"] == "1//refresco-de-prueba"
    method, path, _, body, _ = fake.calls[0]
    assert (method, path) == ("POST", "oauth2.googleapis.com/token")
    assert body["code_verifier"] == "verif" and body["grant_type"] == "authorization_code"
    assert GH.granted(tok["scope"]) == ["activity_and_fitness", "sleep"]
    with pytest.raises(GH.GoogleError):
        GH.exchange("c", "s", "x", "v", "r", opener=FakeGoogle(lambda *a: {"access_token": "solo-acceso"}))

    def bad(*a):
        raise Err(400, fx("error_invalid_grant.json"))
    with pytest.raises(GH.Reauth):
        GH.exchange("c", "s", "x", "v", "r", opener=FakeGoogle(bad))


def test_revoke_never_raises():
    def gone(*a):
        raise Err(400, {"error": "invalid_token"})
    assert GH.revoke("t", opener=FakeGoogle(gone)) is False
    assert GH.revoke("t", opener=FakeGoogle(lambda *a: {})) is True


# ---------------------------------------------------------------- cliente
def test_list_follows_pages_and_stops_on_repeated_token():
    c, fake = client(recorded())
    pts = c.list("exercise", 'exercise.interval.civil_start_time >= "2026-10-01"', page_size=25)
    assert len(pts) == 3
    assert fake.paths().count("/dataTypes/exercise/dataPoints") == 2  # no se queda pidiendo la misma página
    assert fake.calls[1][2]["pageSize"] == "25" and "filter" in fake.calls[1][2]
    assert fake.calls[1][4] == "Bearer ya29.nuevo"  # el token de acceso sale del refresh_token


def test_expired_access_token_is_refreshed_once():
    state = {"n": 0}

    def route(method, path, q, body):
        if path.endswith("/token"):
            return {"access_token": f"ya29.{state['n']}"}
        state["n"] += 1
        if state["n"] == 1:
            raise Err(401, {"error": {"code": 401, "status": "UNAUTHENTICATED"}})
        return fx("identity.json")
    c, fake = client(route, access_token="viejo")
    assert c.identity()["healthUserId"] == "1234567890"
    assert [p for p in fake.paths() if p.endswith("/token")]


def test_revoked_refresh_token_is_reauth():
    def route(method, path, q, body):
        raise Err(400, fx("error_invalid_grant.json"))
    c, _ = client(route)
    with pytest.raises(GH.Reauth):
        c.identity()


@pytest.mark.parametrize("code,body", [(400, "error_not_linked.json"), (412, None)])
def test_account_not_linked(code, body):
    def route(method, path, q, b):
        if path.endswith("/token"):
            return {"access_token": "a"}
        raise Err(code, fx(body) if body else {})
    c, _ = client(route)
    with pytest.raises(GH.NotLinked) as e:
        c.identity()
    assert e.value.link_url.startswith("https://")


def test_rate_limit_is_retried_and_forbidden_is_scope_missing():
    state = {"n": 0}
    waits = []

    def route(method, path, q, body):
        if path.endswith("/token"):
            return {"access_token": "a"}
        state["n"] += 1
        if path.endswith("/identity") and state["n"] < 3:
            raise Err(429, {"error": {"code": 429}})
        if "/sleep/" in path:
            raise Err(403, fx("error_permission.json"))
        return fx("identity.json")
    fake = FakeGoogle(route)
    c = GH.Client("id", "s", "r", opener=fake, sleep=waits.append, gap=0)
    assert c.identity()["healthUserId"]
    assert waits == [2.0, 4.0]  # espera creciente
    with pytest.raises(GH.ScopeMissing):
        c.list("sleep")


def test_daily_rollup_sends_civil_range():
    c, fake = client(recorded())
    pts = c.daily("steps", date(2026, 11, 7), date(2026, 11, 9))
    assert len(pts) == 2
    method, path, _, body, _ = fake.calls[-1]
    assert method == "POST" and path.endswith("/dataTypes/steps/dataPoints:dailyRollUp")
    assert body["range"] == {"start": {"date": {"year": 2026, "month": 11, "day": 7}},
                             "end": {"date": {"year": 2026, "month": 11, "day": 9}}}


# ---------------------------------------------------------------- conversión
def test_helpers():
    assert GH.seconds("2587.598s") == pytest.approx(2587.598) and GH.seconds(None) == 0
    assert GH.instant("2026-11-08T07:02:11.123456789Z") == datetime(2026, 11, 8, 7, 2, 11, 123456, tzinfo=UTC)
    assert GH.local("2026-11-08T07:00:00Z", "3600s") == datetime(2026, 11, 8, 8, 0)
    assert GH.civil({"year": 2026, "month": 3, "day": 5}) == "2026-03-05"
    a, b = GH.activity_id("abc"), GH.activity_id("abd")
    assert a == GH.activity_id("abc") and a != b and 0 < a < 2 ** 53


def test_exercise_to_garmin_activity():
    key, a = GH.to_activity(fx("exercise_p1.json")["dataPoints"][0])
    assert key == str(GH.activity_id("8811a2b3-run")) and a["googleId"] == "8811a2b3-run"
    assert a["activityType"]["typeKey"] == "running"
    assert a["startTimeLocal"] == "2026-11-08 08:02:11"  # hora local (UTC+1)
    assert a["distance"] == pytest.approx(8012.345) and a["movingDuration"] == pytest.approx(2587.598)
    assert a["duration"] == pytest.approx(2899.877, abs=0.01)
    assert a["averageHR"] == 152 and a["maxHR"] is None
    assert a["averageSpeed"] == pytest.approx(1 / 0.3229) and a["elevationGain"] == pytest.approx(48)
    assert a["vO2MaxValue"] == 51.3 and a["averageRunningCadenceInStepsPerMinute"] == pytest.approx(167.2, abs=0.1)
    _, gym = GH.to_activity(fx("exercise_p1.json")["dataPoints"][1])
    assert gym["activityType"]["typeKey"] == "strength_training" and gym["distance"] == 0
    _, swim = GH.to_activity(fx("exercise_p2.json")["dataPoints"][0])
    assert swim["activityType"]["typeKey"] == "lap_swimming" and swim["averageSpeed"] == pytest.approx(0.7143)
    assert GH.to_activity({"exercise": {"interval": {}}}) is None


def test_sleep_main_night_naps_and_classic():
    recs = GH.to_sleep(fx("sleep.json")["dataPoints"])
    night = recs["2026-11-08"]
    assert night["sleepTimeSeconds"] == 412 * 60 and night["napTimeSeconds"] == 25 * 60
    assert night["deepSleepSeconds"] == 85 * 60 and night["remSleepSeconds"] == 106 * 60
    assert night["lightSleepSeconds"] == 221 * 60 and night["awakeSleepSeconds"] == 38 * 60 and night["awakeCount"] == 9
    assert pd.to_datetime(night["sleepStartTimestampLocal"], unit="ms") == pd.Timestamp("2026-11-07 23:40")
    assert pd.to_datetime(night["sleepEndTimestampLocal"], unit="ms") == pd.Timestamp("2026-11-08 07:10")
    classic = recs["2026-11-07"]  # sin fases: todo cuenta como sueño ligero y no se inventan profundo/REM
    assert classic["deepSleepSeconds"] is None and classic["remSleepSeconds"] is None
    assert classic["lightSleepSeconds"] == 420 * 60 and classic["deviceRemCapable"] is False


def test_hrv_weight_heart_rate_and_daily():
    assert GH.to_hrv(fx("daily_heart_rate_variability.json")["dataPoints"])["2026-11-08"]["lastNightAvg"] == 49
    w = GH.to_weight(fx("weight.json")["dataPoints"])
    assert w["2026-11-08"]["latestWeight"]["weight"] == 70350.0  # la última del día
    assert set(w) == {"2026-11-08", "2026-11-05"}
    hr = GH.to_heart_rate(fx("heart_rate.json")["dataPoints"])
    assert [v for _, v in hr] == [62, 152]  # tramos de 2 min; el 999 se descarta
    d = GH.to_daily("2026-11-08", {"steps": 100, "azm_low": 10, "azm_high": 64})
    assert d["intensityMinutes"] == {"moderate": 10, "vigorous": 32}  # Google cuenta doble en cardio y pico
    assert GH.to_daily("2026-11-08", {"rhr": 50})["includesWellnessData"] is True


# ---------------------------------------------------------------- sincronización con respuestas grabadas
def test_sync_fills_garmin_shaped_store(tmp_path):
    c, fake = client(recorded())
    store = Store(tmp_path / "g.sqlite")
    res = GH.Syncer(c, store, today=TODAY, deadline=0).run()
    assert not res["partial"] and not res["skipped"]
    assert len(dict(store.items("activity"))) == 3
    ds = store.get("daily_summary", "2026-11-08")
    assert ds["movement"]["steps"]["value"] == 14873 and ds["heartRate"]["restingValue"] == 51
    assert ds["calories"] == {"burnedTotal": 2950, "burnedActive": 955}
    assert ds["movement"]["steps"]["distanceInMeters"] == pytest.approx(13100)
    assert store.get("hrv", "2026-11-07")["lastNightAvg"] == 44
    assert store.get("heart_rate", "2026-11-08")["heartRateValues"]
    run_key = str(GH.activity_id("8811a2b3-run"))
    assert store.get("fit_summary", run_key)["vo2max_fit"] == 51.3  # el del entreno manda sobre el del día
    gym_key = str(GH.activity_id("8811a2b3-gym"))
    assert store.get("strength_sets", gym_key) == []  # sin FIT: no se buscan series
    assert store.get("profile", "hr_zones")[0]["restingHeartRateUsed"] == 52
    assert store.state("last_sync") == TODAY.isoformat()

    daily, sleep, acts = T.daily(store), T.sleep(store), T.activities(store)
    row = daily[daily["date"] == "2026-11-08"].iloc[0]
    assert row["steps"] == 14873 and row["rhr"] == 51 and row["worn"]
    assert sleep[sleep["date"] == "2026-11-08"].iloc[0]["sleep_h"] == pytest.approx(412 / 60)
    assert set(acts["group"]) == {"Correr", "Fuerza", "Natación"}
    assert T.weight(store)["weight_kg"].max() == pytest.approx(70.35)
    assert T.profile(store)["rest_hr"] == 52

    # segunda vez: solo los últimos días
    fake.calls.clear()
    GH.Syncer(c, store, today=TODAY, deadline=0).run()
    ex = next(q for _, p, q, _, _ in fake.calls if p.endswith("/exercise/dataPoints"))
    assert ex["filter"] == f'exercise.interval.civil_start_time >= "{(TODAY - timedelta(days=3)).isoformat()}"'
    assert len([p for p in fake.paths() if p.endswith(":dailyRollUp")]) == 5  # un tramo por tipo


def test_missing_permissions_are_skipped(tmp_path):
    c, _ = client(recorded(deny={"sleep", "daily-resting-heart-rate", "daily-heart-rate-variability", "weight",
                                 "heart-rate"}))
    store = Store(tmp_path / "g.sqlite")
    res = GH.Syncer(c, store, today=TODAY, deadline=0).run()
    assert set(res["skipped"]) == {"sleep", "hrv", "weight", "heart_rate"}
    assert store.get("daily_summary", "2026-11-08")["heartRate"]["restingValue"] is None
    assert len(dict(store.items("activity"))) == 3


def test_not_linked_stops_the_sync(tmp_path):
    def route(method, path, q, body):
        if path.endswith("/token"):
            return {"access_token": "a"}
        raise Err(400, fx("error_not_linked.json"))
    c, _ = client(route)
    with pytest.raises(GH.NotLinked):
        GH.Syncer(c, Store(tmp_path / "g.sqlite"), today=TODAY, deadline=0).run()


def test_deadline_leaves_the_rest_for_next_run(tmp_path):
    c, _ = client(recorded())
    store = Store(tmp_path / "g.sqlite")
    res = GH.Syncer(c, store, today=TODAY, deadline=time.time() - 1).run()
    assert res["partial"] and GH.LAST_PARTIAL
    assert store.state("gh_done:daily") is None


# ---------------------------------------------------------------- de punta a punta: Google → informe
def synthetic(today: date, days: int = 60):
    """Google simulado con `days` días de datos realistas hasta hoy (8 entrenos, sueño, pulso, HRV, peso)."""
    start = today - timedelta(days=days - 1)
    span = [start + timedelta(days=i) for i in range(days)]

    def g(d):
        return {"year": d.year, "month": d.month, "day": d.day}

    def iso(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def route(method, path, q, body):
        if path.endswith("/token"):
            return {"access_token": "a"}
        if path.endswith("/identity"):
            return fx("identity.json")
        dtype = path.split("/dataTypes/")[1].split("/")[0]
        if path.endswith(":dailyRollUp"):
            a = date(**body["range"]["start"]["date"])
            b = date(**body["range"]["end"]["date"])
            field = {"steps": ("steps", lambda i: {"countSum": str(8000 + 37 * i)}),
                     "distance": ("distance", lambda i: {"millimetersSum": str(6_000_000 + 1000 * i)}),
                     "active-energy-burned": ("activeEnergyBurned", lambda i: {"kcalSum": 400.0 + i}),
                     "total-calories": ("totalCalories", lambda i: {"kcalSum": 2300.0 + i}),
                     "active-zone-minutes": ("activeZoneMinutes", lambda i: {"sumInFatBurnHeartZone": "15", "sumInCardioHeartZone": "20"})}[dtype]
            return {"rollupDataPoints": [{"civilStartTime": {"date": g(d)}, field[0]: field[1](i)}
                                         for i, d in enumerate(span) if a <= d < b]}
        if dtype == "exercise":
            pts = []
            for i, d in enumerate(span[::-7][:8]):
                t0 = datetime(d.year, d.month, d.day, 7, 0, tzinfo=UTC)
                pts.append({"name": f"users/1/dataTypes/exercise/dataPoints/e{i}", "exercise": {
                    "interval": {"startTime": iso(t0), "endTime": iso(t0 + timedelta(minutes=50)), "startUtcOffset": "3600s", "endUtcOffset": "3600s"},
                    "exerciseType": "RUNNING" if i % 3 else "WEIGHTLIFTING", "displayName": "Entreno", "activeDuration": "2900s",
                    "metricsSummary": {"distanceMillimeters": 9_000_000.0 if i % 3 else 0, "averageHeartRateBeatsPerMinute": "148",
                                       "caloriesKcal": 600.0, "averagePaceSecondsPerMeter": 0.32 if i % 3 else 0}}})
            return {"dataPoints": pts}
        if dtype == "sleep":
            return {"dataPoints": [{"sleep": {"type": "STAGES", "interval": {
                "startTime": iso(datetime(d.year, d.month, d.day, 22, 30, tzinfo=UTC) - timedelta(days=1)),
                "endTime": iso(datetime(d.year, d.month, d.day, 6, 0, tzinfo=UTC)), "startUtcOffset": "3600s", "endUtcOffset": "3600s",
                "civilEndTime": {"date": g(d)}},
                "summary": {"minutesAsleep": str(410 + i % 30), "minutesAwake": "20", "stagesSummary": [
                    {"type": "DEEP", "minutes": "80", "count": "4"}, {"type": "REM", "minutes": "100", "count": "5"},
                    {"type": "LIGHT", "minutes": str(230 + i % 30), "count": "20"}, {"type": "AWAKE", "minutes": "20", "count": "6"}]},
                "metadata": {"mainSleep": True}}} for i, d in enumerate(span)][::-1]}
        if dtype == "daily-resting-heart-rate":
            return {"dataPoints": [{"dailyRestingHeartRate": {"date": g(d), "beatsPerMinute": str(50 + i % 4)}} for i, d in enumerate(span)]}
        if dtype == "daily-heart-rate-variability":
            return {"dataPoints": [{"dailyHeartRateVariability": {"date": g(d), "averageHeartRateVariabilityMilliseconds": 45.0 + i % 6}}
                                   for i, d in enumerate(span)]}
        if dtype == "weight":
            return {"dataPoints": [{"weight": {"weightGrams": 70000.0 - 10 * i, "sampleTime": {
                "physicalTime": f"{d.isoformat()}T06:30:00Z", "utcOffset": "3600s", "civilTime": {"date": g(d)}}}}
                for i, d in enumerate(span[::3])]}
        if dtype == "daily-vo2-max":
            return {"dataPoints": [{"dailyVo2Max": {"date": g(d), "vo2Max": 50.0}} for d in span]}
        if dtype == "heart-rate":
            d = date.fromisoformat(q["filter"].split('"')[1])
            t0 = datetime(d.year, d.month, d.day, tzinfo=UTC)
            return {"dataPoints": [{"heartRate": {"beatsPerMinute": str(60 + m % 30), "sampleTime": {
                "physicalTime": iso(t0 + timedelta(minutes=m)), "utcOffset": "3600s"}}} for m in range(0, 1440, 5)]}
        raise Err(404, {})
    return route


def test_google_data_builds_the_whole_report(tmp_path, monkeypatch):
    today = date.today()
    c, _ = client(synthetic(today))
    store = Store(tmp_path / "g.sqlite")
    GH.Syncer(c, store, today=today, deadline=0).run()

    X.SECTION_ERRORS.clear()
    prof = T.profile(store)
    tables = {"daily": T.daily(store), "sleep": T.sleep(store), "hrv": T.hrv(store), "weight": T.weight(store),
              "activities": T.activities(store)}
    acts = tables["activities"]
    am = M.activity_metrics(acts, T.fit_summary(store), T.fit_records(store, acts["activity_id"]),
                            prof.get("rest_hr") or 60, prof.get("max_hr") or 190)
    A = R.assemble({**tables, "activities": am}, prof)
    T.write_tables(store, {**tables, "activity_metrics": am, "load": A["load"], "day": A["day"].reset_index()})
    data = X.payload(A, am, store.state("last_sync"), dict(store.items("strength_sets")))
    assert not X.SECTION_ERRORS, X.SECTION_ERRORS
    assert data["days"] and data["days"][-1]["d"] == today.isoformat()
    last = data["days"][-1]
    for k in ("steps", "rhr", "hrv", "sleepH", "deepH", "cal", "calActive", "imVig", "walkKm"):
        assert last.get(k), k
    assert "readiness" in data and data["weights"]
    assert len(am) == 8 and am["trimp"].notna().all()
    runs = am[am["group"] == "Correr"]
    assert (runs["vo2max_fit"] == 50.0).all()
    assert extras.live(store, today)["hrLast"]
    monkeypatch.setattr(extras, "FIT_DIR", tmp_path / "fit")
    extras.write_activity_details(am, tmp_path / "site", prof.get("zones"))
    json.dumps(data)  # se puede publicar tal cual


# ---------------------------------------------------------------- API (Lambda) con S3, SSM y Google simulados
class _ClientError(Exception):
    pass


class _NoSuchKey(_ClientError):
    pass


class _ParamNotFound(Exception):
    pass


class FakeS3:
    class exceptions:
        ClientError = _ClientError
        NoSuchKey = _NoSuchKey

    def __init__(self):
        self.objs: dict[str, bytes] = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objs:
            raise _NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objs[Key])}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objs[Key] = Body if isinstance(Body, bytes) else Body.encode()

    def head_object(self, Bucket, Key):
        if Key not in self.objs:
            raise _ClientError(Key)

    def download_file(self, Bucket, Key, Filename):
        if Key not in self.objs:
            raise _ClientError(Key)
        Path(Filename).write_bytes(self.objs[Key])

    def get_paginator(self, name):
        s3 = self

        class P:
            def paginate(self, Bucket, Prefix):
                keys = [k for k in s3.objs if k.startswith(Prefix)]
                if name == "list_object_versions":
                    return [{"Versions": [{"Key": k, "VersionId": "v1"} for k in keys], "DeleteMarkers": []}]
                return [{"Contents": [{"Key": k} for k in keys]}]
        return P()

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.objs.pop(o["Key"], None)


class FakeSSM:
    class exceptions:
        ParameterNotFound = _ParamNotFound

    def __init__(self):
        self.params: dict[str, dict] = {}

    def get_parameter(self, Name, WithDecryption=False):
        if Name not in self.params:
            raise _ParamNotFound(Name)
        return {"Parameter": {"Value": self.params[Name]["Value"]}}

    def put_parameter(self, Name, Value, Type="String", Overwrite=False):
        self.params[Name] = {"Value": Value, "Type": Type}

    def delete_parameter(self, Name):
        if Name not in self.params:
            raise _ParamNotFound(Name)
        del self.params[Name]


class FakeLambda:
    def __init__(self):
        self.invokes: list[dict] = []

    def invoke(self, **kw):
        self.invokes.append(json.loads(kw["Payload"]))


HOST = "runch.example.com"
ID_PARAM, SECRET_PARAM = "/garmin-stats/google-health-client-id", "/garmin-stats/google-health-client-secret"


def _load(path: str, name: str, monkeypatch, env: dict, clients: dict):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    fake = types.ModuleType("boto3")
    fake.client = lambda svc: clients[svc]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def api(tmp_path, monkeypatch):
    secret, origin = "s" * 64, "o" * 64
    owner, friend, garmin = "persona@example.com", "amiga@example.com", "garmin@example.com"
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME", "GARMIN_STATS_UID", "GARMIN_STATS_AI_BUDGET",
                                              "GARMIN_STATS_ADAPT_MODEL", "GARMIN_STATS_ROOT", "GARMIN_STATS_USAGE_LOG")}
    s3, ssm, lam = FakeS3(), FakeSSM(), FakeLambda()
    ssm.params[ID_PARAM] = {"Value": "cid.apps.googleusercontent.com", "Type": "String"}
    ssm.params[SECRET_PARAM] = {"Value": "secreto", "Type": "SecureString"}
    h = _load("infra/lambda/api/handler.py", "api_handler_google_test", monkeypatch,
              {"BUCKET": "b", "SESSION_SECRET": secret, "ORIGIN_SECRET": origin, "OWNER_EMAIL": owner,
               "ANTHROPIC_KEY_PARAM": "/x", "AWS_LAMBDA_FUNCTION_NAME": "api", "SYNC_FUNCTION": "sync",
               "PUBLIC_HOST": HOST},
              {"s3": s3, "ssm": ssm, "lambda": lam})
    monkeypatch.setattr(h, "ROOT", tmp_path / "gs")
    monkeypatch.setattr(h, "HOME", tmp_path / "home")
    s3.objs["admin/users.json"] = json.dumps({"users": [
        {"email": owner, "uid": "u1", "role": "owner", "status": "onboarding"},
        {"email": friend, "uid": "u2", "role": "friend", "status": "onboarding", "consentAt": 1},
        {"email": garmin, "uid": "u3", "role": "friend", "status": "active", "consentAt": 1}]}).encode()
    google = FakeGoogle(lambda m, p, q, b: _google_ok(p))
    monkeypatch.setattr(GH, "OPENER", google)

    def cookie(email):
        b64 = base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
        exp = str(int(time.time()) + 3600)
        return f"gs_session={b64}.{exp}.{hmac.new(secret.encode(), f'{b64}.{exp}'.encode(), hashlib.sha256).hexdigest()}"

    def call(method, path, body=None, who=friend, query="", cookies=(), host=HOST):
        ev = {"headers": {"x-origin-verify": origin, "x-viewer-host": host},
              "cookies": [cookie(who), *cookies], "requestContext": {"http": {"method": method}},
              "rawPath": path, "rawQueryString": query, "body": json.dumps(body) if body is not None else ""}
        return h.handler(ev, None)

    def user(email):
        return next(u for u in json.loads(s3.objs["admin/users.json"])["users"] if u["email"] == email)

    yield types.SimpleNamespace(call=call, s3=s3, ssm=ssm, lam=lam, google=google, h=h, user=user,
                                owner=owner, friend=friend, garmin=garmin)
    for k, v in old_env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    time.tzset()


def _google_ok(path):
    if path == "oauth2.googleapis.com/token":
        return fx("token.json")
    if path == "oauth2.googleapis.com/revoke":
        return {}
    if path.endswith("/identity"):
        return fx("identity.json")
    raise Err(404, {})


def _me(api, who=None):
    r = api.call("GET", "/api/me", who=who or api.friend)
    assert r["statusCode"] == 200
    return json.loads(r["body"])


def _connect(api, query="back=ajustes"):
    r = api.call("GET", "/api/google/connect", query=query)
    assert r["statusCode"] == 302
    return r


def _callback(api, connect_resp, **over):
    loc = urllib.parse.urlparse(connect_resp["headers"]["location"])
    state = urllib.parse.parse_qs(loc.query)["state"][0]
    q = {"state": state, "code": "4/codigo", "scope": " ".join(GH.SCOPES), **over}
    cookie = connect_resp["cookies"][0].split(";")[0]
    return api.call("GET", "/api/google/callback", query=urllib.parse.urlencode(q), cookies=[cookie])


def test_me_says_if_google_health_is_available(api):
    me = _me(api)
    assert me["google"] == {"available": True, "connected": False} and me["source"] is None
    assert _me(api, api.garmin)["source"] == "garmin"
    api.ssm.params.pop(ID_PARAM)
    api.h._GH.clear()
    assert _me(api)["google"]["available"] is False


def test_connect_redirects_to_google_with_pkce(api):
    r = _connect(api)
    loc = urllib.parse.urlparse(r["headers"]["location"])
    q = urllib.parse.parse_qs(loc.query)
    assert loc.netloc == "accounts.google.com"
    assert q["redirect_uri"] == [f"https://{HOST}/api/google/callback"]
    assert q["client_id"] == ["cid.apps.googleusercontent.com"] and q["code_challenge_method"] == ["S256"]
    assert "Path=/api/google" in r["cookies"][0] and "HttpOnly" in r["cookies"][0] and "Max-Age=600" in r["cookies"][0]


@pytest.mark.parametrize("who,query,reason", [("garmin", "", "garmin"), ("owner", "", "consent")])
def test_connect_refusals(api, who, query, reason):
    r = api.call("GET", "/api/google/connect", who=getattr(api, who), query=query)
    assert r["headers"]["location"] == f"/?google=error&reason={reason}"


def test_connect_unavailable_without_client(api):
    api.ssm.params.pop(SECRET_PARAM)
    r = api.call("GET", "/api/google/connect", query="back=ajustes")
    assert r["headers"]["location"] == "/?google=error&reason=unavailable#ajustes"


def test_callback_saves_encrypted_permission_and_starts_sync(api):
    r = _callback(api, _connect(api))
    assert r["statusCode"] == 302 and r["headers"]["location"] == "/?google=ok#ajustes"
    assert "Max-Age=0" in r["cookies"][0]
    p = api.ssm.params["/garmin-stats/users/u2/google-token"]
    assert p["Type"] == "SecureString" and json.loads(p["Value"])["refresh_token"] == "1//refresco-de-prueba"
    assert json.loads(p["Value"])["healthUserId"] == "1234567890"
    u = api.user(api.friend)
    assert u["source"] == "google" and u["status"] == "active" and u["dataSource"] == "google"
    assert api.lam.invokes and api.lam.invokes[-1]["uid"] == "u2"
    token_call = next(c for c in api.google.calls if c[1].endswith("/token"))
    assert token_call[3]["redirect_uri"] == f"https://{HOST}/api/google/callback" and token_call[3]["code_verifier"]
    me = _me(api)
    assert me["source"] == "google"
    assert me["google"]["connected"] and me["google"]["status"] == "ok"
    assert me["google"]["scopes"] == ["activity_and_fitness", "sleep"]
    # con Google conectado no se puede poner una clave de Garmin (una sola fuente)
    r = api.call("POST", "/api/onboarding/key", {"key": "x" * 40})
    assert r["statusCode"] == 409


def test_callback_rejects_bad_state_and_denied(api):
    c = _connect(api)
    assert _callback(api, c, state="otro")["headers"]["location"] == "/?google=error&reason=state#ajustes"
    r = api.call("GET", "/api/google/callback", query="state=x&code=y")  # sin la cookie del inicio
    assert r["headers"]["location"] == "/?google=error&reason=state"
    assert _callback(api, c, error="access_denied", code="")["headers"]["location"] == "/?google=error&reason=denied#ajustes"
    assert "/garmin-stats/users/u2/google-token" not in api.ssm.params


def test_callback_without_health_scopes_revokes(api, monkeypatch):
    monkeypatch.setattr(GH, "OPENER", FakeGoogle(lambda m, p, q, b: {**fx("token.json"), "scope": "openid"}
                                                 if p.endswith("/token") else {}))
    r = _callback(api, _connect(api))
    assert r["headers"]["location"] == "/?google=error&reason=scopes#ajustes"
    assert any(c[1].endswith("/revoke") for c in GH.OPENER.calls)
    assert api.user(api.friend).get("source") is None


def test_callback_not_linked(api, monkeypatch):
    def route(m, p, q, b):
        if p.endswith("/identity"):
            raise Err(400, fx("error_not_linked.json"))
        return _google_ok(p)
    monkeypatch.setattr(GH, "OPENER", FakeGoogle(route))
    r = _callback(api, _connect(api, "back=onboarding&consent=1"))
    assert r["headers"]["location"] == "/?google=error&reason=not_linked#onboarding"
    me = _me(api)
    assert me["google"]["status"] == "not_linked" and me["google"]["linkUrl"] == "https://fitbit.google.com/auth/signup"
    assert not api.lam.invokes  # se descarga cuando esté enlazado (reintento cada hora o botón actualizar)
    assert api.call("POST", "/api/sync", {})["statusCode"] == 202


def test_disconnect_revokes_and_can_delete_data(api):
    _callback(api, _connect(api))
    api.s3.objs["users/u2/state/garmin.sqlite"] = b"datos"
    api.s3.objs["site/u/u2/data.js"] = b"window.__GARMIN__={};"
    api.s3.objs["users/u2/state/coach.json"] = b"{}"
    api.s3.objs["users/u2/state/sync_status.json"] = json.dumps({"status": "done", "finished": 1}).encode()
    api.google.calls.clear()
    r = api.call("POST", "/api/google/disconnect", {"deleteData": True})
    assert r["statusCode"] == 200
    assert json.loads(r["body"]) == {"ok": True, "deleted": True, "revoked": True}
    assert api.user(api.friend)["sourceChangedAt"]
    revoke = next(c for c in api.google.calls if c[1].endswith("/revoke"))
    assert revoke[3]["token"] == "1//refresco-de-prueba"
    assert "/garmin-stats/users/u2/google-token" not in api.ssm.params
    assert "users/u2/state/garmin.sqlite" not in api.s3.objs and "site/u/u2/data.js" not in api.s3.objs
    assert "users/u2/state/coach.json" in api.s3.objs  # el plan y lo demás se quedan
    u = api.user(api.friend)
    assert u["source"] is None and u["status"] == "onboarding"
    assert _me(api)["google"] == {"available": True, "connected": False}
    assert api.call("POST", "/api/google/disconnect", {})["statusCode"] == 409


def test_garmin_after_google_starts_from_scratch(api):
    _callback(api, _connect(api))
    api.call("POST", "/api/google/disconnect", {})
    api.s3.objs["users/u2/state/garmin.sqlite"] = b"datos de google"
    api.h._wipe_health_data("u2")
    assert "users/u2/state/garmin.sqlite" not in api.s3.objs
    assert api.user(api.friend)["dataSource"] == "google"  # sabe de qué fuente son los datos guardados


def test_account_delete_revokes_google(api):
    _callback(api, _connect(api))
    api.google.calls.clear()
    r = api.call("POST", "/api/account/delete", {})
    assert r["statusCode"] == 200
    assert any(c[1].endswith("/revoke") for c in api.google.calls)
    assert "/garmin-stats/users/u2/google-token" not in api.ssm.params


# ---------------------------------------------------------------- sincronización en AWS
@pytest.fixture
def sync_handler(tmp_path, monkeypatch):
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME", "GARMIN_STATS_ROOT")}
    s3, ssm, lam = FakeS3(), FakeSSM(), FakeLambda()
    s3.objs["admin/users.json"] = json.dumps({"users": [
        {"email": "a@x.com", "uid": "g1", "status": "active", "source": "google"},
        {"email": "b@x.com", "uid": "g2", "status": "google_not_linked", "source": "google"},
        {"email": "c@x.com", "uid": "g3", "status": "google_reauth", "source": "google"},
        {"email": "d@x.com", "uid": "m1", "status": "active"}]}).encode()
    h = _load("infra/lambda/sync/handler.py", "sync_handler_google_test", monkeypatch,
              {"BUCKET": "b", "AWS_LAMBDA_FUNCTION_NAME": "sync"}, {"s3": s3, "ssm": ssm, "lambda": lam})
    yield types.SimpleNamespace(h=h, s3=s3, ssm=ssm, lam=lam)
    for k, v in old_env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    time.tzset()


def _users(s3):
    return {u["uid"]: u for u in json.loads(s3.objs["admin/users.json"])["users"]}


def test_hourly_dispatch_includes_google_users(sync_handler):
    sync_handler.h._dispatch()
    assert sorted(i["uid"] for i in sync_handler.lam.invokes) == ["g1", "g2", "m1"]  # g3 tiene que volver a conectar


@pytest.mark.parametrize("err,status", [(GH.NotLinked(), "google_not_linked"), (GH.Reauth(401, "x"), "google_reauth")])
def test_google_errors_mark_the_user_without_alarm(sync_handler, monkeypatch, err, status):
    def boom(user, ctx):
        raise err
    monkeypatch.setattr(sync_handler.h, "_run", boom)
    out = sync_handler.h.handler({"uid": "g1"}, None)
    assert out["ok"] is False
    assert _users(sync_handler.s3)["g1"]["status"] == status
    assert json.loads(sync_handler.s3.objs["users/g1/state/sync_status.json"])["status"] == status


def test_not_linked_user_becomes_active_after_a_good_sync(sync_handler, monkeypatch):
    monkeypatch.setattr(sync_handler.h, "_run", lambda user, ctx: False)
    assert sync_handler.h.handler({"uid": "g2"}, None)["ok"]
    assert _users(sync_handler.s3)["g2"]["status"] == "active"


def test_google_client_reads_the_saved_permission(sync_handler):
    with pytest.raises(GH.Reauth):
        sync_handler.h._google_client("g1")  # sin permiso guardado
    sync_handler.ssm.params["/garmin-stats/users/g1/google-token"] = {"Value": json.dumps({"refresh_token": "r"})}
    sync_handler.ssm.params[ID_PARAM] = {"Value": "cid"}
    sync_handler.ssm.params[SECRET_PARAM] = {"Value": "sec"}
    c = sync_handler.h._google_client("g1")
    assert isinstance(c, GH.Client) and c._refresh == "r" and c._id == "cid"


def test_report_is_skipped_until_google_has_data(sync_handler, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_handler.h, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    assert sync_handler.h._has_data() is False  # sin base de datos
    store = Store(tmp_path / "data" / "garmin.sqlite")
    store.put("sleep", "2026-11-08", {"sleepTimeSeconds": 1})
    store.commit()
    assert sync_handler.h._has_data() is False  # solo sueño: aún no hay días ni entrenos
    store.put("daily_summary", "2026-11-08", GH.to_daily("2026-11-08", {"steps": 10}))
    store.close()
    assert sync_handler.h._has_data() is True


# ---------------------------------------------------------------- revisión: dominio, cookie, revocar, borrados, fechas
def test_only_the_public_host_is_accepted(api):
    r = api.call("GET", "/api/google/connect", query="back=ajustes", host="evil.example.com")
    assert r["headers"]["location"] == "/?google=error&reason=unavailable#ajustes"
    c = _connect(api)  # el bueno funciona
    cookie = c["cookies"][0].split(";")[0]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(c["headers"]["location"]).query)["state"][0]
    r = api.call("GET", "/api/google/callback", query=f"state={state}&code=x", cookies=[cookie], host="evil.example.com")
    assert r["headers"]["location"] == "/?google=error&reason=unavailable#ajustes"
    assert not [x for x in api.google.calls if x[1].endswith("/token")]  # nunca se manda otra vuelta a Google


def test_without_public_host_google_is_not_available(api, monkeypatch):
    monkeypatch.setattr(api.h, "PUBLIC_HOST", "")
    assert _me(api)["google"]["available"] is False
    assert api.call("GET", "/api/google/connect")["headers"]["location"] == "/?google=error&reason=unavailable"


@pytest.mark.parametrize("raw", ["%%%", GH.b64url(b"[1, 2]"), GH.b64url(b'"texto"'), GH.b64url(b"no es json")])
def test_junk_state_cookie_is_rejected_without_crashing(api, raw):
    r = api.call("GET", "/api/google/callback", query="state=x&code=y", cookies=[f"gs_google={raw}"])
    assert r["statusCode"] == 302 and r["headers"]["location"] == "/?google=error&reason=state"


def test_callback_enforces_the_consent_flag(api):
    tmp = GH.b64url(json.dumps({"v": "v", "s": "st", "b": "", "c": False, "u": "u1"}).encode())
    r = api.call("GET", "/api/google/callback", who=api.owner, query="state=st&code=y", cookies=[f"gs_google={tmp}"])
    assert r["headers"]["location"] == "/?google=error&reason=consent"
    assert not api.google.calls and "/garmin-stats/users/u1/google-token" not in api.ssm.params
    tmp = GH.b64url(json.dumps({"v": "v", "s": "st", "b": "", "c": True, "u": "u1"}).encode())
    r = api.call("GET", "/api/google/callback", who=api.owner, query="state=st&code=y", cookies=[f"gs_google={tmp}"])
    assert r["headers"]["location"] == "/?google=ok"
    assert api.user(api.owner)["consentAt"]


def test_failed_revoke_is_reported(api, monkeypatch, capsys):
    _callback(api, _connect(api))

    def route(m, p, q, b):
        if p.endswith("/revoke"):
            raise Err(503, {})
        return _google_ok(p)
    monkeypatch.setattr(GH, "OPENER", FakeGoogle(route))
    r = api.call("POST", "/api/google/disconnect", {})
    assert json.loads(r["body"]) == {"ok": True, "deleted": False, "revoked": False}
    assert "no ha retirado el permiso" in capsys.readouterr().out
    assert "/garmin-stats/users/u2/google-token" not in api.ssm.params  # se borra igualmente


def test_garmin_account_delete_does_not_touch_google(api, capsys):
    assert api.h._google_forget("u3") is None
    r = api.call("POST", "/api/account/delete", {}, who=api.garmin)
    assert r["statusCode"] == 200
    assert "google" not in capsys.readouterr().out and not api.google.calls


def _running(api, uid):
    api.s3.objs[f"users/{uid}/state/sync_status.json"] = json.dumps({"status": "running", "at": int(time.time())}).encode()


def test_no_wipe_while_a_sync_is_running(api):
    _callback(api, _connect(api))
    _running(api, "u2")
    api.s3.objs["users/u2/state/garmin.sqlite"] = b"datos"
    r = api.call("POST", "/api/google/disconnect", {"deleteData": True})
    assert r["statusCode"] == 409 and json.loads(r["body"])["error"] == api.h.BUSY
    assert "users/u2/state/garmin.sqlite" in api.s3.objs and api.user(api.friend)["source"] == "google"
    # sin borrar datos sí se puede desconectar (la descarga en marcha ya no subirá nada: sourceChangedAt)
    assert api.call("POST", "/api/google/disconnect", {})["statusCode"] == 200
    # pasar a Garmin borraría los datos de Google: tampoco con una descarga en marcha
    r = api.call("POST", "/api/onboarding/key", {"key": "x" * 40})
    assert r["statusCode"] == 409 and json.loads(r["body"])["error"] == api.h.BUSY
    # una descarga muerta (más de 16 min) no bloquea
    api.s3.objs["users/u2/state/sync_status.json"] = json.dumps({"status": "running", "at": int(time.time()) - 2000}).encode()
    assert not api.h._sync_running("u2")


def test_switching_to_google_while_garmin_sync_runs_is_busy(api):
    users = json.loads(api.s3.objs["admin/users.json"])
    users["users"][1].update(dataSource="garmin")  # tuvo Garmin, ahora sin fuente
    api.s3.objs["admin/users.json"] = json.dumps(users).encode()
    _running(api, "u2")
    r = _callback(api, _connect(api))
    assert r["headers"]["location"] == "/?google=error&reason=busy#ajustes"
    assert "/garmin-stats/users/u2/google-token" not in api.ssm.params
    api.s3.objs["users/u2/state/sync_status.json"] = json.dumps({"status": "done"}).encode()
    api.s3.objs["users/u2/state/garmin.sqlite"] = b"datos de garmin"
    assert _callback(api, _connect(api))["headers"]["location"] == "/?google=ok#ajustes"
    assert "users/u2/state/garmin.sqlite" not in api.s3.objs
    u = api.user(api.friend)
    assert u["dataSource"] == "google" and u["sourceChangedAt"]


def test_invalid_client_is_an_owner_error_not_reauth():
    def route(*a):
        raise Err(401, {"error": "invalid_client", "error_description": "The OAuth client was not found."})
    c, _ = client(route)
    with pytest.raises(GH.GoogleError) as e:
        c.identity()
    assert not isinstance(e.value, GH.Reauth)
    for code in ("invalid_grant", "unauthorized_client"):
        c, _ = client(lambda *a, code=code: (_ for _ in ()).throw(Err(400, {"error": code})))
        with pytest.raises(GH.Reauth):
            c.identity()


def test_today_is_madrid_date(monkeypatch, tmp_path):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    assert GH.today_local() == datetime.now(ZoneInfo("Europe/Madrid")).date()
    assert GH.Syncer(client(recorded())[0], Store(tmp_path / "g.sqlite")).today == GH.today_local()

    def missing(name):
        raise ZoneInfoNotFoundError(name)
    monkeypatch.setattr(GH, "ZoneInfo", missing)
    assert GH.today_local() == date.today()  # sin base de zonas: la hora local (la Lambda fija TZ a Madrid)


def test_sync_does_not_push_after_a_source_change(sync_handler, monkeypatch):
    h = sync_handler.h
    pushed = []
    monkeypatch.setattr(h, "_reset", lambda: None)

    def fake_run(user, ctx):
        # mientras descarga, la persona desconecta Google Health (la API apunta sourceChangedAt)
        reg = json.loads(sync_handler.s3.objs["admin/users.json"])
        reg["users"][0].update(source=None, status="onboarding", sourceChangedAt=int(time.time()) + 1)
        sync_handler.s3.objs["admin/users.json"] = json.dumps(reg).encode()
        h._push(user["uid"])  # lo que haría _run: aquí ya no sube nada
        pushed.append(True)
        return False
    monkeypatch.setattr(h, "_run", fake_run)
    out = h.handler({"uid": "g1"}, None)
    assert out == {"ok": False, "sourceChanged": True} and not pushed
    assert json.loads(sync_handler.s3.objs["users/g1/state/sync_status.json"])["status"] == "cancelled"
    assert _users(sync_handler.s3)["g1"]["status"] == "onboarding"  # no lo pisa con "active" ni "google_reauth"


def test_reauth_after_disconnect_is_not_a_reconnect_prompt(sync_handler, monkeypatch):
    def fake_run(user, ctx):
        reg = json.loads(sync_handler.s3.objs["admin/users.json"])
        reg["users"][0].update(source=None, status="onboarding")
        sync_handler.s3.objs["admin/users.json"] = json.dumps(reg).encode()
        raise GH.Reauth(401, "permiso borrado")
    monkeypatch.setattr(sync_handler.h, "_run", fake_run)
    assert sync_handler.h.handler({"uid": "g1"}, None)["sourceChanged"]
    assert _users(sync_handler.s3)["g1"]["status"] == "onboarding"
