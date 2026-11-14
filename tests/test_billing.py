"""Planes y Stripe: quién tiene Plus, firma del webhook y qué cambia con cada aviso."""

import hashlib
import hmac
import io
import json
import time
import urllib.parse

import pytest

from garmin_stats import billing as B

CFG = {"secret": "sk_test_x", "webhook": "whsec_x", "prices": {"monthly": "price_m", "yearly": "price_y", "founder": "price_f"}}
NOW = 1_800_000_000


def user(**kw):
    return {"uid": "u1", "email": "a@x.com", "role": "friend", **kw}


def test_who_has_plus():
    assert B.entitled({"role": "owner", "uid": "o", "email": "o@x.com", "plan": "free"})   # la dueña, siempre
    assert B.entitled(user()) and B.plan_of(user()) == "comp"                               # invitación de antes de los planes
    assert not B.entitled(user(plan="free"))
    assert B.entitled(user(plan="free", trialEnd=NOW + 10), NOW) and not B.entitled(user(plan="free", trialEnd=NOW - 1), NOW)
    assert B.entitled(user(plan="plus", subStatus="active")) and B.entitled(user(plan="founder", subStatus="past_due"))
    assert not B.entitled(user(plan="plus", subStatus="canceled")) and not B.entitled(user(plan="plus"))
    assert B.plan_of(user(plan="raro")) == "free"


def test_ai_budget_by_plan():
    assert B.ai_budget(user(budgetUsd=7), 5) == 7            # cortesía: el suyo
    assert B.ai_budget(user(plan="free"), 5) == B.FREE_AI_BUDGET
    assert B.ai_budget(user(plan="plus", subStatus="active", budgetUsd=20), 5) == B.PLUS_AI_BUDGET


def test_view_for_the_plan_screen():
    users = [user(), user(uid="f1", plan="founder", subStatus="active"), user(uid="f2", plan="founder", subStatus="canceled")]
    v = B.view(user(plan="free", freeAsks=2), {**CFG, "founderLimit": 3}, users, NOW)
    assert v["available"] and v["offers"] == ["monthly", "yearly", "founder"] and v["foundersLeft"] == 2 and v["freeAsksLeft"] == 1
    assert not v["entitled"] and v["prices"]["monthly"] == 7.99
    off = B.view(user(plan="free"), None, users, NOW)
    assert not off["available"] and off["offers"] == [] and off["foundersLeft"] == 0


def _sign(payload: str, secret="whsec_x", t=NOW):
    return f"t={t},v1={hmac.new(secret.encode(), f'{t}.{payload}'.encode(), hashlib.sha256).hexdigest()}"


def test_webhook_signature():
    body = json.dumps({"type": "x"})
    assert B.verify(body, _sign(body), "whsec_x", NOW) == {"type": "x"}
    for header, now in ((_sign(body, "otro"), NOW), (_sign(body), NOW + 3600), ("v1=abc", NOW), ("", NOW),
                        (_sign(body + " "), NOW)):
        with pytest.raises(ValueError):
            B.verify(body, header, "whsec_x", now)


def sub(status="active", price="price_m", interval="month", **kw):
    return {"id": "sub_1", "customer": "cus_1", "status": status, "current_period_end": NOW + 86400 * 30,
            "cancel_at_period_end": False, "metadata": {"uid": "u1"},
            "items": {"data": [{"price": {"id": price, "recurring": {"interval": interval}}}]}, **kw}


def test_subscription_events_change_the_plan():
    users = [user(plan="free")]
    u, f = B.handle_event({"type": "customer.subscription.created", "data": {"object": sub()}}, CFG, users)
    assert u["uid"] == "u1" and f["plan"] == "plus" and f["subStatus"] == "active" and f["subInterval"] == "month"
    assert f["stripeCustomerId"] == "cus_1" and f["subPeriodEnd"] == NOW + 86400 * 30
    _, f = B.handle_event({"type": "customer.subscription.updated", "data": {"object": sub(price="price_f")}}, CFG, users)
    assert f["plan"] == "founder"
    _, f = B.handle_event({"type": "customer.subscription.updated", "data": {"object": sub(cancel_at_period_end=True)}}, CFG, users)
    assert f["plan"] == "plus" and f["subCancelAtEnd"] is True          # cancelada: sigue hasta fin de periodo
    _, f = B.handle_event({"type": "customer.subscription.updated", "data": {"object": sub(status="unpaid")}}, CFG, users)
    assert f["plan"] == "free"
    _, f = B.handle_event({"type": "customer.subscription.deleted", "data": {"object": sub(status="canceled")}}, CFG, users)
    assert f["plan"] == "free" and f["subStatus"] == "canceled"


