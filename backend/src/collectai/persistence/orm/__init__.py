"""SQLAlchemy 2.0 declarative ORM classes for the 12 entities this story's
ACs exercise (Customer, Account, DelinquencyRecord, DelinquentItem,
Interaction, Conversation, PromiseToPay, PaymentEvent, PaymentArrangement,
HardshipCase, Dispute, EscalationCase). The remaining 11 business tables are
created by the migrations with full fidelity but deliberately have no ORM
class here (component-map.md: no story in this group reads/writes them yet).
"""

from __future__ import annotations

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.base import Base
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm, DelinquentItemOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm

__all__ = [
    "AccountOrm",
    "Base",
    "ConversationOrm",
    "CustomerOrm",
    "DelinquencyRecordOrm",
    "DelinquentItemOrm",
    "DisputeOrm",
    "EscalationCaseOrm",
    "HardshipCaseOrm",
    "InteractionOrm",
    "PaymentArrangementOrm",
    "PaymentEventOrm",
    "PromiseToPayOrm",
]
