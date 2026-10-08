"""invoicing: creates invoices and sends them to the external invoicing system.

Internal only. The external system (einvoice-mock here) is someone else's
service: it can be slow or down. So an invoice is saved as "pending" first,
and a background loop retries pending invoices every 10 seconds.
"""

import os
import socket
import threading
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Invoice, engine, wait_and_init

PREFIX = "/api/invoicing"
HOSTNAME = socket.gethostname()
EINVOICE_URL = os.environ.get("EINVOICE_URL", "http://einvoice-mock:8000")
RETRY_SECONDS = 10


def send(invoice_id: int) -> None:
    """Try to hand one invoice to the external system."""
    with Session(engine) as session:
        invoice = session.get(Invoice, invoice_id)
        if invoice is None or invoice.status == "sent":
            return
        invoice.attempts += 1
        try:
            reply = httpx.post(f"{EINVOICE_URL}/api/einvoice/submit",
                               json={"order_id": invoice.order_id, "amount_huf": invoice.amount_huf},
                               timeout=3)
            reply.raise_for_status()
            invoice.status = "sent"
            invoice.reference = reply.json()["reference"]
        except (httpx.HTTPError, KeyError) as error:
            print(f"invoice {invoice.id} still pending: {error}", flush=True)
        session.commit()


def retry_loop() -> None:
    while True:
        time.sleep(RETRY_SECONDS)
        try:
            with Session(engine) as session:
                pending = session.scalars(select(Invoice.id).where(Invoice.status == "pending")).all()
            for invoice_id in pending:
                send(invoice_id)
        except Exception as error:  # keep the loop alive whatever happens
            print(f"retry loop: {error}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_and_init()
    threading.Thread(target=retry_loop, daemon=True).start()
    yield


app = FastAPI(title="invoicing", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=PREFIX + "/openapi.json")


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    return response


@app.get("/docs", include_in_schema=False)
@app.get(PREFIX + "/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="invoicing API")


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


class NewInvoice(BaseModel):
    order_id: int
    customer_email: str
    amount_huf: int


@app.post(PREFIX + "/invoices")
def create_invoice(body: NewInvoice):
    with Session(engine) as session:
        invoice = Invoice(order_id=body.order_id, customer_email=body.customer_email,
                          amount_huf=body.amount_huf, status="pending", attempts=0)
        session.add(invoice)
        session.commit()
        invoice_id = invoice.id
    send(invoice_id)
    return get_invoice(invoice_id)


def get_invoice(invoice_id: int) -> dict:
    with Session(engine) as session:
        i = session.get(Invoice, invoice_id)
        return {"id": i.id, "order_id": i.order_id, "customer_email": i.customer_email,
                "amount_huf": i.amount_huf, "status": i.status, "reference": i.reference,
                "attempts": i.attempts}


@app.get(PREFIX + "/invoices")
def list_invoices():
    with Session(engine) as session:
        ids = session.scalars(select(Invoice.id).order_by(Invoice.id.desc()).limit(50)).all()
    return [get_invoice(i) for i in ids]
