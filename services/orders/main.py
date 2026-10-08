"""orders: customers, login, checkout, order history, refunds.

This service contains five deliberate weaknesses. Each one is marked
`# VULNERABLE (...)`, with a `# FIX: ...` line right under it. For four of
them the fixed code is already there, commented out: remove the `#` in front
of those lines, then rebuild orders. The fifth (API9) is fixed by deleting
the endpoint.
"""

import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Customer, Order, OrderItem, engine, hash_password, wait_and_init

PREFIX = "/api/orders"
HOSTNAME = socket.gethostname()
JWT_SECRET = os.environ["JWT_SECRET"]
CATALOG_URL = os.environ.get("CATALOG_URL", "http://catalog:8000")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://payments:8000")
INVOICING_URL = os.environ.get("INVOICING_URL", "http://invoicing:8000")

# The handheld console with 20 units. Used by the API4 and API6 fix below.
LIMITED_PRODUCT_ID = 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_and_init()
    yield


app = FastAPI(title="orders", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=PREFIX + "/openapi.json")


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    return response


@app.get("/docs", include_in_schema=False)
@app.get(PREFIX + "/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="orders API")


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


# ---------------------------------------------------------------------------
# Login and tokens
# ---------------------------------------------------------------------------

bearer = HTTPBearer(auto_error=False)


def make_token(customer: Customer) -> str:
    claims = {
        "sub": str(customer.id),
        "email": customer.email,
        "role": customer.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def current_customer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Customer:
    """Read the bearer token, check the signature, load the customer."""
    if credentials is None:
        raise HTTPException(401, "Missing token")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    with Session(engine) as session:
        customer = session.get(Customer, int(claims["sub"]))
    if customer is None:
        raise HTTPException(401, "Unknown customer")
    return customer


class Login(BaseModel):
    email: str
    password: str


class Register(BaseModel):
    email: str
    password: str
    name: str
    address: str


@app.post(PREFIX + "/auth/register")
def register(body: Register):
    with Session(engine) as session:
        if session.scalar(select(Customer).where(Customer.email == body.email)):
            raise HTTPException(409, "E-mail already registered")
        customer = Customer(email=body.email, password_hash=hash_password(body.password),
                            name=body.name, address=body.address, role="customer")
        session.add(customer)
        session.commit()
        return {"id": customer.id, "email": customer.email}


@app.post(PREFIX + "/auth/login")
def login(body: Login):
    with Session(engine) as session:
        customer = session.scalar(select(Customer).where(Customer.email == body.email))
    if customer is None or customer.password_hash != hash_password(body.password):
        raise HTTPException(401, "Wrong e-mail or password")
    return {"access_token": make_token(customer), "token_type": "bearer",
            "role": customer.role, "name": customer.name}


# The two endpoints below are what the Nginx gateway asks on every request
# (auth_request in nginx/gateway.conf). Open source Nginx cannot validate a
# JWT itself, so it asks the service that issued it.
@app.get(PREFIX + "/auth/verify")
def verify(response: Response, customer: Customer = Depends(current_customer)):
    response.headers["X-User-Id"] = str(customer.id)
    response.headers["X-User-Role"] = customer.role
    return {"ok": True}


@app.get(PREFIX + "/auth/verify-admin")
def verify_admin(response: Response, customer: Customer = Depends(current_customer)):
    if customer.role != "admin":
        raise HTTPException(403, "Admins only")
    response.headers["X-User-Id"] = str(customer.id)
    response.headers["X-User-Role"] = customer.role
    return {"ok": True}


@app.get(PREFIX + "/me")
def me(customer: Customer = Depends(current_customer)):
    return {"id": customer.id, "email": customer.email, "name": customer.name,
            "address": customer.address, "role": customer.role}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def order_out(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_huf": order.total_huf,
        "delivery_name": order.delivery_name,
        "delivery_address": order.delivery_address,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [{"product_id": i.product_id, "name": i.product_name,
                   "quantity": i.quantity, "unit_price_huf": i.unit_price_huf} for i in order.items],
    }


@app.get(PREFIX + "/")
def my_orders(customer: Customer = Depends(current_customer)):
    with Session(engine) as session:
        orders = session.scalars(select(Order).where(Order.customer_id == customer.id)
                                 .order_by(Order.id.desc())).all()
        return [order_out(o) for o in orders]


# VULNERABLE (API9 improper inventory management): the old v1 endpoint is
# still deployed, has no authentication and lists anyone's orders.
# FIX: delete this whole function. There is nothing to uncomment here.
@app.get(PREFIX + "/v1/orders")
def v1_list_orders(customer_id: int):
    with Session(engine) as session:
        orders = session.scalars(select(Order).where(Order.customer_id == customer_id)).all()
        return [order_out(o) for o in orders]


@app.get(PREFIX + "/{order_id}")
def get_order(order_id: int, customer: Customer = Depends(current_customer)):
    with Session(engine) as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(404, "Order not found")
        # VULNERABLE (API1 BOLA): any logged-in customer can read any order,
        # including the other customer's name and delivery address.
        # FIX: only the owner may see it. Uncomment the two lines below.
        # if order.customer_id != customer.id:
        #     raise HTTPException(404, "Order not found")
        return order_out(order)


class CartItem(BaseModel):
    product_id: int
    quantity: int = 1
    unit_price: int  # sent by the browser, see weakness 2


class Checkout(BaseModel):
    items: list[CartItem]


def create_invoice(order_id: int, email: str, amount: int) -> None:
    """Runs after the response is sent. If it fails, the order is still valid."""
    try:
        httpx.post(f"{INVOICING_URL}/api/invoicing/invoices",
                   json={"order_id": order_id, "customer_email": email, "amount_huf": amount},
                   timeout=3)
    except httpx.HTTPError as error:
        print(f"invoice for order {order_id} not created: {error}", flush=True)


@app.post(PREFIX + "/")
def checkout(body: Checkout, background: BackgroundTasks,
             customer: Customer = Depends(current_customer)):
    if not body.items:
        raise HTTPException(400, "Cart is empty")

    # VULNERABLE (API4 and API6 unrestricted business flow): nothing limits
    # how many limited consoles one customer buys, so a bot can buy all 20.
    # FIX: one limited console per customer. Uncomment the six lines below.
    # with Session(engine) as session:
    #     already = session.scalar(select(OrderItem).join(Order).where(
    #         Order.customer_id == customer.id, OrderItem.product_id == LIMITED_PRODUCT_ID))
    # for item in body.items:
    #     if item.product_id == LIMITED_PRODUCT_ID and (item.quantity > 1 or already):
    #         raise HTTPException(409, "Limit: one per customer")

    # 1. Reserve stock in catalog. Catalog answers with the real price.
    lines = []
    for item in body.items:
        reply = httpx.post(f"{CATALOG_URL}/api/catalog/products/{item.product_id}/reserve",
                           json={"quantity": item.quantity}, timeout=5)
        if reply.status_code == 409:
            raise HTTPException(409, "Out of stock")
        reply.raise_for_status()
        reserved = reply.json()

        # VULNERABLE (API3 broken object property level authorization): the
        # price comes from the request body, so the client can send 0.
        unit_price = item.unit_price
        # FIX: use the price catalog just returned. Uncomment the line below.
        # unit_price = reserved["unit_price"]

        lines.append(OrderItem(product_id=item.product_id, product_name=reserved["name"],
                               quantity=item.quantity, unit_price_huf=unit_price))

    total = sum(line.quantity * line.unit_price_huf for line in lines)

    # 2. Save the order, then charge it through payments.
    with Session(engine) as session:
        order = Order(customer_id=customer.id, status="pending", total_huf=total,
                      delivery_name=customer.name, delivery_address=customer.address, items=lines)
        session.add(order)
        session.commit()
        try:
            charge = httpx.post(f"{PAYMENTS_URL}/api/payments/charges",
                                json={"order_id": order.id, "amount_huf": total}, timeout=5)
            charge.raise_for_status()
            order.status = "paid"
        except httpx.HTTPError:
            order.status = "payment_failed"
        session.commit()
        result = order_out(order)

    if result["status"] != "paid":
        raise HTTPException(502, "Payment failed")

    # 3. The invoice is created in the background. If invoicing or the
    # external system is down, the customer still gets the order.
    background.add_task(create_invoice, result["id"], customer.email, total)
    return result


@app.post(PREFIX + "/admin/refund/{order_id}")
def admin_refund(order_id: int, customer: Customer = Depends(current_customer)):
    # VULNERABLE (API5 broken function level authorization): this is an admin
    # function, but any logged-in customer can call it.
    # FIX: admins only. Uncomment the two lines below.
    # if customer.role != "admin":
    #     raise HTTPException(403, "Admins only")
    with Session(engine) as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(404, "Order not found")
        if order.status == "refunded":
            raise HTTPException(409, "Already refunded")
        reply = httpx.post(f"{PAYMENTS_URL}/api/payments/refunds",
                           json={"order_id": order.id, "amount_huf": order.total_huf}, timeout=5)
        reply.raise_for_status()
        order.status = "refunded"
        session.commit()
        return order_out(order)
