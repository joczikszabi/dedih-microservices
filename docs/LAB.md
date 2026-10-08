# Mikroszolgáltatás architektúra, gyakorlati útmutató

ELTE IK, DEDIH 2.0. Ebben a dokumentumban benne van minden lépés, amit ma
végigcsinálunk. Ha lemaradsz, ebből egyedül is tudsz haladni tovább.

---

## Mit csinálunk ma

| Blokk | Téma | Min fut |
| --- | --- | --- |
| 1 | Mikroszolgáltatások: mit, mikor, mikor ne | Docker Compose |
| 2 | API biztonság és Nginx | Docker Compose, gateway-jel |
| 3 | Mikroszolgáltatások Kubernetesen | kind |
| 4 | Zero trust a clusteren belül: Istio, mTLS, workload identity | kind + Istio |
| 5 | Monitoring | kind + Prometheus, Grafana, Kiali |

Az alkalmazás egy kitalált webshop, a **Retro Game Shop**. Retro játékokat és
konzolokat árul. Van egy limitált termék: egy újra kiadott kézi konzol,
összesen **20 darab**.

A shop öt service-ből áll:

| Service | Mit csinál |
| --- | --- |
| `web` | a weboldal, amit a böngészőben látsz |
| `catalog` | termékek, árak, készlet |
| `orders` | vásárlók, belépés, rendelés, visszatérítés |
| `payments` | fizetés és visszatérítés (szimulált), belső service |
| `invoicing` | számlák, belső service |

Mellettük fut egy `einvoice-mock`, ami egy külső számlázó rendszert játszik el,
egy Postgres adatbázis, és elöl egy Nginx.

Ide jutunk el a nap végére:

| Támadás | Reggel | + Nginx gateway | + Istio |
| --- | --- | --- | --- |
| Más vásárló rendelésének olvasása (BOLA) | átmegy | átmegy | |
| Rendelés 0 forintért | átmegy | átmegy | |
| Visszatérítés sima vásárlóként | átmegy | **403** | |
| Bot megveszi mind a 20 konzolt | átmegy | **429** | |
| Régi `/v1` végpont | átmegy | **404** | |
| Feltört `catalog` pod visszatérítést kér a `payments`-től | átmegy | átmegy | **RBAC: access denied** |

Egyik réteg sem old meg mindent egyedül.

---

## Fontos tudnivalók

**Ma nem kell kódot írnod és fájlt szerkesztened.** Minden lépés egy kész fájl
vagy egy parancs, amit innen másolsz.

**Teszt fiókok** (minden adat kitalált):

| E-mail | Jelszó | Szerep |
| --- | --- | --- |
| `alice@example.com` | `alice123` | vásárló |
| `bob@example.com` | `bob123` | vásárló |
| `admin@example.com` | `admin123` | admin |

**Ha valami elromlott, és tiszta lapot szeretnél**, ez visszaállítja a
termékeket, a készletet és a rendeléseket. Compose-on és Kubernetesen is működik:

```bash
scripts/reset-demo.sh
```

**A nap végén töröld a Codespace-t.** Lásd a Takarítás részt.

---

## 0. Előkészületek

1. Nyisd meg: `https://github.com/joczikszabi/dedih-microservices`
2. Jobb felül **Fork**, majd **Create fork**.
3. A **saját** forkodon: zöld **Code** gomb, **Codespaces** fül, a `...` menü,
   **New with options**. A **Machine type** legyen **4-core**, majd
   **Create codespace**.
4. Az első indítás öt-hat perc.

> A 4 mag és 16 GB memória kell a délutáni Istio és monitoring miatt. A repó
> ezt kéri is, de ha a gép kisebb lett, töröld és hozd létre újra 4-core
> beállítással.

Ha kész, ellenőrizd a terminálban:

```bash
docker --version
docker compose version
kubectl version --client
kind --version
istioctl version --remote=false
```

> Ha valamelyiket nem találja, akkor a container létrehozásakor futó szkript
> hibára futott. A javítás: `F1` billentyű, majd
> **Codespaces: Rebuild Container**. A `postCreateCommand` ugyanis csak a
> container létrehozásakor fut le, újraindításkor nem.

---

## 1. Blokk: a shop öt service-ként

