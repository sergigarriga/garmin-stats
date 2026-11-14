"""Planes y facturación (Stripe). Python puro: la API de Stripe se llama con urllib, sin SDK.

Planes (campo `plan` de cada persona en admin/users.json):
  comp     invitación de cortesía: todo incluido, sin pagar (las personas invitadas hasta ahora y la dueña)
  free     gratis: datos y gráficas; sin coach, chat, resumen, foto de comida ni lista de la compra
  plus     Runch Plus de pago (mensual o anual)
  founder  Fundadores: Plus a precio reducido para siempre (plazas limitadas)

La suscripción la lleva Stripe (Checkout + portal del cliente); la app solo guarda el estado que llega por webhook:
`stripeCustomerId`, `subId`, `subStatus`, `subPeriodEnd`, `subCancelAtEnd`, `subInterval`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1"
PLANS = ("comp", "free", "plus", "founder")
PAID = ("plus", "founder")
# Lo que se enseña en la web (el cobro real lo fija el precio de Stripe).
PRICES_EUR = {"monthly": 7.99, "yearly": 59.0, "founder": 4.99}
FOUNDER_LIMIT = 50
TRIAL_DAYS = 14
FREE_ASKS = 3            # preguntas de prueba al chat en el plan gratis
FREE_AI_BUDGET = 0.30    # $ de IA al mes en el plan gratis (un texto barato al día)
PLUS_AI_BUDGET = 4.0     # $ de IA al mes en los planes de pago
GOOD = ("active", "trialing", "past_due")  # past_due: Stripe reintenta el cobro unos días; no se corta al momento
TOLERANCE = 300          # s: un webhook más viejo que esto se rechaza (repetición)
OPENER = urllib.request.urlopen  # los tests lo sustituyen


class StripeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- planes
def plan_of(user: dict) -> str:
    """Plan de la persona. Sin campo `plan` es una invitación de antes de que hubiera planes: cortesía."""
    if user.get("role") == "owner":
        return "comp"
    p = user.get("plan") or "comp"
    return p if p in PLANS else "free"


def entitled(user: dict, now: float | None = None) -> bool:
    """¿Tiene las funciones de pago ahora mismo?"""
    now = time.time() if now is None else now
    p = plan_of(user)
    if p == "comp":
        return True
    if p in PAID and user.get("subStatus") in GOOD:
        return True
    return bool(user.get("trialEnd") and user["trialEnd"] > now)  # prueba de 14 días sin tarjeta


def ai_budget(user: dict, default: float, now: float | None = None) -> float:
    """Tope de IA del mes ($): el suyo si es cortesía, el de Plus si paga y el mínimo si está en gratis."""
    if not entitled(user, now):
        return FREE_AI_BUDGET
    return float(user.get("budgetUsd") or default) if plan_of(user) == "comp" else PLUS_AI_BUDGET


def view(user: dict, cfg: dict | None, users: list[dict], now: float | None = None) -> dict:
    """Lo que la web necesita para la pantalla «Tu plan»."""
    founders = sum(1 for u in users if plan_of(u) == "founder" and u.get("subStatus") in GOOD)
    limit = int((cfg or {}).get("founderLimit") or FOUNDER_LIMIT)
    prices = (cfg or {}).get("prices") or {}
    return {
        "plan": plan_of(user), "entitled": entitled(user, now),
        "status": user.get("subStatus"), "periodEnd": user.get("subPeriodEnd"),
        "cancelAtEnd": bool(user.get("subCancelAtEnd")), "interval": user.get("subInterval"),
        "trialEnd": user.get("trialEnd") if (user.get("trialEnd") or 0) > (now or time.time()) else None,
        "available": bool(cfg and cfg.get("secret") and prices.get("monthly")),
        "canManage": bool(cfg and cfg.get("secret") and user.get("stripeCustomerId")),
        "prices": {**PRICES_EUR, **{k: v for k, v in ((cfg or {}).get("display") or {}).items() if k in PRICES_EUR}},
        "offers": [k for k in ("monthly", "yearly", "founder") if prices.get(k)],
        "foundersLeft": max(0, limit - founders) if prices.get("founder") else 0,
        "freeAsksLeft": max(0, FREE_ASKS - int(user.get("freeAsks") or 0)),
        "trialDays": TRIAL_DAYS,
    }


# ---------------------------------------------------------------- Stripe (HTTP)
def _flat(obj, prefix="") -> list[tuple[str, str]]:
    """Diccionario anidado → pares clave[sub][0]=valor, como espera Stripe (form-encoded)."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _flat(v, f"{prefix}[{k}]" if prefix else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += _flat(v, f"{prefix}[{i}]")
    elif obj is not None:
        out.append((prefix, "true" if obj is True else "false" if obj is False else str(obj)))
    return out


