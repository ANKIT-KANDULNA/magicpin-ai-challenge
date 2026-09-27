"""
Vera AI Challenge — Multi-Turn Conversation Handler
===================================================
Handles follow-up turns from merchants or customers, including:
1. WhatsApp Business canned auto-reply detection
2. Hostile / unsubscribe / spam graceful exit
3. Explicit intent-to-action transition
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    turns: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)


def respond(state: ConversationState, merchant_message: str) -> dict:
    """
    Given the conversation so far + the merchant's latest message,
    produces the next action: 'send', 'wait', or 'end'.
    """
    msg_clean = merchant_message.strip()
    msg_lower = msg_clean.lower()

    # Record turn into state
    state.turns.append({"from": "merchant", "message": msg_clean})

    # 1. Hostile / Opt-out Detection
    hostile_triggers = [
        "stop", "spam", "unsubscribe", "don't message", "dont message",
        "not interested", "useless", "annoying", "leave me alone", "remove me"
    ]
    if any(h in msg_lower for h in hostile_triggers):
        return {
            "action": "end",
            "body": "I sincerely apologize for the inconvenience. I will stop messaging you and update your preferences.",
            "cta": "none",
            "rationale": "Merchant opted out / signaled hostility; gracefully exiting conversation."
        }

    # 2. Canned Auto-Reply Detection
    auto_reply_markers = [
        "thank you for contacting",
        "our team will respond shortly",
        "automated assistant",
        "automated response",
        "we are currently unavailable",
        "busy right now"
    ]
    is_canned = any(marker in msg_lower for marker in auto_reply_markers)
    repeated_count = sum(1 for t in state.turns if t.get("message", "").strip().lower() == msg_lower)

    if is_canned or repeated_count >= 2:
        return {
            "action": "end",
            "rationale": "Detected canned WhatsApp Business auto-reply; ending conversation to avoid polluting turns."
        }

    # 3. Intent Transition (Commitment to Action)
    intent_action_triggers = [
        "lets do it", "let's do it", "whats next", "what's next",
        "go ahead", "yes please", "proceed", "i want to join",
        "update my profile", "sure do it", "confirm"
    ]
    if any(trigger in msg_lower for trigger in intent_action_triggers):
        return {
            "action": "send",
            "body": "Great! Proceeding right now. Here is your draft ready to go. Please confirm to publish immediately.",
            "cta": "binary",
            "rationale": "Merchant expressed explicit commitment; switched immediately to action mode with next-step draft."
        }

    # 4. Standard Contextual Follow-up
    return {
        "action": "send",
        "body": "Got it! Here is the next step to update and boost your Google Business Profile.",
        "cta": "open_ended",
        "rationale": "Acknowledged merchant input and progressed conversation towards value."
    }