### 1.1 Indítsd el

```bash
cd /workspaces/dedih-microservices
docker compose up -d --build
```

Az első indítás két-három perc, mert minden image-et meg kell építeni.

```bash
docker compose ps
```

Kilenc konténert látsz: öt service, a `web`, az `einvoice-mock`, a `postgres`
és az `nginx`.

### 1.2 Használd a shopot

A Codespace alján nyisd meg a **PORTS** fület, és a **Shop (8080)** sorban
kattints a földgömb ikonra.

1. Nézd meg a termékeket. Az oldal alján egy szürke sor van:
   `catalog served by ...`. Ez mutatja, melyik `catalog` példány válaszolt.
   Most csak egy van. A 3. blokkban ez megváltozik.
2. **Log in**, a mezők már ki vannak töltve Alice adataival.
3. Tegyél valamit a kosárba, és rendeld meg.
4. **My orders**: ott a rendelésed.

### 1.3 Minden service-nek saját ajtaja van

A shop a 8080-as porton fut. De nézd meg a többi portot is a **PORTS** fülön:

| Port | Service |
| --- | --- |
| 8001 | catalog |
| 8002 | orders |
| 8003 | payments |
| 8004 | invoicing |

Nyisd meg mindegyiket, és írd a cím végére: `/docs`. Mindegyiknél egy Swagger
UI jön fel, a service teljes API-jával. A `payments` és az `invoicing` belső
service, a böngészőnek nem kellene elérnie őket. Mégis elérhetők.

Ugyanez a terminálból. Kérj egy visszatérítést közvetlenül a `payments`-től,
belépés nélkül:

```bash
curl -s -X POST localhost:8003/api/payments/refunds \
  -H "Content-Type: application/json" \
  -d '{"order_id":4,"amount_huf":99999}' | jq
```

```json
{
  "id": 23,
  "kind": "refund",
  "order_id": 4,
  "amount_huf": 99999,
  "requested_by": "unknown (no mTLS)",
  "created_at": "..."
}
```

Nem kérdezett semmit. A `requested_by` mező azt mutatja, hogy azt sem tudja,
ki kérte. Erre a 4. blokkban visszatérünk.

Ez a mai első tanulság: minden service, amit külön elindítasz, egy újabb ajtó.

---

## 2. Blokk: API biztonság és Nginx

### 2.1 Belépés a terminálból

A következő parancsok Alice nevében futnak. Ehhez először belépünk, és
eltesszük a token-t egy változóba:

```bash
TOKEN=$(curl -s localhost:8080/api/orders/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"alice123"}' | jq -r .access_token)
echo $TOKEN
```

Egy hosszú szöveget kapsz, `eyJ`-vel kezdődik. Ez egy JWT.

> Ha új terminált nyitsz, ezt a lépést meg kell ismételni.

### 2.2 Öt támadás a nyitott shop ellen

**1. Más rendelésének olvasása (API1, BOLA).** Alice rendelései az 1-es és
a 2-es. Kérjük el a 3-ast:

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN" | jq
```

Bob rendelése, Bob nevével és címével. Elég volt átírni egy számot.

**2. Rendelés 0 forintért (API3).** A böngésző elküldi az árat is, és az
`orders` elhiszi:

```bash
curl -s -X POST localhost:8080/api/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":2,"quantity":1,"unit_price":0}]}' | jq
```

`"total_huf": 0`, `"status": "paid"`.

**3. Visszatérítés sima vásárlóként (API5).** Ez admin funkció lenne:

```bash
curl -s -X POST localhost:8080/api/orders/admin/refund/3 \
  -H "Authorization: Bearer $TOKEN" | jq
