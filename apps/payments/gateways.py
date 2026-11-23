"""
Payment gateways behind one interface (create / verify / inquire) so the
active gateway can be switched from the admin panel. Real gateways
(Zarinpal, IDPay, ...) are added as new classes in GATEWAYS.

Amounts are always passed in Toman; each gateway converts to its own unit.
"""

import secrets
from dataclasses import dataclass, field
from decimal import Decimal

from django.urls import reverse


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class CreateResult:
    authority: str
    redirect_url: str


@dataclass(frozen=True)
class VerifyResult:
    success: bool
    amount: Decimal | None = None
    ref_id: str = ""
    card_pan: str = ""
    raw: dict = field(default_factory=dict)


class BaseGateway:
    name = ""
    title = ""

    def create(self, *, amount: Decimal, callback_url: str, description: str, mobile: str = "") -> CreateResult:
        raise NotImplementedError

    def verify(self, *, authority: str, amount: Decimal) -> VerifyResult:
        raise NotImplementedError

    def inquire(self, *, authority: str, amount: Decimal) -> VerifyResult:
        return self.verify(authority=authority, amount=amount)


class MockGateway(BaseGateway):
    """Development gateway: a local page lets you choose success or failure."""

    name = "mock"
    title = "درگاه آزمایشی"

    def create(self, *, amount, callback_url, description, mobile=""):
        from .models import MockTransaction

        authority = "MOCK-" + secrets.token_hex(10).upper()
        MockTransaction.objects.create(authority=authority, amount=amount, callback_url=callback_url)
        return CreateResult(authority=authority, redirect_url=reverse("payments:mock_gateway", args=[authority]))

    def verify(self, *, authority, amount):
        from .models import MockTransaction

        tx = MockTransaction.objects.filter(authority=authority).first()
        if tx is None or not tx.paid:
            return VerifyResult(success=False, raw={"status": "not_paid"})
        # The bank reports the amount it actually charged; the caller compares it.
        return VerifyResult(
            success=True, amount=tx.amount, ref_id=f"REF{tx.pk:08d}", card_pan="603799******1234",
            raw={"status": "paid", "amount": str(tx.amount)},
        )


GATEWAYS = {cls.name: cls for cls in (MockGateway,)}


def get_gateway(name: str) -> BaseGateway:
    try:
        return GATEWAYS[name]()
    except KeyError:
        raise GatewayError(f"Unknown gateway: {name}")
