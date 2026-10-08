# DEDIH Microservices

Teaching repository for the **Mikroszolgáltatás architektúra** course,
ELTE IK, DEDIH 2.0.

A small fictional webshop, the Retro Game Shop, split into five services. In
the morning every service is wide open. During the day it gets an API
gateway, moves to Kubernetes, gets a service mesh with workload identity, and
finally monitoring that shows a bot attack as a spike.

Participants follow **[docs/LAB.md](docs/LAB.md)**, which is in Hungarian.

## What the day looks like

| Attack | Stage A: Compose | Stage B: + Nginx gateway | Code fix (commented out) | Stage E: + Istio |
| --- | --- | --- | --- | --- |
| Read another customer's order (API1, BOLA) | works | works | refused | |
| Order with `unit_price: 0` (API3) | works | works | refused | |
| Refund as a customer (API5) | works | 403 at the gateway | | |
| Bot buys all 20 consoles (API4/API6) | works | 429 after 3 | 1 per customer | |
| Old `/api/orders/v1/` endpoint (API9) | works | 404 at the gateway | delete it | |
| Compromised catalog pod refunds via payments | works | works | | `RBAC: access denied` |

No single layer fixes everything. The gateway cannot fix business logic, and
the code fixes cannot stop a compromised pod inside the network.

## The application

| Service | Tech | Owns | Reachable from outside |
| --- | --- | --- | --- |
| `web` | Astro static build, nginx-unprivileged | nothing | yes |
| `catalog` | FastAPI | `catalog` db: products, stock | yes, read only |
| `orders` | FastAPI | `orders` db: customers, orders | yes |
| `payments` | FastAPI | `payments` db: ledger | no |
| `invoicing` | FastAPI | `invoicing` db: invoices | no |
| `einvoice-mock` | FastAPI | memory | no, stands in for an external system |
| `postgres` | `postgres:17-alpine` | one database and user per service | no |
| `nginx` | `nginx:1.30-alpine` | | the only door, on 8080 |

Each service is one `main.py` (routes) and one `db.py` (tables and seed
data, SQLAlchemy). The small pieces they share, like the `X-Served-By` header
and the Swagger UI routes, are copied rather than put in a shared library:
each service can be built and deployed on its own, which is the point.

Every service answers `/health`, serves Swagger UI at `/docs` and under its
prefix (`/api/catalog/docs`), and sets `X-Served-By: <hostname>`.

The deliberate weaknesses are all in `services/orders/main.py`, each marked
`# VULNERABLE (...)` with the fix commented out right under it. The sixth,
`payments` trusting any caller, has no code fix on purpose.

Test accounts: `alice@example.com` / `alice123`, `bob@example.com` / `bob123`,
`admin@example.com` / `admin123`. All data is made up.

## Stages

| Stage | Block | Command |
| --- | --- | --- |
| A | 1 | `docker compose up -d --build` |
| B | 2 | `docker compose down` then `docker compose -f compose.nginx.yaml up -d --build` |
| C (optional demo) | 2 | uncomment a fix in `services/orders/main.py`, then `docker compose -f compose.nginx.yaml up -d --build orders` |
| D | 3 | `docker compose down` then `scripts/cluster-up.sh` |
| E | 4, 5 | `scripts/mesh-up.sh`, then the files in `mesh/` one by one |

## Layout

```
.devcontainer/     Codespace definition: Docker in Docker, kubectl, kind, istioctl, jq
services/          catalog, orders, payments, invoicing, einvoice-mock (FastAPI)
web/               the shop UI, Astro, multi-stage Dockerfile
nginx/             proxy.conf (stage A, routing only), gateway.conf (stage B onwards)
db/init.sql        one database and one user per service
compose.yaml       stage A, every service on its own port too
compose.nginx.yaml stage B, only Nginx on 8080
kind/              one node, host port 8080 mapped to the Nginx NodePort
k8s/               namespace shop, one Deployment, Service and ServiceAccount per service
mesh/              Istio install, 01-strict-mtls.yaml, 02-payments-policy.yaml,
                   addons/ (Prometheus, Grafana, Kiali from Istio 1.31.1) and monitoring/
scripts/           cluster-up, mesh-up, attacks, bot, traffic, dashboards, reset-demo
docs/LAB.md        the participant guide, Hungarian
```

## Measured on a Mac (Docker Desktop, 10 cores, 24 GB), 2026-10-08

| | |
| --- | --- |
| `scripts/cluster-up.sh`, node image cached | 72 s |
| `scripts/mesh-up.sh`, images not cached | 273 s |
| kind node memory, shop only | 1.5 GB |
| kind node memory, shop + Istio + Prometheus, Grafana, Kiali, all sidecars | 3.1 GB |
| Sum of CPU requests in the cluster, mesh included | 1410m |
| Alert `ShopRequestFlood`: bot start to firing | about 60 s |
| Rolling update of catalog, 3 replicas, requests during it | 80 of 80 answered 200 |

A 4 core / 16 GB Codespace has room for this. It has not yet been measured in
a Codespace itself.

## Notes for whoever teaches this next

- `kubectl port-forward` does not load balance, it pins one pod. The shop
  is reached through a NodePort (`kind/kind-config.yaml`), so scaling
  `catalog` really shows three names. `scripts/dashboards.sh` uses
  port-forward only for Grafana, Kiali, Prometheus and the two internal pages.
- Nginx must not override the `Host` header towards the services. With the
  browser's host name the Istio sidecar does not recognise the destination,
  sends the request out as plain TCP, and STRICT mTLS rejects it (the shop
  answered 503 in testing until this was fixed).
- Nginx itself stays PERMISSIVE under STRICT mTLS (`mesh/01-strict-mtls.yaml`):
  browsers have no mesh certificate. In a cluster with an Istio ingress
  gateway, the gateway plays this role.
- Postgres is a StatefulSet outside the mesh, so that
  `kubectl rollout restart deployment -n shop` in block 4 does not wipe the
  data.
- An AuthorizationPolicy took between 2 and about 15 seconds to take effect in
  testing. If the attack still succeeds right after `kubectl apply`, wait and
  run it again.
- Nginx resolves service names once, at start. If a rebuilt Compose service
  ever gives 502, `docker compose restart nginx`.
- The rate limit is per token, not per IP: in a Codespace every request comes
  from the same address.
- Every container image, Python package and tool version was checked to exist
  on 2026-10-08.

## Licence

MIT.