```

`"status": "refunded"`. Alice visszatérítette Bob rendelését.

**4. A régi API (API9).** Valaha volt egy `v1` végpont. Senki nem használja,
de még fut, és token sem kell hozzá:

```bash
curl -s "localhost:8080/api/orders/v1/orders?customer_id=2" | jq
```

Bob összes rendelése, címmel.

**5. A bot (API4, API6).** Ez a szkript Bob nevében, amilyen gyorsan csak tud,
újra és újra megpróbálja megvenni a limitált konzolt:

```bash
scripts/bot.sh
```

```
200 200 200 200 200 200 200 200 200 200 200 200 200 200 200
200 200 200 200 200 409 409 409 409 409 409 409 409 409 409
Orders placed: 20   sold out (409): 10   rate limited (429): 0   other: 0
```

Egy másodperc alatt elfogyott mind a 20. A 409 azt jelenti: nincs több.
Nézd meg a böngészőben is: **Sold out**.

### 2.3 Hol van a hiba a kódban?

Nyisd meg a `services/orders/main.py` fájlt, és keress rá: `VULNERABLE`.
Mindegyik hiba mellett ott a megjegyzés, és alatta, kikommentezve, a javítás.
Például a BOLA:

```python
# VULNERABLE (API1 BOLA): any logged-in customer can read any order,
# including the other customer's name and delivery address.
# FIX: only the owner may see it. Uncomment the two lines below.
# if order.customer_id != customer.id:
#     raise HTTPException(404, "Order not found")
```

Most nem javítjuk ki. Előbb nézzük meg, mit tud ebből megoldani egy gateway.

### 2.4 Nginx mint API gateway

Állítsd le a nyitott shopot, és indítsd el a gateway-es változatot:

```bash
docker compose down
docker compose -f compose.nginx.yaml up -d --build
```

Nyisd meg az `nginx/gateway.conf` fájlt, és olvassuk végig együtt. Öt rész
van benne:

1. **Rate limit**: token-enként percenként 6 rendelés.
2. **Routing**: mi érhető el egyáltalán. A `payments` és az `invoicing` nincs
   benne.
3. **Token ellenőrzés**: az Nginx minden kérésnél megkérdezi az `orders`-t,
   hogy a token érvényes-e (`auth_request`).
4. **Admin útvonalak**: csak admin token-nel.
5. **Régi verzió**: a `/api/orders/v1/` 404-et ad.

### 2.5 A támadások újra

A belső portok most zárva vannak:

```bash
curl -s -m 3 localhost:8003/api/payments/docs || echo "8003: closed"
```

Token nélkül nem megy semmi:

```bash
curl -s -i localhost:8080/api/orders/3
```

```
HTTP/1.1 401 Unauthorized
{"detail":"Gateway: missing or invalid token"}
```

Állítsd vissza a shopot, és lépj be újra:

```bash
scripts/reset-demo.sh
TOKEN=$(curl -s localhost:8080/api/orders/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"alice123"}' | jq -r .access_token)
```

**A bot:**

```bash
scripts/bot.sh
```

```
200 200 200 429 429 429 429 429 429 429 429 429 429 429 429
429 429 429 429 429 429 429 429 429 429 429 429 429 429 429
Orders placed: 3   sold out (409): 0   rate limited (429): 27   other: 0
```

Hármat még megvett, utána a gateway megállította. Egy ember ugyanekkor
nyugodtan vásárol, mert a limit token-enként számol:

```bash
curl -s -X POST localhost:8080/api/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":3,"quantity":1,"unit_price":8990}]}' | jq "{id, status, total_huf}"
```

**Visszatérítés vásárlóként:**

```bash
curl -s -i -X POST localhost:8080/api/orders/admin/refund/4 -H "Authorization: Bearer $TOKEN"
```

```
HTTP/1.1 403 Forbidden
{"detail":"Gateway: forbidden"}
```

Adminként viszont megy:

```bash
ADMIN=$(curl -s localhost:8080/api/orders/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | jq -r .access_token)
curl -s -X POST localhost:8080/api/orders/admin/refund/4 -H "Authorization: Bearer $ADMIN" | jq "{id, status}"
```

**A régi API:**

```bash
curl -s -i "localhost:8080/api/orders/v1/orders?customer_id=2"
```

```
HTTP/1.1 404 Not Found
{"detail":"Not Found"}
```

**És ami nem változott.** A BOLA és a 0 forintos rendelés:

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN" | jq "{id, delivery_name, delivery_address}"
curl -s -X POST localhost:8080/api/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":2,"quantity":1,"unit_price":0}]}' | jq "{id, status, total_huf}"
```

Mindkettő ugyanúgy átmegy. A gateway nem tudja, kié a 3-as rendelés, és azt
sem, mennyibe kerül egy konzol. Ez üzleti logika, azt csak a service-ben lehet
javítani. Ezt a következő lépésben megmutatom.