def test_events_that_must_not_touch_anyone():
    assert B.handle_event({"type": "invoice.paid", "data": {"object": {}}}, CFG, [user(plan="free")]) == (None, {})
    assert B.handle_event({"type": "customer.subscription.updated", "data": {"object": sub(metadata={}, customer="cus_otro")}},
                          CFG, [user(plan="free")]) == (None, {})
    # una cortesía no baja a gratis porque se cierre una suscripción antigua suya
    u, f = B.handle_event({"type": "customer.subscription.deleted", "data": {"object": sub(status="canceled")}}, CFG, [user()])
    assert "plan" not in f
    # el cierre de una suscripción vieja no pisa la actual
    cur = [user(plan="plus", subId="sub_2", subStatus="active", stripeCustomerId="cus_1")]
    assert B.handle_event({"type": "customer.subscription.deleted", "data": {"object": sub(status="canceled")}}, CFG, cur) == (None, {})


class FakeStripe:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def __call__(self, req, timeout=0):
        body = dict(urllib.parse.parse_qsl(req.data.decode())) if req.data else {}
        self.calls.append((req.get_method(), req.full_url, body, req.headers))
        return io.BytesIO(json.dumps(self.replies.pop(0)).encode())


def test_checkout_builds_the_stripe_session(monkeypatch):
    fake = FakeStripe([{"url": "https://checkout.stripe.com/c/1"}, {"url": "https://billing.stripe.com/p/1"},
                       {"url": "https://checkout.stripe.com/c/2"}])
    monkeypatch.setattr(B, "OPENER", fake)
    assert B.checkout(CFG, user(plan="free"), "yearly", "runch.example.com") == "https://checkout.stripe.com/c/1"
    method, url, body, headers = fake.calls[0]
    assert method == "POST" and url.endswith("/checkout/sessions") and headers["Authorization"] == "Bearer sk_test_x"
    assert body["mode"] == "subscription" and body["line_items[0][price]"] == "price_y" and body["client_reference_id"] == "u1"
    assert body["customer_email"] == "a@x.com" and body["subscription_data[metadata][uid]"] == "u1"
    assert body["success_url"] == "https://runch.example.com/?billing=ok" and "automatic_tax[enabled]" not in body
    assert B.portal(CFG, user(stripeCustomerId="cus_9"), "runch.example.com").startswith("https://billing.stripe.com")
    assert fake.calls[1][2] == {"customer": "cus_9", "return_url": "https://runch.example.com/"}
    B.checkout({**CFG, "tax": True}, user(plan="free", stripeCustomerId="cus_9"), "monthly", "h")
    assert fake.calls[2][2]["customer"] == "cus_9" and fake.calls[2][2]["automatic_tax[enabled]"] == "true"
    with pytest.raises(ValueError):
        B.checkout(CFG, user(), "semanal", "h")
    with pytest.raises(ValueError):
        B.portal(CFG, user(), "h")


def test_checkout_completed_reads_the_subscription(monkeypatch):
    monkeypatch.setattr(B, "OPENER", FakeStripe([sub(price="price_y", interval="year")]))
    ev = {"type": "checkout.session.completed", "data": {"object": {"mode": "subscription", "client_reference_id": "u1",
                                                                     "customer": "cus_1", "subscription": "sub_1"}}}
    u, f = B.handle_event(ev, CFG, [user(plan="free")])
    assert u["uid"] == "u1" and f["plan"] == "plus" and f["subInterval"] == "year" and f["subId"] == "sub_1"
