"""eval-ds-v2 case bank: FINANCIAL_HARDSHIP, DISPUTE and REQUEST_HUMAN (24 new cases each).

Labels follow `EVAL_DS_V2_LABELLING_RUBRIC.md`. Hardship messages state a financial cause and
nothing else (no illness, bereavement or safety wording, which would be a vulnerability signal);
dispute messages contest the debt, an amount, a fee or ownership; human-request messages ask for
a person and nothing else.
"""

from __future__ import annotations

from collectai_eval.datasets._v2_common import NewCase, cases

_FINANCIAL_HARDSHIP = (
    "My company let me go last month and I have no income at the moment.",
    "I was made redundant two weeks ago and I'm still looking for work.",
    "My employer has cut my salary by a third, so I can't keep up with my bills.",
    "My contract ended and I haven't found a new position yet.",
    "Business has been very slow this quarter and I can't cover my obligations.",
    "I'm the only earner in my household and my income has dropped sharply.",
    "My salary has been delayed for two months and I have nothing to pay with.",
    "I had to spend my savings on an emergency car repair and now I'm short.",
    "Since my overtime was removed I earn much less than before.",
    "I'm a freelancer and several of my clients stopped paying me.",
    "My rent went up a lot and there's nothing left for anything else.",
    "I've been on unpaid leave and can't meet my payments right now.",
    "I lost my main source of income and I'm struggling to cover basic costs.",
    "My bonus was cancelled and I was counting on it to pay this.",
    "I am supporting several relatives and my own money has run out.",
    "Everything has become expensive and my pay hasn't changed, I'm falling behind.",
    "My shop had to close last month, so I don't have any earnings.",
    "I've had unexpected expenses and I'm in a difficult financial position.",
    "Work dried up over the summer and I'm behind on everything.",
    "I don't have the money at the moment because my hours were reduced.",
    "My spouse lost their job and our household income has halved.",
    "I'm between jobs right now and cannot afford to make payments.",
    "After my pay cut, I can no longer afford my monthly obligations.",
    "Honestly I'm broke this month, my income just isn't enough anymore.",
)

_DISPUTE = (
    "I have never had an account with you, so this debt cannot be mine.",
    "The overdue balance you show is far higher than what I actually borrowed.",
    "I paid this off in full last year and have the receipt to prove it.",
    "You've charged me a late fee twice for the same month.",
    "This transaction is fraud, I was abroad when it was made.",
    "I cancelled this service before the date you're billing me for.",
    "The interest on my statement doesn't match my agreement.",
    "I returned the item and was told the charge would be reversed, yet it's still here.",
    "There's a payment on my statement that I didn't authorise.",
    "My records show a different balance from yours and I don't accept yours.",
    "Someone else opened this account using my details, it isn't my debt.",
    "I was charged for a fee I was never told about, and I contest it.",
    "You are collecting on a debt that was cleared with the previous lender years ago.",
    "The date of default you've listed is wrong, and so is the amount.",
    "I question this balance, it includes charges from a card I closed.",
    "That overdue amount is incorrect, please check your calculations.",
    "I dispute the collection fee, nobody agreed to it.",
    "This account has been paid; your system hasn't updated it.",
    "I never received the goods that this charge is for.",
    "The name on this account is not mine, you have the wrong person.",
    "I'm formally disputing this debt and asking for proof that I owe it.",
    "Why am I being charged again? I already cleared this amount two months ago.",
    "The statement shows a payment I made as unpaid. That is a mistake.",
    "Your figures are wrong and I will not pay an amount I don't owe.",
)

_REQUEST_HUMAN = (
    "Please put me through to a member of staff.",
    "Is there a real person I can speak with?",
    "I'd like to speak to someone at the bank, not a chatbot.",
    "Can an actual agent take over this conversation?",
    "Human please.",
    "I prefer talking to a person about my account.",
    "Stop the automated replies and connect me to an advisor.",
    "Let me talk to your collections team directly.",
    "I don't trust automated systems, get me a real employee.",
    "Can I be transferred to a supervisor?",
    "I need a human being to look at this.",
    "Connect me to customer service staff, please.",
    "Are you a robot? I want a real person.",
    "Please pass me to a live agent.",
    "I'd like to arrange a conversation with an officer.",
    "This is too complicated for a chat, I want to speak to someone.",
    "Can somebody from your team call me?",
    "Give me a person, not a script.",
    "Talk to a human. Now.",
    "I'd feel more comfortable with a real advisor handling this.",
    "May I speak with a real agent instead of the assistant?",
    "Please hand this over to one of your human colleagues.",
    "I refuse to continue with an AI, transfer me.",
    "Can a specialist officer contact me about my account?",
)

CASES: list[NewCase] = [
    *cases(
        "FINANCIAL_HARDSHIP",
        "FINANCIAL_HARDSHIP",
        _FINANCIAL_HARDSHIP,
        escalation_reason="FINANCIAL_HARDSHIP",
    ),
    *cases("DISPUTE", "DISPUTE", _DISPUTE, escalation_reason="DISPUTE"),
    *cases("REQUEST_HUMAN", "REQUEST_HUMAN", _REQUEST_HUMAN, escalation_reason="REQUEST_HUMAN"),
]