### 2.6 A javítás (előadói demó)

Ezt a lépést én csinálom a képernyőn, neked nem kell. A
`services/orders/main.py` fájlban kiveszem a `#` jelet a BOLA javítás két sora
elől, és csak az `orders` service-t építem újra:

```bash
docker compose -f compose.nginx.yaml up -d --build orders
```

Pár másodperc múlva:

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN"
```

```
{"detail":"Order not found"}
```

A többi service nem indult újra. Ez a független telepítés.

---

## 3. Blokk: Kubernetes

### 3.1 Cluster és telepítés

Először állítsd le a Compose-t, mert a cluster is a 8080-as portot akarja:

```bash
docker compose down
```

Aztán egy szkript elvégzi az egészet: létrehozza a `dedih` nevű kind
clustert, megépíti és betölti az image-eket, és telepíti a `k8s/` mappát a
`shop` namespace-be:

```bash
scripts/cluster-up.sh
```

Nagyjából egy-két perc. A végén:

```
NAME                             READY   STATUS    RESTARTS   AGE
catalog-5fc58cc9c7-mb5vk         1/1     Running   0          19s
einvoice-mock-674ff5b8f7-tb7fz   1/1     Running   0          19s
invoicing-5bb85568bc-hft7s       1/1     Running   0          19s
nginx-6bffc86cd5-cvsmd           1/1     Running   0          19s
orders-79cd75bfff-hfnhj          1/1     Running   0          19s
payments-86d748f4cf-nwmnr        1/1     Running   0          18s
postgres-0                       1/1     Running   0          18s
web-cb987f8b5-w77d4              1/1     Running   0          18s
```

Nyisd meg újra a shopot a 8080-as porton. Ugyanaz a shop, ugyanaz a
`gateway.conf`, csak most Kubernetesen. Az oldal alján a
`catalog served by` sorban most egy pod neve áll.

Nézz bele egy manifest-be, például a `k8s/orders.yaml`-ba. Az `orders` a
többi service-t a nevén éri el: `http://catalog:8000`. Ezt a Kubernetes DNS
oldja fel. Mindegyik service-nek saját ServiceAccount-ja van. Ez a 4. blokkban
lesz fontos.

### 3.2 Csak a catalog-ot skálázzuk

```bash
kubectl get pods -n shop
kubectl scale deployment catalog -n shop --replicas=3
kubectl get pods -n shop -l app=catalog
```

```
NAME                       READY   STATUS    RESTARTS   AGE
catalog-5fc58cc9c7-86gvb   1/1     Running   0          4s
catalog-5fc58cc9c7-mb5vk   1/1     Running   0          37s
catalog-5fc58cc9c7-thtzg   1/1     Running   0          4s
```

Frissítsd a böngészőt többször. A `catalog served by` sor változik: három pod
osztozik a forgalmon. A többi service egy példányban fut tovább. Ezt ígérte a
mikroszolgáltatás reggel: azt skálázod, aminek kell.

Ugyanez a terminálból:

```bash
for i in $(seq 1 9); do curl -s -o /dev/null -D - localhost:8080/api/catalog/products | grep -i x-served-by; done
```

### 3.3 Új verzió a catalog-ból, leállás nélkül

Indíts egy második terminált (a `+` jel a terminál panelen), és futtasd benne
ezt. Kétszer másodpercenként lekéri a terméket, és kiírja a választ és a
verziót:

```bash
while true; do curl -s -o /dev/null -w "%{http_code} " localhost:8080/api/catalog/products/1; curl -s -D - -o /dev/null localhost:8080/api/catalog/products/1 | grep -i x-app-version; sleep 0.5; done
```

Az első terminálban add ki az új verziót:

```bash
kubectl set env deployment/catalog -n shop APP_VERSION=v2
kubectl rollout status deployment/catalog -n shop
```

A második terminálban a `v1` sorok között megjelennek a `v2` sorok, aztán már
csak `v2` van. Közben minden válasz `200`. A Kubernetes egyesével cseréli a
podokat, és csak akkor küld forgalmat egy új podra, ha az már kész. Az
`orders`, a `payments` és a többi közben nem indult újra.

A második terminálban `Ctrl+C`.

