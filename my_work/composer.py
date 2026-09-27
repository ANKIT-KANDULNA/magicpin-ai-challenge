"""
Vera AI Challenge — 4-Context Message Composer
================================================
Composes merchant-facing and customer-facing WhatsApp messages from:
1. CategoryContext
2. MerchantContext
3. TriggerContext
4. CustomerContext (optional)
"""

import os
import json
import time
import re
from typing import Optional, Dict, Any
from urllib import request as urlrequest, error as urlerror

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Gemini Configuration
DEFAULT_API_KEY = ""
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", DEFAULT_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


SYSTEM_PROMPT = """You are Vera, magicpin's Merchant AI Assistant for local businesses in India (or drafting on behalf of the merchant if sending to a customer).

Your mission is to compose high-impact, contextually precise WhatsApp outreach messages.

MANDATORY RULES:
1. SPECIFICITY (CRITICAL): Anchor on verifiable, concrete facts from the provided context (exact numbers, percentages, trial numbers, prices like 'Haircut @ ₹99', dates, official source citations like 'JIDA Oct 2026 p.14'). NEVER fabricate data, fake studies, fake competitor names, or fake discounts not present in the context.
2. CATEGORY FIT: 
   - Dentists: Clinical peer-to-peer tone. Use "Dr. <Name>". Technical terms are welcome. Taboos: NEVER claim "guaranteed" or "cure".
   - Salons: Friendly, trend-savvy, practical.
   - Restaurants: Operator-to-operator, busy, direct.
   - Gyms: Motivating, coaching.
   - Pharmacies: Reliable, health-focused, precise.
3. MERCHANT FIT: Personalize to this merchant (identity, city/locality, performance stats, active offers). If their language preference includes "hi", use natural Indian English with Hindi phrases (Hinglish).
4. TRIGGER RELEVANCE: Clearly state "WHY NOW" connecting directly to the trigger event (e.g. research released, performance spike, seasonal trend, recall due).
5. ENGAGEMENT COMPULSION & CTA:
   - Use levers: Curiosity, loss aversion, social proof, low-friction ask.
   - SINGLE primary call-to-action in the very last sentence (e.g., "Reply YES to publish", "Want me to draft it?").
   - Keep WhatsApp messages punchy (under 60-80 words). No corporate preamble ("I hope you are well").

OUTPUT FORMAT:
Respond with ONLY a valid JSON object matching this schema:
{
  "body": "<the WhatsApp message text>",
  "cta": "binary" | "open_ended" | "none",
  "rationale": "<1-2 sentences explaining why this message was composed this way>"
}
"""


def _call_gemini(prompt: str, retries: int = 5) -> str:
    """Calls Gemini API with exponential backoff for resilience."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [
            {"parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for attempt in range(retries):
        try:
            req = urlrequest.Request(url, data=data, headers=headers)
            with urlrequest.urlopen(req, timeout=30) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                return resp_json["candidates"][0]["content"]["parts"][0]["text"]
        except urlerror.HTTPError as e:
            if attempt < retries - 1:
                wait_sec = 8 * (attempt + 1) if e.code == 429 else (2 ** attempt)
                time.sleep(wait_sec)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

    raise RuntimeError("Gemini API call failed after retries")


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main composition function required by the challenge brief.
    Takes 4 contexts and returns: body, cta, send_as, suppression_key, rationale.
    """
    scope = trigger.get("scope", "merchant")
    send_as = "merchant_on_behalf" if (scope == "customer" and customer) else "vera"
    suppression_key = trigger.get("suppression_key", f"suppress_{trigger.get('id')}")

    # Build contextual prompt
    prompt = f"""COMPOSE WHATSAPP MESSAGE FOR THIS SCENARIO:

=== 1. CATEGORY CONTEXT ({category.get('slug', 'general')}) ===
Voice Profile: {json.dumps(category.get('voice', {}))}
Offer Catalog: {json.dumps(category.get('offer_catalog', []))}
Peer Benchmarks: {json.dumps(category.get('peer_stats', {}))}
Digest Items: {json.dumps(category.get('digest', [])[:3])}
Seasonal Beats: {json.dumps(category.get('seasonal_beats', []))}
Trend Signals: {json.dumps(category.get('trend_signals', []))}

=== 2. MERCHANT CONTEXT ===
ID: {merchant.get('merchant_id')}
Identity: {json.dumps(merchant.get('identity', {}))}
Performance (30d): {json.dumps(merchant.get('performance', {}))}
Active Offers: {json.dumps([o for o in merchant.get('offers', []) if o.get('status') == 'active'])}
Customer Base: {json.dumps(merchant.get('customer_aggregate', {}))}
Signals: {json.dumps(merchant.get('signals', []))}

=== 3. TRIGGER CONTEXT (WHY NOW) ===
Trigger ID: {trigger.get('id')}
Kind: {trigger.get('kind')}
Payload: {json.dumps(trigger.get('payload', {}))}
Urgency (1-5): {trigger.get('urgency', 2)}

=== 4. CUSTOMER CONTEXT ({'CUSTOMER-FACING' if customer else 'NONE - MERCHANT FACING'}) ===
{json.dumps(customer) if customer else 'Not applicable (message goes to merchant)'}
Send As: {send_as}
"""

    try:
        raw_output = _call_gemini(prompt)
        parsed = json.loads(raw_output)
        body = parsed.get("body", "").strip()
        cta = parsed.get("cta", "open_ended")
        rationale = parsed.get("rationale", f"Triggered by {trigger.get('kind')}")
    except Exception as e:
        # Fallback if LLM unavailable
        owner_name = merchant.get("identity", {}).get("owner_first_name") or merchant.get("identity", {}).get("name", "there")
        prefix = "Dr. " if category.get("slug") == "dentists" and not owner_name.startswith("Dr.") else ""
        body = f"Hi {prefix}{owner_name}, we noticed an update regarding {trigger.get('kind', 'your profile')}. Would you like to review it today?"
        cta = "binary"
        rationale = f"Fallback composition due to error: {str(e)}"

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": suppression_key,
        "rationale": rationale,
    }