def request(secret: str, method: str, path: str, params: dict | None = None) -> dict:
    data = urllib.parse.urlencode(_flat(params or {})).encode() if method != "GET" else None
    url = API + path + (("?" + urllib.parse.urlencode(_flat(params or {}))) if method == "GET" and params else "")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded",
        "Stripe-Version": "2024-06-20"})
    try:
        with OPENER(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"]
        except Exception:  # noqa: BLE001
            msg = f"HTTP {e.code}"
        raise StripeError(e.code, msg) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise StripeError(503, f"sin conexión con Stripe ({type(e).__name__})") from None


def checkout(cfg: dict, user: dict, offer: str, host: str) -> str:
    """Crea la página de pago de Stripe para esta persona y devuelve su dirección."""
    price = (cfg.get("prices") or {}).get(offer)
    if not price:
        raise ValueError("Ese plan no está disponible.")
    params = {
        "mode": "subscription", "line_items": [{"price": price, "quantity": 1}],
        "client_reference_id": user["uid"], "locale": "es", "allow_promotion_codes": True,
        "success_url": f"https://{host}/?billing=ok", "cancel_url": f"https://{host}/?billing=cancel",
        "subscription_data": {"metadata": {"uid": user["uid"], "offer": offer}},
        "metadata": {"uid": user["uid"], "offer": offer},
        "consent_collection": {"terms_of_service": "required"} if cfg.get("requireTerms") else None,
        "automatic_tax": {"enabled": True} if cfg.get("tax") else None,
        "billing_address_collection": "required" if cfg.get("tax") else None,
    }
    if user.get("stripeCustomerId"):
        params["customer"] = user["stripeCustomerId"]
        if cfg.get("tax"):
            params["customer_update"] = {"address": "auto"}
    else:
        params["customer_email"] = user["email"]
    return request(cfg["secret"], "POST", "/checkout/sessions", params)["url"]


def portal(cfg: dict, user: dict, host: str) -> str:
    """Portal del cliente de Stripe: cambiar tarjeta, ver facturas, cancelar."""
    if not user.get("stripeCustomerId"):
        raise ValueError("Aún no tienes una suscripción.")
    return request(cfg["secret"], "POST", "/billing_portal/sessions",
                   {"customer": user["stripeCustomerId"], "return_url": f"https://{host}/"})["url"]


# ---------------------------------------------------------------- webhook
def verify(payload: str, header: str, secret: str, now: float | None = None) -> dict:
    """Comprueba la firma `Stripe-Signature` (HMAC-SHA256 de "t.payload") y devuelve el evento. ValueError si no vale."""
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    sigs = [p.split("=", 1)[1] for p in (header or "").split(",") if p.startswith("v1=")]
    try:
        t = int(parts.get("t", ""))
    except ValueError:
        raise ValueError("firma sin fecha") from None
    if abs((time.time() if now is None else now) - t) > TOLERANCE:
        raise ValueError("firma caducada")
    want = hmac.new(secret.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(want, s) for s in sigs):
        raise ValueError("firma no válida")
    return json.loads(payload)


def from_subscription(sub: dict, cfg: dict) -> dict:
    """Campos de la persona a partir de una suscripción de Stripe."""
    item = ((sub.get("items") or {}).get("data") or [{}])[0]
    price = item.get("price") or {}
    status = sub.get("status")
    founder = price.get("id") and price.get("id") == (cfg.get("prices") or {}).get("founder")
    fields = {
        "subId": sub.get("id"), "subStatus": status, "stripeCustomerId": sub.get("customer"),
        "subPeriodEnd": sub.get("current_period_end") or item.get("current_period_end"),
        "subCancelAtEnd": bool(sub.get("cancel_at_period_end")),
        "subInterval": (price.get("recurring") or {}).get("interval"),
    }
    # Activa (o con el cobro en reintento): plan de pago. Terminada o sin pagar: vuelve al plan gratis.
    fields["plan"] = ("founder" if founder else "plus") if status in GOOD else "free"
    return fields


def handle_event(event: dict, cfg: dict, users: list[dict]) -> tuple[dict | None, dict]:
    """Aplica un evento de Stripe. Devuelve (persona, campos a guardar), o (None, {}) si no hay nada que hacer."""
    kind, obj = event.get("type", ""), (event.get("data") or {}).get("object") or {}

    def who(uid=None, customer=None):
        return next((u for u in users if (uid and u["uid"] == uid) or (customer and u.get("stripeCustomerId") == customer)), None)

    if kind == "checkout.session.completed":
        u = who(uid=obj.get("client_reference_id") or (obj.get("metadata") or {}).get("uid"), customer=obj.get("customer"))
        if not u or obj.get("mode") != "subscription":
            return None, {}
        fields = {"stripeCustomerId": obj.get("customer")}
        if obj.get("subscription"):
            sub = request(cfg["secret"], "GET", f"/subscriptions/{obj['subscription']}")
            fields.update(from_subscription(sub, cfg))
        return u, fields
    if kind.startswith("customer.subscription."):
        u = who(uid=(obj.get("metadata") or {}).get("uid"), customer=obj.get("customer"))
        if not u or plan_of(u) == "comp":  # una cortesía no pasa a gratis porque se cierre una suscripción antigua
            return (u, {"stripeCustomerId": obj.get("customer")}) if u else (None, {})
        if u.get("subId") and obj.get("id") != u["subId"] and obj.get("status") not in GOOD:
            return None, {}  # el cierre de una suscripción vieja no toca la actual
        fields = from_subscription(obj, cfg)
        if kind.endswith(".deleted"):
            fields.update({"plan": "free", "subStatus": "canceled", "subCancelAtEnd": False})
        return u, fields
    return None, {}