A böngészőben is látszik: `catalog served by ..., version v2`.

### 3.4 Indítsd el a mesh telepítését (ebéd előtt)

```bash
scripts/mesh-up.sh
```

Ez feltelepíti az Istio-t, a Prometheus-t, a Grafana-t és a Kiali-t. Négy-öt
perc, ebéd alatt lefut. Az injection-t nem kapcsolja be, azt a 4. blokkban
kézzel csináljuk.

A végén ezt kell látnod:

```
NAME                          READY   STATUS    RESTARTS   AGE
grafana-7fb8cf5b56-zxrl4      1/1     Running   0          3m56s
istiod-5cf8f5d6df-rbc9z       1/1     Running   0          4m9s
kiali-745dfb677c-5qr4c        1/1     Running   0          3m56s
prometheus-6447557fdc-kmnt4   2/2     Running   0          3m56s
```

---

## 4. Blokk: zero trust a clusteren belül

Ebben a blokkban feltételezzük, hogy a `catalog` service-t feltörték. A
támadó a `catalog` podon belül futtat parancsokat, és onnan visszatérítést kér
a `payments`-től. A `catalog`-nak semmi dolga a `payments`-szel.

Indítsd el a belső oldalakat:

```bash
scripts/dashboards.sh
```

Nyisd meg a **PORTS** fülön a **payments (8003)** portot, és írd a cím végére:
`/api/payments/ledger`. Ez a fizetési napló. Az utolsó oszlop: ki kérte.

### 4.1 1. lépés: a támadás

```bash
scripts/attack-from-catalog.sh
```

```
==> From inside the catalog pod: POST http://payments:8000/api/payments/refunds
200 {"id":1,"kind":"refund","order_id":3,"amount_huf":39990,"requested_by":"unknown (no mTLS)",...}

==> The payments ledger, newest first
#1   refund  order 3     39990 HUF   requested by: unknown (no mTLS)
```

Átment, és senki nem tudja, ki kérte.

### 4.2 2. lépés: sidecar minden podba

```bash
kubectl get pods -n shop
kubectl label namespace shop istio-injection=enabled
kubectl rollout restart deployment -n shop
kubectl get pods -n shop
```

Fél perc után:

```
NAME                            READY   STATUS    RESTARTS   AGE
catalog-5f47986fdc-4l74k        2/2     Running   0          10s
catalog-5f47986fdc-v6nbm        2/2     Running   0          35s
catalog-5f47986fdc-xmb8l        2/2     Running   0          19s
einvoice-mock-df66f8476-g2xb8   2/2     Running   0          35s
invoicing-7f6d84f9b-2mldk       2/2     Running   0          35s
nginx-785b5578b4-qnjg4          2/2     Running   0          35s
orders-79bd95ddd6-btwrb         2/2     Running   0          35s
payments-7d6985bcfb-ctcvj       2/2     Running   0          35s
postgres-0                      1/1     Running   0          28m
web-689b57cff4-mj72k            2/2     Running   0          35s
```

`1/1` helyett `2/2`: minden pod mellé bekerült egy második konténer, az Envoy
sidecar. A `postgres` szándékosan kimaradt, az adatbázis ma a mesh-en kívül
marad.

Mivel a podok újraindultak, futtasd újra:

```bash
scripts/dashboards.sh
```

A támadás újra:

```bash
scripts/attack-from-catalog.sh
```

```
200 {"id":1,"kind":"refund","order_id":3,"amount_huf":39990,"requested_by":"spiffe://cluster.local/ns/shop/sa/catalog",...}

#1   refund  order 3     39990 HUF   requested by: spiffe://cluster.local/ns/shop/sa/catalog
```

Még mindig átmegy. De most már tudjuk, ki volt: a `shop` namespace `catalog`
ServiceAccount-ja. Ez a **workload identity**, SPIFFE formátumban. Rendelj
valamit a böngészőben, és nézd meg a naplót: a fizetésnél
`spiffe://cluster.local/ns/shop/sa/orders` áll.

### 4.3 3. lépés: STRICT mTLS

Van egy másik támadó is: egy pod a `shop` namespace-ben, de sidecar nélkül.
Ő még mindig átjut:

```bash
scripts/attack-from-outside-mesh.sh
```

