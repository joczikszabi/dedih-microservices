"""catalog: products, prices and stock.

Public:   GET  /api/catalog/products, GET /api/catalog/products/{id}
Internal: POST /api/catalog/products/{id}/reserve  (called by orders at checkout)
"""

import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db import Product, engine, wait_and_init

PREFIX = "/api/catalog"
HOSTNAME = socket.gethostname()
# Changing this value is how block 3 rolls out a "new version" of catalog.
APP_VERSION = os.environ.get("APP_VERSION", "v1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_and_init()
    yield


app = FastAPI(title="catalog", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=PREFIX + "/openapi.json")


@app.middleware("http")
async def served_by(request: Request, call_next):
    # Every response says which instance answered. The shop shows it in the
    # status line, which is how scaling becomes visible in block 3.
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    response.headers["X-App-Version"] = APP_VERSION
    return response


# Swagger UI on /docs (direct port, stage A) and under the prefix (through Nginx).
@app.get("/docs", include_in_schema=False)
@app.get(PREFIX + "/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="catalog API")


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


def product_out(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price_huf": product.price_huf,
        "stock": product.stock,
        "limited": product.limited,
    }


@app.get(PREFIX + "/products")
def list_products():
    with Session(engine) as session:
        products = session.scalars(select(Product).order_by(Product.id)).all()
        return [product_out(p) for p in products]


@app.get(PREFIX + "/products/{product_id}")
def get_product(product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found")
        return product_out(product)


class Reservation(BaseModel):
    quantity: int = 1


@app.post(PREFIX + "/products/{product_id}/reserve")
def reserve(product_id: int, body: Reservation):
    """Take items out of stock. Returns the real price, which orders should use."""
    if body.quantity < 1:
        raise HTTPException(400, "Quantity must be at least 1")
    with Session(engine) as session:
        # One UPDATE with a WHERE on the stock, so two parallel checkouts can
        # never both take the last item.
        row = session.execute(
            update(Product)
            .where(Product.id == product_id, Product.stock >= body.quantity)
            .values(stock=Product.stock - body.quantity)
            .returning(Product.price_huf, Product.stock, Product.name)
        ).first()
        session.commit()
    if row is None:
        raise HTTPException(409, "Out of stock")
    return {"product_id": product_id, "name": row.name,
            "unit_price": row.price_huf, "remaining": row.stock}
