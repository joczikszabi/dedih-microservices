"""einvoice-mock: a stand-in for an external invoicing / tax system.

In real life this is another company's API. It runs here so that block 5 can
switch it off and watch what the shop does when a partner is down.
Keeps everything in memory. No database.
"""

import socket
from datetime import datetime, timezone
from itertools import count

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel

PREFIX = "/api/einvoice"
HOSTNAME = socket.gethostname()

app = FastAPI(title="einvoice-mock", docs_url=None, redoc_url=None,
              openapi_url=PREFIX + "/openapi.json")

received: list[dict] = []
numbers = count(1)


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    return response


@app.get("/docs", include_in_schema=False)
@app.get(PREFIX + "/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="einvoice-mock API")


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


class Submission(BaseModel):
    order_id: int
    amount_huf: int


@app.post(PREFIX + "/submit")
def submit(body: Submission):
    reference = f"EINV-TEST-{next(numbers):06d}"
    received.append({"reference": reference, "order_id": body.order_id,
                     "amount_huf": body.amount_huf,
                     "received_at": datetime.now(timezone.utc).isoformat()})
    return {"reference": reference}


@app.get(PREFIX + "/received")
def list_received():
    return received[-50:]