Most kapcsoljuk be a szigorú mTLS-t:

```bash
kubectl apply -f mesh/01-strict-mtls.yaml
```

Pár másodperc múlva:

```bash
scripts/attack-from-outside-mesh.sh
```

```
connection failed: [Errno 104] Connection reset by peer
```

Nincs tanúsítványa, nincs identitása, nem jut be. És a `catalog`?

```bash
scripts/attack-from-catalog.sh
```

```
200 {"id":3,"kind":"refund","order_id":3,"amount_huf":39990,"requested_by":"spiffe://cluster.local/ns/shop/sa/catalog",...}
```

**Még mindig átmegy.** A `catalog` része a mesh-nek, érvényes tanúsítványa
van. Az mTLS azt bizonyítja, hogy **ki** hív. Azt nem dönti el, hogy **mit
szabad** neki.

### 4.4 4. lépés: AuthorizationPolicy

Nyisd meg a `mesh/02-payments-policy.yaml` fájlt. Azt mondja: a `payments`-t
és az `invoicing`-ot csak az `orders` ServiceAccount hívhatja.

```bash
kubectl apply -f mesh/02-payments-policy.yaml
```

Várj tíz másodpercet, aztán:

```bash
scripts/attack-from-catalog.sh
```

```
==> From inside the catalog pod: POST http://payments:8000/api/payments/refunds
403 RBAC: access denied
```

> Ha még `200`-at kapsz, várj még tíz másodpercet, és futtasd újra. A szabálynak
> el kell jutnia a sidecar-okhoz, és a már nyitott kapcsolatok egy ideig még a
> régi szabállyal mennek. A teszteken ez 0 és kb. 20 másodperc között volt.

A shop közben működik: rendelj valamit a böngészőben. Az `orders` hívhatja a
`payments`-t, mert ő az `orders`.

Összefoglalva: a NetworkPolicy azt mondja meg, **honnan** jöhet egy hívás. Az
mTLS azt, hogy **ki** hív. Az AuthorizationPolicy azt, hogy **mit szabad**
neki.

---

## 5. Blokk: monitoring

### 5.1 Nyisd meg a műszerfalakat

Ha a 4. blokk óta nem futtattad:

```bash
scripts/dashboards.sh
```

A **PORTS** fülön:

| Port | Mi |
| --- | --- |
| 3000 | Grafana. Bal oldalt **Dashboards**, **shop** mappa, **Retro Game Shop** |
| 20001 | Kiali. A cím végére: `/kiali`. **Traffic Graph**, namespace: `shop` |
| 9090 | Prometheus. Felül **Alerts** |

A service-ek kódjában egy sor monitoring kód sincs. Minden szám az Envoy
sidecar-okból jön.

### 5.2 Normál forgalom

Egy második terminálban:

```bash
scripts/traffic.sh
```

Ez néhány vásárlót játszik el: böngésznek, néha rendelnek. Hagyd futni. Egy-két
perc után a Grafana-ban megjelennek a vonalak, a Kiali-ban pedig a service
gráf, a nyilakon lakat ikonnal: ott mTLS van.

### 5.3 Jön a bot

Az első terminálban:

```bash
scripts/bot.sh 6000
```

Ez egy-két percig fut (a teszt gépen 70 másodperc volt). Nézd a Grafana-t: a **Responses at the gateway**
panelen a `429`-es vonal felugrik, a normál `200` mellette alig mozdul.

Nézd a Prometheus **Alerts** oldalát. A `ShopRequestFlood` szabály előbb
**Pending**, aztán a bot indítása után körülbelül egy perccel **Firing**. A szabály a
`mesh/addons/prometheus.yaml` fájlban van, olvasható.

### 5.4 Ha egy partner kiesik (opcionális)

Állítsuk le a külső számlázó rendszert:

```bash
kubectl scale deployment einvoice-mock -n shop --replicas=0
```

Rendelj valamit a böngészőben. A rendelés sikerül. Nyisd meg a **invoicing
(8004)** portot, a cím végére: `/api/invoicing/invoices`. Az új számla
`pending`. Egy-két perc múlva a Prometheus-ban tüzel az
`ExternalInvoicingFailing` riasztás.

Kapcsold vissza:

