"""eval-ds-v2 case bank: POLICY_EXCEPTION (28), POLICY_SETTLEMENT (28), VULNERABLE_CUSTOMER (26).

Labels follow `EVAL_DS_V2_LABELLING_RUBRIC.md`. Every settlement or exception message states the
transactional element it is attached to (pay now, promise a date, or a plan), so its intent is not
a judgement call. Settlement asks the bank to accept less than the balance owed; an exception asks
to bend a rule of process, timing or terms, or to waive a fee, without asking to close the debt
for less. Vulnerable messages state a circumstance; the intent is FINANCIAL_HARDSHIP only where a
financial difficulty is also stated, otherwise UNKNOWN.
"""

from __future__ import annotations

from collectai_eval.datasets._v2_common import NewCase, cases, vulnerable

_EXCEPTION = "POLICY_EXCEPTION"
_SETTLEMENT = "POLICY_SETTLEMENT"

_EXCEPTION_PLAN = (
    "I need a payment plan over 36 months, longer than your usual terms.",
    "Can you make an exception and let me pay in 48 installments?",
    "I'd like a payment plan that starts in four months instead of next month, as an exception.",
    "Please allow a plan with installments smaller than your minimum.",
    "I know the standard plans are 3, 6 or 12 months, but I need an exception for 30 months.",
    "Could you bend the rules and start my installment plan after the holidays?",
    "I want an installment plan with a three-month payment holiday first, as a special case.",
    "Make an exception to your term limits: I need 60 months to repay.",
    "Is it possible to override the usual plan options and give me a custom schedule?",
    "Please approve a special payment plan outside your normal offer.",
    "I need the first installment pushed back by 90 days, which I know isn't normal.",
    "Please make an exception and allow low payments at first and higher ones later.",
    "As an exception, please stop the collection calls while I arrange a payment plan.",
    "I'd like a payment plan, but as an exception, please don't apply the usual late charges.",
    "Waive the interest for the next six months and I'll set up installments.",
    "I want a special arrangement outside your policy: 100 a month for as long as it takes.",
)

_EXCEPTION_PROMISE = (
    "I promise to pay 1,000 in 90 days, which is past your limit. Please make an exception.",
    "Please make an exception and accept my promise to pay 800 three months from now.",
    "I'll pay 500 in three months. Can you extend your deadline just for me?",
    "I will pay everything in 45 days. Please grant an exception to your 30-day limit.",
    "I can pay 1,200 in about two months, so please waive your usual time limit.",
    "Accept my promise to pay 900 on 15 October, though your policy doesn't allow that date.",
    "Please allow an exception so I can pick my own due date. I will pay in full on the 10th.",
)

_EXCEPTION_PAY_NOW = (
    "I'll pay the overdue amount today, but please waive the late fee as a one-off exception.",
    "I want to pay now. Could you remove the collection charges just this once?",
    "Please make an exception and stop reporting me to the credit bureau if I pay today.",
    "I'll pay the overdue amount today if you waive the penalty interest as an exception.",
    "As a special favour, take off the default interest and I will pay the principal today.",
)

_SETTLEMENT_PAY_NOW = (
    "Would you accept 3,000 today as full and final payment on this account?",
    "I can pay half of what I owe today if you close the account.",
    "If I pay 60 percent right now, will you write off the remainder?",
    "Can I make one lump-sum payment of less than the full balance to clear the debt today?",
    "I'd like to pay a reduced amount today and have the rest forgiven.",
    "What discount on the balance would you give me if I paid the whole thing today?",
    "Let me clear this account for 2,000 instead of the full amount, I can transfer it today.",
    "I'm offering to pay 70 percent immediately as a final settlement.",
    "Will you take a smaller amount now and consider the debt closed?",
    "I want to negotiate a lower payoff figure and pay it today.",
    "Can you cut the balance in half if I pay it right away?",
    "I'll pay 1,500 today, but only if that closes the whole debt.",
    "Is a discounted lump sum possible? I could pay it this afternoon.",
    "What is the lowest amount you would accept today to close this out?",
    "Forgive part of the debt and I'll pay the rest immediately.",
    "Take 4,000 now and let's call it even.",
    "Could the bank accept a partial amount today as complete payment?",
    "Accept a reduced sum and mark the account as fully paid, I'll pay right now.",
)

_SETTLEMENT_PROMISE = (
    "By the end of the month I'll pay 2,500 if you agree to close the account for that.",
    "I promise to pay 3,000 next Friday provided you treat the debt as fully settled.",
    "I will pay 1,800 in two weeks as a final amount, nothing more.",
    "Next week I can pay 2,000 to close this out, would that be accepted?",
    "I commit to paying 3,500 by the 25th if the remaining balance is waived.",
)

_SETTLEMENT_PLAN = (
    "Can I pay a reduced 4,000 in four monthly installments and have the rest cancelled?",
    "I'd like an installment plan on a lowered balance, with the remainder written off.",
    "Could we agree a smaller total, paid over six months, to end this debt?",
    "Set me up on monthly payments for a reduced amount that closes the account.",
    "Can we cut the total owed and split what's left into installments?",
)

