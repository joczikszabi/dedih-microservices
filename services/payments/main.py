"""payments: simulated charges and refunds, and a ledger page.

Internal only: the gateway never routes here. Only orders is supposed to call it.

VULNERABLE (lateral movement): payments trusts any caller that can reach it
over the network. There is no fix in this code on purpose. Block 4 stops it
with Istio: mTLS proves who is calling, an AuthorizationPolicy decides who may.
"""

import html
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import LedgerEntry, engine, wait_and_init

PREFIX = "/api/payments"
HOSTNAME = socket.gethostname()


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_and_init()
    yield


app = FastAPI(title="payments", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=PREFIX + "/openapi.json")


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    return response


@app.get("/docs", include_in_schema=False)
@app.get(PREFIX + "/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="payments API")


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


def caller_identity(request: Request) -> str:
    """Who is calling, according to the service mesh.

    Inside the mesh, the Envoy sidecar in front of this service checks the
    caller's certificate (mTLS) and passes what it found in the
    x-forwarded-client-cert header, for example:

        By=spiffe://cluster.local/ns/shop/sa/payments;Hash=...;URI=spiffe://cluster.local/ns/shop/sa/orders

    The URI part is the caller's SPIFFE ID: namespace plus ServiceAccount.
    Without a mesh there is no such header, and nobody can tell who called.
    """
    header = request.headers.get("x-forwarded-client-cert")
    if not header:
        return "unknown (no mTLS)"
    last_hop = header.split(",")[-1]
    for part in last_hop.split(";"):
        if part.startswith("URI="):
            return part[len("URI="):]
    return "unknown (no mTLS)"


class Payment(BaseModel):
    order_id: int
    amount_huf: int


def record(kind: str, body: Payment, request: Request) -> dict:
    with Session(engine) as session:
        entry = LedgerEntry(kind=kind, order_id=body.order_id, amount_huf=body.amount_huf,
                            requested_by=caller_identity(request))
        session.add(entry)
        session.commit()
        return entry_out(entry)


def entry_out(entry: LedgerEntry) -> dict:
    return {"id": entry.id, "kind": entry.kind, "order_id": entry.order_id,
            "amount_huf": entry.amount_huf, "requested_by": entry.requested_by,
            "created_at": entry.created_at.isoformat() if entry.created_at else None}


@app.post(PREFIX + "/charges")
def charge(body: Payment, request: Request):
    return record("charge", body, request)


@app.post(PREFIX + "/refunds")
def refund(body: Payment, request: Request):
    # No check of who is asking. See the module docstring.
    return record("refund", body, request)


@app.get(PREFIX + "/entries")
def entries(limit: int = 20):
    with Session(engine) as session:
        rows = session.scalars(select(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(limit)).all()
        return [entry_out(e) for e in rows]


@app.get(PREFIX + "/ledger", response_class=HTMLResponse)
def ledger():
    """The same data as /entries, as a page for the browser."""
    rows = entries(limit=50)
    lines = "".join(
        f"<tr class='{r['kind']}'><td>{r['id']}</td><td>{html.escape(str(r['created_at']))}</td>"
        f"<td>{r['kind']}</td><td>{r['order_id']}</td><td>{r['amount_huf']:,} HUF</td>"
        f"<td><code>{html.escape(r['requested_by'])}</code></td></tr>"
        for r in rows
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Payments ledger</title>
<meta http-equiv="refresh" content="5">
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
table {{ border-collapse: collapse; }}
td, th {{ border-bottom: 1px solid #ddd; padding: .4rem .8rem; text-align: left; }}
tr.refund td {{ background: #fff1f0; }}
code {{ font-size: .95em; }}
</style></head><body>
<h1>Payments ledger</h1>
<p>Simulated. Newest first, refreshes every 5 seconds. Served by {HOSTNAME}.</p>
<table><tr><th>#</th><th>Time (UTC)</th><th>Kind</th><th>Order</th><th>Amount</th><th>Requested by</th></tr>
{lines}</table></body></html>"""
