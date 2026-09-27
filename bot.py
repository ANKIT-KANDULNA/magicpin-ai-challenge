"""
magicpin AI Challenge — Vera 2.0 Merchant Assistant Bot
=======================================================
Canonical submission module exposing:
1. compose(category, merchant, trigger, customer) -> dict
2. FastAPI app with all 5 judge endpoints:
   - GET  /v1/healthz
   - GET  /v1/metadata
   - POST /v1/context
   - POST /v1/tick
   - POST /v1/reply
"""

import os
import uvicorn
from my_work.composer import compose
from my_work.bot import app

__all__ = ["app", "compose"]

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("bot:app", host="0.0.0.0", port=port)
