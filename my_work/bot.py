import time
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from my_work.composer import compose

app = FastAPI(title="magicpin Vera AI Bot")
START_TIME = time.time()

# ---------------------------------------------------------
# State Storage: In-memory store for contexts & dialogues
# ---------------------------------------------------------
# contexts key: (scope, context_id) -> {"version": int, "payload": dict}
contexts: dict[tuple[str, str], dict] = {}

# conversations key: conversation_id -> list of turn dicts
conversations: dict[str, list[dict]] = {}


# ---------------------------------------------------------
# Pydantic Schemas for Judge Requests
# ---------------------------------------------------------
class ContextPayload(BaseModel):
    scope: str  # "category" | "merchant" | "customer" | "trigger"
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = []


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str  # "merchant" or "customer"
    message: str
    received_at: str
    turn_number: int


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "magicpin Vera AI Bot",
        "endpoints": ["/v1/healthz", "/v1/metadata", "/v1/context", "/v1/tick", "/v1/reply"],
    }


@app.get("/v1/healthz")
async def healthz():
    """Liveness probe. Reports count of loaded contexts per scope."""
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts,
    }


@app.get("/v1/metadata")
async def metadata():
    """Identifies your bot to the judge harness."""
    return {
        "team_name": "Team Vera",
        "team_members": ["Ankit Kandulna"],
        "model": "gemini-3.8-flash",
        "approach": "4-context LLM composer with verifiable citations, tone matching, and intent switching",
        "contact_email": "ankitkandulna_23cs060@dtu.ac.in",
        "version": "1.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/context")
async def push_context(data: ContextPayload):
    """
    Receives category, merchant, customer, or trigger data.
    Must be idempotent and handle versions properly.
    """
    key = (data.scope, data.context_id)
    current = contexts.get(key)
    if current and current["version"] > data.version:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current["version"],
            },
        )
    if current and current["version"] == data.version:
        return {
            "accepted": True,
            "ack_id": f"ack_{data.context_id}_v{data.version}",
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

    contexts[key] = {"version": data.version, "payload": data.payload}
    return {
        "accepted": True,
        "ack_id": f"ack_{data.context_id}_v{data.version}",
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


import concurrent.futures

@app.post("/v1/tick")
async def tick(data: TickRequest):
    """
    Periodic tick from judge. Bot inspects active triggers and context,
    then composes proactive messages concurrently within the time budget.
    """
    to_compose = []

    for trg_id in data.available_triggers[:5]:  # process up to 5 triggers concurrently
        trg_ctx = contexts.get(("trigger", trg_id), {}).get("payload")
        if not trg_ctx:
            continue

        merchant_id = trg_ctx.get("merchant_id")
        merchant = contexts.get(("merchant", merchant_id), {}).get("payload")
        if not merchant:
            continue

        category_slug = merchant.get("category_slug")
        category = contexts.get(("category", category_slug), {}).get("payload")
        if not category:
            continue

        customer_id = trg_ctx.get("customer_id")
        customer = contexts.get(("customer", customer_id), {}).get("payload") if customer_id else None

        to_compose.append((category, merchant, trg_ctx, customer, trg_id, merchant_id, customer_id))

    if not to_compose:
        return {"actions": []}

    actions = []
    # Run all compositions in parallel to stay well under the 15-30s timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(to_compose)) as executor:
        future_map = {
            executor.submit(compose, cat, merch, trg, cust): (trg_id, merch_id, cust_id, trg, merch)
            for (cat, merch, trg, cust, trg_id, merch_id, cust_id) in to_compose
        }
        for future in concurrent.futures.as_completed(future_map):
            trg_id, merch_id, cust_id, trg, merch = future_map[future]
            try:
                composed = future.result()
            except Exception as e:
                composed = {
                    "body": f"Hi {merch.get('identity', {}).get('name', 'there')}, we have an update regarding {trg.get('kind', 'your account')}.",
                    "cta": "open_ended",
                    "send_as": "vera",
                    "suppression_key": f"suppress_{trg_id}",
                    "rationale": f"Emergency fallback: {e}",
                }

            actions.append({
                "conversation_id": f"conv_{merch_id}_{trg_id}",
                "merchant_id": merch_id,
                "customer_id": cust_id,
                "send_as": composed.get("send_as", "vera"),
                "trigger_id": trg_id,
                "template_name": "vera_outbound_v1",
                "template_params": [merch.get("identity", {}).get("name", "")],
                "body": composed.get("body", ""),
                "cta": composed.get("cta", "open_ended"),
                "suppression_key": composed.get("suppression_key", trg.get("suppression_key", f"suppress_{trg_id}")),
                "rationale": composed.get("rationale", ""),
            })

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(data: ReplyRequest):
    """
    Called when a merchant or customer replies to Vera.
    Returns: action ('send', 'wait', 'end'), body, cta, rationale.
    """
    # Record turn history
    history = conversations.setdefault(data.conversation_id, [])
    history.append({
        "from": data.from_role,
        "message": data.message,
        "turn": data.turn_number,
    })

    msg_lower = data.message.lower().strip()

    # 1. Hostile / Opt-out Detection
    hostile_triggers = ["stop", "spam", "unsubscribe", "don't message", "dont message", 
                        "not interested", "useless", "annoying", "leave me alone", "remove me"]
    if any(h in msg_lower for h in hostile_triggers):
        return {
            "action": "end",
            "body": "I sincerely apologize for the inconvenience. I won't message you again.",
            "cta": "none",
            "rationale": "Merchant opted out / signaled hostility; gracefully exiting conversation.",
        }

    # 2. Canned Auto-Reply Detection
    auto_reply_markers = [
        "thank you for contacting",
        "our team will respond shortly",
        "automated assistant",
        "automated response",
        "we are currently unavailable",
        "busy right now",
    ]
    is_canned = any(marker in msg_lower for marker in auto_reply_markers)
    repeated_count = sum(1 for t in history if t.get("message", "").strip().lower() == msg_lower)

    if is_canned or repeated_count >= 2:
        return {
            "action": "end",
            "rationale": "Detected canned WhatsApp Business auto-reply; ending conversation to avoid polluting turns.",
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
            "rationale": "Merchant expressed explicit commitment; switched immediately to action mode with next-step draft.",
        }

    # 4. Default Helpful Follow-up
    return {
        "action": "send",
        "body": "Got it! Here is the next step to update and boost your Google Business Profile.",
        "cta": "open_ended",
        "rationale": "Acknowledged merchant input and progressed conversation towards value.",
    }