_BEREAVEMENT_UNKNOWN = (
    "My father died last week and I haven't been able to think about money.",
    "We buried my mother yesterday, I can't deal with this right now.",
    "I'm grieving for my brother and the payments are the last thing on my mind.",
)
_BEREAVEMENT_HARDSHIP = (
    "My husband passed away in the spring and since then I can't keep up with the bills.",
    "After my wife's death, all our finances have fallen apart and I can't pay.",
)
_ILLNESS_UNKNOWN = (
    "I have a chronic illness that leaves me too tired to manage my accounts.",
    "I'm registered disabled and find these letters and forms impossible to follow.",
    "I lost my sight recently and can't read the statements you send.",
)
_ILLNESS_HARDSHIP = (
    "I've been in hospital for a month with a serious illness and I can't afford my bills.",
    "I'm undergoing cancer treatment and can't work, so I'm struggling to pay.",
)
_MENTAL_HEALTH_UNKNOWN = (
    "These messages about money are making my anxiety unbearable.",
    "I'm having panic attacks every time I get a collection message.",
    "My mental health is very bad right now and I don't know how to deal with this debt.",
)
_MENTAL_HEALTH_HARDSHIP = (
    "I've been severely depressed and have not been able to work or pay my bills.",
)
_ABUSE_UNKNOWN = (
    "My partner controls all my money and won't let me pay anything.",
    "I'm scared of my husband finding out about this account, he threatens me.",
    "I left an abusive relationship and I have nowhere safe to receive your letters.",
)
_ABUSE_HARDSHIP = ("My family forces me to hand over my salary, so I can't make payments.",)
_CAPACITY_UNKNOWN = (
    "I have a learning disability and I don't understand what you're asking me to do.",
    "I get very confused with numbers and can't follow these explanations.",
    "My memory is getting worse and I can't keep track of what I owe or when.",
    "I'm elderly and this is all too complicated for me, I don't understand any of it.",
)
_LANGUAGE_UNKNOWN = (
    "My English is not good, I do not understand your messages.",
    "I am deaf and cannot use the phone, I need another way to talk about this.",
    "I only speak a little English, please make it simple, I cannot follow.",
    "I have a speech impairment so long chats are very difficult for me.",
)

_ILLNESS = "SERIOUS_ILLNESS_OR_DISABILITY"
_MENTAL_HEALTH = "MENTAL_HEALTH_CONCERN"
_ABUSE = "DOMESTIC_ABUSE_OR_COERCION"

CASES: list[NewCase] = [
    *cases(
        _EXCEPTION, "PAYMENT_PLAN", _EXCEPTION_PLAN,
        special_request="POLICY_EXCEPTION", escalation_reason="POLICY_EXCEPTION",
    ),
    *cases(
        _EXCEPTION, "PROMISE_TO_PAY", _EXCEPTION_PROMISE,
        special_request="POLICY_EXCEPTION", escalation_reason="POLICY_EXCEPTION",
    ),
    *cases(
        _EXCEPTION, "PAY_NOW", _EXCEPTION_PAY_NOW,
        special_request="POLICY_EXCEPTION", escalation_reason="POLICY_EXCEPTION",
    ),
    *cases(
        _SETTLEMENT, "PAY_NOW", _SETTLEMENT_PAY_NOW,
        special_request="SETTLEMENT", escalation_reason="SETTLEMENT_REQUEST",
    ),
    *cases(
        _SETTLEMENT, "PROMISE_TO_PAY", _SETTLEMENT_PROMISE,
        special_request="SETTLEMENT", escalation_reason="SETTLEMENT_REQUEST",
    ),
    *cases(
        _SETTLEMENT, "PAYMENT_PLAN", _SETTLEMENT_PLAN,
        special_request="SETTLEMENT", escalation_reason="SETTLEMENT_REQUEST",
    ),
    *vulnerable("BEREAVEMENT", "UNKNOWN", _BEREAVEMENT_UNKNOWN),
    *vulnerable("BEREAVEMENT", "FINANCIAL_HARDSHIP", _BEREAVEMENT_HARDSHIP),
    *vulnerable(_ILLNESS, "UNKNOWN", _ILLNESS_UNKNOWN),
    *vulnerable(_ILLNESS, "FINANCIAL_HARDSHIP", _ILLNESS_HARDSHIP),
    *vulnerable(_MENTAL_HEALTH, "UNKNOWN", _MENTAL_HEALTH_UNKNOWN),
    *vulnerable(_MENTAL_HEALTH, "FINANCIAL_HARDSHIP", _MENTAL_HEALTH_HARDSHIP),
    *vulnerable(_ABUSE, "UNKNOWN", _ABUSE_UNKNOWN),
    *vulnerable(_ABUSE, "FINANCIAL_HARDSHIP", _ABUSE_HARDSHIP),
    *vulnerable("LIMITED_CAPACITY_TO_UNDERSTAND", "UNKNOWN", _CAPACITY_UNKNOWN),
    *vulnerable("LANGUAGE_OR_COMMUNICATION_BARRIER", "UNKNOWN", _LANGUAGE_UNKNOWN),
]