```bash
kubectl scale deployment einvoice-mock -n shop --replicas=1
```

Tíz-húsz másodperc múlva a függő számla `sent` lesz. Az `invoicing` tíz
másodpercenként újrapróbálja.

A második terminálban állítsd le a forgalmat: `Ctrl+C`.

---

## 6. Takarítás

```bash
pkill -f "kubectl port-forward"
kind delete cluster --name dedih
docker compose down
```

A Codespace törlése: a forkodon **Code** gomb, **Codespaces** fül, a három pont,
**Delete**.

---

## 7. Hibaelhárítás

**Valamelyik parancsot (`kind`, `istioctl`, `jq`) nem találja a terminál.**
`F1`, majd **Codespaces: Rebuild Container**.

**`port is already allocated` vagy a `cluster-up.sh` szerint foglalt a 8080.**
Fut még a Compose. `docker compose down`, és próbáld újra.

**`Login failed` a `bot.sh` vagy a `traffic.sh` futtatásakor.**
Nem fut a shop a 8080-as porton. `docker compose ps` vagy
`kubectl get pods -n shop`.

**`jq: parse error` egy `curl` parancs után.**
A válasz nem JSON, valószínűleg hiba. Futtasd újra a parancsot `| jq` nélkül,
és nézd meg, mit kaptál.

**`401` minden kérésre.** Új terminálban nincs `TOKEN` változó. Ismételd meg a
2.1-es belépést.

**`502 Bad Gateway` Compose alatt, miután egy service-t újraépítettünk.**
`docker compose -f compose.nginx.yaml restart nginx`.

**A 8080-as porton nem válaszol semmi, közvetlenül a cluster létrehozása után.**
Várj tíz másodpercet, és próbáld újra.

**A Grafana, a Kiali vagy a ledger nem nyílik meg.**
Futtasd újra: `scripts/dashboards.sh`.

**A `kubectl get pods -n shop` szerint egy pod `Pending` vagy `ImagePullBackOff`.**
`kubectl describe pod <név> -n shop`, a végén az `Events` megmondja, miért.
Ha `ImagePullBackOff`, futtasd újra a `scripts/cluster-up.sh` szkriptet.

**Az AuthorizationPolicy után a támadás még `200`.**
Várj tíz másodpercet, és futtasd újra.

**Mindent elrontottam a clusterben, tiszta lapot szeretnék.**

```bash
kind delete cluster --name dedih
scripts/cluster-up.sh
```

---

## 8. Parancsok összefoglalva

| Parancs | Mit csinál |
| --- | --- |
| `docker compose up -d --build` | a nyitott shop (1. blokk) |
| `docker compose -f compose.nginx.yaml up -d --build` | a shop gateway mögött (2. blokk) |
| `docker compose down` | leállítás |
| `scripts/bot.sh` | a bot, a limitált konzolt próbálja megvenni |
| `scripts/reset-demo.sh` | a shop alapállapotba |
| `scripts/cluster-up.sh` | kind cluster és a shop Kubernetesen |
| `kubectl get pods -n shop` | mi fut a clusterben |
| `kubectl scale deployment catalog -n shop --replicas=3` | példányszám állítása |
| `kubectl set env deployment/catalog -n shop APP_VERSION=v2` | új verzió kiadása |
| `kubectl rollout status deployment/catalog -n shop` | megvárja, amíg kész |
| `scripts/mesh-up.sh` | Istio és monitoring telepítése |
| `kubectl label namespace shop istio-injection=enabled` | sidecar injection bekapcsolása |
| `kubectl rollout restart deployment -n shop` | minden pod újraindítása |
| `kubectl apply -f mesh/01-strict-mtls.yaml` | csak mTLS-sel lehet bejutni |
| `kubectl apply -f mesh/02-payments-policy.yaml` | csak az `orders` hívhatja a `payments`-t |
| `scripts/attack-from-catalog.sh` | támadás a feltört catalog podból |
| `scripts/attack-from-outside-mesh.sh` | támadás sidecar nélküli podból |
| `scripts/dashboards.sh` | Grafana, Kiali, Prometheus és a belső oldalak |
| `scripts/traffic.sh` | normál forgalom a grafikonokhoz |
| `kind delete cluster --name dedih` | a cluster törlése |
