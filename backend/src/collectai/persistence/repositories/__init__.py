"""Customer-scoped repositories for the 12 ORM-mapped entities."""

from __future__ import annotations

from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.conversation_repository import ConversationRepository
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.delinquent_item_repository import DelinquentItemRepository
from collectai.persistence.repositories.dispute_repository import DisputeRepository
from collectai.persistence.repositories.escalation_case_repository import EscalationCaseRepository
from collectai.persistence.repositories.hardship_case_repository import HardshipCaseRepository
from collectai.persistence.repositories.interaction_repository import InteractionRepository
from collectai.persistence.repositories.payment_arrangement_repository import (
    PaymentArrangementRepository,
)
from collectai.persistence.repositories.payment_event_repository import PaymentEventRepository
from collectai.persistence.repositories.promise_to_pay_repository import PromiseToPayRepository

__all__ = [
    "AccountRepository",
    "ConversationRepository",
    "CustomerRepository",
    "DelinquencyRecordRepository",
    "DelinquentItemRepository",
    "DisputeRepository",
    "EscalationCaseRepository",
    "HardshipCaseRepository",
    "InteractionRepository",
    "PaymentArrangementRepository",
    "PaymentEventRepository",
    "PromiseToPayRepository",
]
