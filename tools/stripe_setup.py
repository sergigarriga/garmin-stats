"""Prepara Stripe para Runch: producto, precios, portal del cliente y webhook. Se puede relanzar (no duplica).

Antes: crea la cuenta en stripe.com y guarda la clave secreta (de prueba primero: sk_test_...) en
~/.config/garmin/stripe.json  →  {"secret": "sk_test_..."}        (chmod 600; nunca en el repositorio ni en un chat)

Uso:  PYTHONPATH=src python3 tools/stripe_setup.py https://tu-dominio        (el dominio público de la app)
Después: infra/deploy.sh  (sube la configuración cifrada a AWS y activa los pagos).

Para pasar a real: repite con la clave sk_live_... (el script crea lo mismo en modo real).
"""

import json
import sys
from pathlib import Path

from garmin_stats import billing as B

CONF = Path("~/.config/garmin/stripe.json").expanduser()
PRODUCT = "Runch Plus"
# clave → (céntimos, intervalo, nombre)
OFFERS = {"monthly": (799, "month", "Runch Plus mensual"), "yearly": (5900, "year", "Runch Plus anual"),
          "founder": (499, "month", "Runch Plus Fundadores")}
EVENTS = ["checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
          "customer.subscription.deleted"]


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        sys.exit(__doc__)
    site = sys.argv[1].rstrip("/")
    cfg = json.loads(CONF.read_text())
    sk = cfg["secret"]
    call = lambda m, p, q=None: B.request(sk, m, p, q)  # noqa: E731

    products = call("GET", "/products", {"limit": 100, "active": True})["data"]
    product = next((p for p in products if p["name"] == PRODUCT), None) or call("POST", "/products", {
        "name": PRODUCT, "description": "Coach con IA, plan de entreno, chat, resumen diario, comida y lista de la compra"})
    existing = call("GET", "/prices", {"product": product["id"], "limit": 100, "active": True})["data"]
    prices = {}
    for key, (cents, interval, name) in OFFERS.items():
        found = next((p for p in existing if p.get("lookup_key") == f"runch_{key}"), None)
        prices[key] = (found or call("POST", "/prices", {
            "product": product["id"], "currency": "eur", "unit_amount": cents, "nickname": name,
            "recurring": {"interval": interval}, "lookup_key": f"runch_{key}", "tax_behavior": "inclusive"}))["id"]

    url = f"{site}/api/stripe/webhook"
    hooks = call("GET", "/webhook_endpoints", {"limit": 100})["data"]
    if not any(h["url"] == url for h in hooks) or not cfg.get("webhook"):
        for h in hooks:
            if h["url"] == url:  # sin su secreto guardado no sirve: se rehace
                call("DELETE", f"/webhook_endpoints/{h['id']}")
        cfg["webhook"] = call("POST", "/webhook_endpoints", {"url": url, "enabled_events": EVENTS,
                                                             "description": "Runch: estado de las suscripciones"})["secret"]

    if not call("GET", "/billing_portal/configurations", {"limit": 1, "active": True})["data"]:
        call("POST", "/billing_portal/configurations", {
            "business_profile": {"headline": "Runch Plus", "privacy_policy_url": f"{site}/auth/privacidad",
                                 "terms_of_service_url": f"{site}/auth/condiciones"},
            "features": {"invoice_history": {"enabled": True}, "payment_method_update": {"enabled": True},
                         "subscription_cancel": {"enabled": True, "mode": "at_period_end"}}})

    cfg.update(prices=prices, founderLimit=cfg.get("founderLimit") or B.FOUNDER_LIMIT, site=site)
    CONF.write_text(json.dumps(cfg, indent=1))
    CONF.chmod(0o600)
    live = sk.startswith("sk_live_")
    print(f"Stripe listo ({'REAL' if live else 'modo de prueba'}): producto, {len(prices)} precios, webhook y portal.")
    print("Siguiente paso: infra/deploy.sh")


if __name__ == "__main__":
    main()
