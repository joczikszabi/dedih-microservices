# Mikroszolgáltatás architektúra, gyakorlati útmutató

ELTE IK, DEDIH 2.0. Ebben a dokumentumban benne van minden lépés, amit ma
végigcsinálunk, és a fontosabb kimenetek is, amiket látni fogsz. Ha lemaradsz,
innen egyedül is folytatni tudod.

---

## Mit csinálunk ma

| Blokk | Téma | Min fut |
| --- | --- | --- |
| 1 | Mikroszolgáltatások: mit, mikor, mikor ne | Docker Compose, gateway nélkül |
| 2 | API biztonság és Nginx | Docker Compose, gateway mögött |
| 3 | Mikroszolgáltatások Kubernetesen | kind |
| 4 | Zero trust a clusteren belül: Istio, mTLS, workload identity | kind és Istio |
| 5 | Monitoring | kind, Prometheus, Grafana, Kiali |

Az alkalmazás egy kitalált webshop, a **Retro Game Shop**. Retro játékokat és
konzolokat árul. Van egy limitált termék is: egy újra kiadott kézi konzol,
összesen **20 darab**.

A shop öt service-ből áll:

| Service | Mit csinál |
| --- | --- |
| `web` | a weboldal, amit a böngészőben látsz |
| `catalog` | termékek, árak, készlet |
| `orders` | vásárlók, belépés, rendelés, visszatérítés |
| `payments` | fizetés és visszatérítés (szimulált), belső service |
| `invoicing` | számlák, belső service |

Mellettük fut még az `einvoice-mock`, ami egy külső számlázó rendszert játszik
el, egy Postgres adatbázis, és legelöl egy Nginx.

Ma ezeket a támadásokat próbáljuk ki, és ezt látjuk majd a nap végén:

| Támadás | Gateway nélkül | Gateway mögött | A javítás után | Istio után |
| --- | --- | --- | --- | --- |
| Más vásárló rendelésének olvasása (BOLA) | átmegy | átmegy | **elutasítva** | |
| Rendelés 0 forintért | átmegy | átmegy | **elutasítva** | |
| Visszatérítés sima vásárlóként | átmegy | **403** | | |
| A bot megveszi mind a 20 konzolt | átmegy | **429** | | |
| Régi `/v1` végpont | átmegy | **404** | | |
| A feltört `catalog` pod visszatérítést kér a `payments` service-től | átmegy | átmegy | | **RBAC: access denied** |

Egyetlen réteg sem javít meg mindent.

---

## Fontos tudnivalók

**Tesztfiókok** (minden adat kitalált):

| E-mail | Jelszó | Szerep |
| --- | --- | --- |
| `alice@example.com` | `alice123` | vásárló |
| `bob@example.com` | `bob123` | vásárló |
| `admin@example.com` | `admin123` | admin |

**Ha valami elromlott, és tiszta lappal kezdenéd**, ez a parancs visszaállítja
a termékeket, a készletet és a rendeléseket. Compose alatt és Kubernetesen is
működik:

```bash
scripts/reset-demo.sh
```

**A nap végén töröld a Codespace-t.** A lépéseket a 6. fejezetben találod.

---

## 0. Előkészületek

1. Nyisd meg: `https://github.com/joczikszabi/dedih-microservices`
2. Jobb felül **Fork**, majd **Create fork**.
3. A **saját** forkodon: zöld **Code** gomb, **Codespaces** fül, a `...` menü,
   **New with options**. A **Machine type** legyen **4-core**, majd
   **Create codespace**.
4. Az első indítás kb. öt perc.

> **Gépigény:** legalább 4 CPU mag és 8 GB memória. A teljes cluster az Istióval
> és a monitoringgal együtt kb. 3 GB memóriát használ, a CPU a szűkebb keresztmetszet.
>
> - **Codespaces:** a **4-core** gép (16 GB) az ajánlott. A 2-core gépen a délutáni
>   Istio és monitoring nincs kipróbálva.
> - **Saját gépen:** Docker Desktopban legalább 4 CPU és 8 GB memória legyen
>   beállítva (Settings, Resources).

Ha elindult, ellenőrizd a terminálban:

```bash
docker --version
docker compose version
kubectl version --client
kind --version
istioctl version --remote=false
```

> Ha valamelyik parancsot nem találja, akkor a container létrehozásakor futó
> szkript hibára futott. A javítás: nyisd meg a Command Palette-et
> (`Ctrl+Shift+P`, Macen `Cmd+Shift+P`), majd **Codespaces: Rebuild Container**. A `postCreateCommand` ugyanis csak a
> container létrehozásakor fut le, újraindításkor nem.

---

## 1. Blokk: a webshop gateway nélkül

### 1.1 Indítsd el

```bash
cd /workspaces/dedih-microservices
docker compose up -d --build
```

Az első indítás kb. három perc, mert minden image-et most épít meg.

```bash
docker compose ps
```

Nyolc konténert látsz: a négy backend service (`catalog`, `orders`, `payments`,
`invoicing`), az `einvoice-mock`, a `web`, a `postgres` és az `nginx`.

Az indítás után a service-eknek még kb. öt másodperc kell, amíg csatlakoznak
az adatbázishoz. Ha addig `502 Bad Gateway` jön, várj egy kicsit, és próbáld
újra.

Ez a shop **nyitott változata**: van előtte egy Nginx, de az csak továbbítja a
kéréseket, semmit nem ellenőriz.

### 1.2 Próbáld ki a shopot

A Codespace alján nyisd meg a **PORTS** fület, és a **Shop (8080)** sorban
kattints a földgömb ikonra.

1. Nézd meg a termékeket. Az oldal alján van egy szürke sor:
   `catalog served by ...`. Ez mutatja, melyik `catalog` példány válaszolt.
   Most még csak egy van, a 3. blokkban lesz belőle három.
2. **Log in**. A mezőkben már Alice adatai vannak.
3. Tegyél valamit a kosárba, és rendeld meg.
4. **My orders**: itt látod a rendelésedet.

### 1.3 Minden service elérhető kívülről

A shop a 8080-as porton fut. A **PORTS** fülön viszont más portok is vannak:

| Port | Service |
| --- | --- |
| 8001 | catalog |
| 8002 | orders |
| 8003 | payments |
| 8004 | invoicing |

Nyisd meg mindegyiket, és írd a cím végére: `/docs`. Mindegyiknél bejön egy
Swagger UI, a service teljes API-jával. A `payments` és az `invoicing` belső
service, a böngészőből el sem kellene érni őket. Mégis elérhetők.

Ugyanez a terminálból: kérj visszatérítést közvetlenül a `payments`
service-től, belépés nélkül.

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

Semmit nem kérdezett, egyszerűen végrehajtotta. A `requested_by` mező szerint
azt sem tudja, ki kérte. Erre a 4. blokkban visszatérünk.

Minden külön elindított service egy újabb végpont, amit kívülről el lehet érni.

---

## 2. Blokk: API biztonság és Nginx

### 2.1 Belépés a terminálból

A következő parancsok Alice nevében futnak. Ehhez először belépünk, és a
tokent eltesszük egy változóba:

```bash
TOKEN=$(curl -s localhost:8080/api/orders/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"alice123"}' | jq -r .access_token)
echo $TOKEN
```

Egy hosszú szöveget kapsz, ami `eyJ`-vel kezdődik. Ez egy JWT.

> Ha új terminált nyitsz, ezt a lépést ott is meg kell ismételni.

### 2.2 Öt támadás a nyitott változat ellen

**1. Más rendelésének olvasása (API1, BOLA).** Alice rendelései az 1-es és a
2-es. Kérjük el a 3-ast:

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN" | jq
```

Megjön Bob rendelése, Bob nevével és címével. Elég volt átírni egy számot.

**2. Rendelés 0 forintért (API3).** A böngésző a rendeléssel együtt az árat is
elküldi, és az `orders` elfogadja:

```bash
curl -s -X POST localhost:8080/api/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":2,"quantity":1,"unit_price":0}]}' | jq
```

A válaszban `"total_huf": 0` és `"status": "paid"` áll.

**3. Visszatérítés sima vásárlóként (API5).** Ez adminoknak szánt funkció:

```bash
curl -s -X POST localhost:8080/api/orders/admin/refund/3 \
  -H "Authorization: Bearer $TOKEN" | jq
```

A válaszban `"status": "refunded"`. Alice visszatérítette Bob rendelését.

**4. A régi API (API9).** Valamikor volt egy `v1` végpont. Már senki nem
használja, de még fut, és token sem kell hozzá:

```bash
curl -s "localhost:8080/api/orders/v1/orders?customer_id=2" | jq
```

Megjön Bob összes rendelése, címmel együtt.

**5. A bot (API4, API6).** Ez a szkript belép Bobként, és amilyen gyorsan csak
tud, újra és újra megpróbálja megvenni a limitált konzolt:

```bash
scripts/bot.sh
```

```
200 200 200 200 200 200 200 200 200 200 200 200 200 200 200
200 200 200 200 200 409 409 409 409 409 409 409 409 409 409
Orders placed: 20   sold out (409): 10   rate limited (429): 0   other: 0
```

Egy másodperc alatt elfogyott mind a 20. A 409 azt jelenti, hogy nincs több.
A böngészőben is látszik: **Sold out**.

### 2.3 Hol van a hiba a kódban?

Nyisd meg a `services/orders/main.py` fájlt, és keress rá erre: `VULNERABLE`.
Mindegyik hibánál ott van egy megjegyzés, és alatta kommentben a javítás. A
javításhoz a sorok elől ki kell venni a `#` jelet. Például a BOLA:

```python
# VULNERABLE (API1 BOLA): any logged-in customer can read any order,
# including the other customer's name and delivery address.
# FIX: only the owner may see it. Uncomment the two lines below.
# if order.customer_id != customer.id:
#     raise HTTPException(404, "Order not found")
```

Most még nem javítjuk ki. Előbb megnézzük, mit tud ebből megoldani egy gateway.

### 2.4 Nginx mint API gateway

Állítsd le a nyitott változatot, és indítsd el ugyanazt a gateway mögött:

```bash
docker compose down
docker compose -f compose.nginx.yaml up -d --build
```

Nyisd meg az `nginx/gateway.conf` fájlt. Öt része van:

1. **Rate limit**: tokenenként percenként 6 rendelés.
2. **Routing**: mi érhető el kívülről egyáltalán. A `payments` és az
   `invoicing` nincs benne.
3. **Token ellenőrzés**: az Nginx minden kérésnél megkérdezi az `orders`
   service-t, hogy érvényes-e a token (`auth_request`).
4. **Admin útvonalak**: csak admin tokennel érhetők el.
5. **Régi verzió**: a `/api/orders/v1/` útvonal 404-et ad.

### 2.5 A támadások újra, a gateway mögött

A belső portok most zárva vannak:

```bash
curl -s -m 3 localhost:8003/api/payments/docs || echo "8003: closed"
```

Token nélkül semmi nem megy át:

```bash
curl -s -i localhost:8080/api/orders/3
```

```
HTTP/1.1 401 Unauthorized
{"detail":"Gateway: missing or invalid token"}
```

Állítsd vissza a shop adatait, és lépj be újra:

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

Hármat még megvett, utána a gateway megállította. Közben Alice nyugodtan
vásárolhat, mert a limit tokenenként számol:

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

Admin tokennel viszont működik:

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

**Ami nem változott: a BOLA és a 0 forintos rendelés.**

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN" | jq "{id, delivery_name, delivery_address}"
curl -s -X POST localhost:8080/api/orders/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":2,"quantity":1,"unit_price":0}]}' | jq "{id, status, total_huf}"
```

Mindkettő ugyanúgy átmegy. A gateway nem tudja, kié a 3-as rendelés, és azt
sem, mennyibe kerül egy konzol. Ez üzleti logika, ezt csak a service kódjában
lehet javítani.

### 2.6 A javítás után (előadói demó)

Ezt a lépést az előadó mutatja meg a képernyőn, neked nem kell megcsinálnod.
A `services/orders/main.py` fájlban a BOLA javítás két sora elől kivesszük a
`#` jelet, és csak az `orders` service-t építjük újra:

```bash
docker compose -f compose.nginx.yaml up -d --build orders
```

Néhány másodperc múlva ugyanaz a kérés:

```bash
curl -s localhost:8080/api/orders/3 -H "Authorization: Bearer $TOKEN"
```

```
{"detail":"Order not found"}
```

A többi service közben nem indult újra. Ez a független telepítés: egy
service-t ki lehet cserélni úgy, hogy a többihez nem nyúlunk.

---

## 3. Blokk: Kubernetes

### 3.1 A cluster és a shop

Először állítsd le a Compose-t, mert a cluster is a 8080-as portot használja:

```bash
docker compose down
```

Utána egy szkript elvégzi az egészet. Létrehozza a `dedih` nevű kind
clustert, megépíti és betölti az image-eket, és telepíti a `k8s/` mappát a
`shop` namespace-be:

```bash
scripts/cluster-up.sh
```

Ez kb. két perc. A végén ezt látod:

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

Nyisd meg újra a shopot a 8080-as porton. Ugyanaz a shop, ugyanazzal a
`gateway.conf` fájllal, csak most Kubernetesen fut. Az oldal alján a
`catalog served by` sorban most egy pod neve áll.

Nézz bele egy manifestbe, például a `k8s/orders.yaml` fájlba. Az `orders` a
többi service-t a nevén éri el, például `http://catalog:8000`. A nevet a
Kubernetes DNS oldja fel. Minden service-nek saját ServiceAccountja van, ez a
4. blokkban lesz fontos.

### 3.2 Csak a catalogot skálázzuk

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

Frissítsd a böngészőt többször egymás után. A `catalog served by` sor
változik, mert három pod osztozik a forgalmon. A többi service közben egy
példányban fut tovább. Ez volt az 1. blokk egyik ígérete: csak azt skálázod,
aminek kell.

Ugyanez a terminálból:

```bash
for i in $(seq 1 9); do curl -s -o /dev/null -D - localhost:8080/api/catalog/products | grep -i x-served-by; done
```

### 3.3 Új catalog verzió, leállás nélkül

Nyiss egy második terminált (a `+` jel a terminál panelen), és futtasd benne
ezt. Fél másodpercenként lekéri a terméket, és kiírja a választ meg a verziót:

```bash
while true; do curl -s -o /dev/null -w "%{http_code} " localhost:8080/api/catalog/products/1; curl -s -D - -o /dev/null localhost:8080/api/catalog/products/1 | grep -i x-app-version; sleep 0.5; done
```

Az első terminálban add ki az új verziót:

```bash
kubectl set env deployment/catalog -n shop APP_VERSION=v2
kubectl rollout status deployment/catalog -n shop
```

A második terminálban a `v1` sorok között megjelennek a `v2` sorok, aztán már
csak `v2` jön. Közben minden válasz `200`. A Kubernetes egyesével cseréli a
podokat, és egy új podra csak akkor küld forgalmat, amikor az már készen áll.
Az `orders`, a `payments` és a többi service közben nem indult újra.

A második terminálban állítsd le a ciklust: `Ctrl+C`.

A böngészőben is látszik: `catalog served by ..., version v2`.

### 3.4 Indítsd el az Istio és a monitoring telepítését (ebéd előtt)

```bash
scripts/mesh-up.sh
```

Ez telepíti az Istiót, a Prometheust, a Grafanát és a Kialit. Kb. öt perc,
ebéd alatt lefut. A sidecar injectiont nem kapcsolja be, azt a 4. blokkban
kézzel csináljuk meg.

A végén ezt látod:

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
támadó a `catalog` podon belül futtat parancsokat, és onnan kér
visszatérítést a `payments` service-től. A `catalog` service-nek semmi dolga a
`payments` service-szel.

Indítsd el a belső oldalakat:

```bash
scripts/dashboards.sh
```

Nyisd meg a **PORTS** fülön a **payments (8003)** portot, és írd a cím végére:
`/api/payments/ledger`. Ez a fizetési napló (ledger). Az utolsó oszlopban az
áll, hogy ki kérte az adott tételt.

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

A kérés átment, és senki nem tudja, ki küldte.

### 4.2 2. lépés: sidecar minden podba

```bash
kubectl get pods -n shop
kubectl label namespace shop istio-injection=enabled
kubectl rollout restart deployment -n shop
kubectl get pods -n shop
```

Kb. fél perc múlva:

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

`1/1` helyett most `2/2` áll: minden podba bekerült egy második konténer, az
Envoy sidecar. A `postgres` szándékosan kimaradt, az adatbázis ma a mesh-en
kívül marad.

A podok újraindultak, ezért a belső oldalakat is újra kell indítani:

```bash
scripts/dashboards.sh
```

Most futtasd újra a támadást:

```bash
scripts/attack-from-catalog.sh
```

```
200 {"id":1,"kind":"refund","order_id":3,"amount_huf":39990,"requested_by":"spiffe://cluster.local/ns/shop/sa/catalog",...}

#1   refund  order 3     39990 HUF   requested by: spiffe://cluster.local/ns/shop/sa/catalog
```

Még mindig átmegy, de most már látjuk, ki volt: a `shop` namespace `catalog`
ServiceAccountja. Ez a **workload identity**, SPIFFE formátumban. Rendelj
valamit a böngészőben, és nézd meg a ledgert: a fizetés mellett
`spiffe://cluster.local/ns/shop/sa/orders` áll.

### 4.3 3. lépés: STRICT mTLS

Van egy másik támadó is: egy pod a `shop` namespace-ben, de sidecar nélkül.
Ő most még átjut:

```bash
scripts/attack-from-outside-mesh.sh
```

Kapcsoljuk be a szigorú mTLS-t:

```bash
kubectl apply -f mesh/01-strict-mtls.yaml
```

Néhány másodperc múlva próbáld újra:

```bash
scripts/attack-from-outside-mesh.sh
```

```
connection failed: [Errno 104] Connection reset by peer
```

Nincs tanúsítványa, így identitása sincs, és nem jut be. És a `catalog`?

```bash
scripts/attack-from-catalog.sh
```

```
200 {"id":3,"kind":"refund","order_id":3,"amount_huf":39990,"requested_by":"spiffe://cluster.local/ns/shop/sa/catalog",...}
```

**Még mindig átmegy.** A `catalog` a mesh része, érvényes tanúsítványa van. Az
mTLS azt bizonyítja, hogy **ki** hív. Azt nem dönti el, hogy **mit szabad**
neki.

### 4.4 4. lépés: AuthorizationPolicy

Nyisd meg a `mesh/02-payments-policy.yaml` fájlt. Ez a szabály azt mondja ki,
hogy a `payments` és az `invoicing` service-t csak az `orders` ServiceAccount
hívhatja.

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

> Ha még `200` jön, várj újabb tíz másodpercet, és futtasd újra. A szabálynak
> el kell jutnia a sidecarokhoz, és a már nyitott kapcsolatok egy ideig még a
> régi szabállyal mennek. A teszteken ez 0 és kb. 20 másodperc között volt.

A shop közben működik: rendelj valamit a böngészőben. Az `orders` hívhatja a
`payments` service-t, mert ő az `orders` ServiceAccounttal fut.

Összefoglalva: a NetworkPolicy azt mondja meg, **honnan** jöhet egy hívás. Az
mTLS azt, hogy **ki** hív. Az AuthorizationPolicy azt, hogy **mit szabad**
neki.

---

## 5. Blokk: monitoring

### 5.1 Nyisd meg a dashboardokat

Ha a 4. blokk óta nem futtattad:

```bash
scripts/dashboards.sh
```

A **PORTS** fülön:

| Port | Mi fut rajta |
| --- | --- |
| 3000 | Grafana. Bal oldalt **Dashboards**, **shop** mappa, **Retro Game Shop** |
| 20001 | Kiali. A cím végére írd: `/kiali`. **Traffic Graph**, namespace: `shop` |
| 9090 | Prometheus. Felül **Alerts** |

A service-ek kódjában egyetlen sor monitoring kód sincs. Minden szám az Envoy
sidecarokból jön.

### 5.2 Normál forgalom

Egy második terminálban:

```bash
scripts/traffic.sh
```

Ez néhány vásárlót játszik el: nézelődnek, és néha rendelnek is. Hagyd futni.
Kb. egy perc múlva megjelennek a vonalak a Grafanában, a Kialiban pedig a
service gráf. A nyilakon lakat ikon jelzi, hogy ott mTLS van.

### 5.3 Jön a bot

Az első terminálban:

```bash
scripts/bot.sh 6000
```

Ez kb. egy percig fut (a teszt gépen 70 másodpercig). Nézd a Grafanát: a
**Responses at the gateway** panelen a `429` vonala felugrik, a normál `200`
mellette alig mozdul.

Nézd meg a Prometheus **Alerts** oldalát is. A `ShopRequestFlood` szabály
előbb **Pending** állapotba kerül, majd kb. egy perccel a bot indítása után
**Firing** lesz. A szabályt a `mesh/addons/prometheus.yaml` fájlban találod.

### 5.4 Ha egy partner kiesik (opcionális)

Állítsuk le a külső számlázó rendszert:

```bash
kubectl scale deployment einvoice-mock -n shop --replicas=0
```

Rendelj valamit a böngészőben. A rendelés sikerül. Nyisd meg az **invoicing
(8004)** portot, és írd a cím végére: `/api/invoicing/invoices`. Az új számla
állapota `pending`. Kb. egy perc múlva a Prometheusban tüzel az
`ExternalInvoicingFailing` riasztás.

Kapcsold vissza:

```bash
kubectl scale deployment einvoice-mock -n shop --replicas=1
```

Az `invoicing` tíz másodpercenként újrapróbálja a függő számlákat, így kb. húsz
másodpercen belül a számla `sent` lesz.

A második terminálban állítsd le a forgalmat: `Ctrl+C`.

---

## 6. A nap végén: leállítás és törlés

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
Command Palette (`Ctrl+Shift+P`, Macen `Cmd+Shift+P`), majd **Codespaces: Rebuild Container**.

**`port is already allocated`, vagy a `cluster-up.sh` szerint foglalt a 8080.**
Még fut a Compose. Add ki a `docker compose down` parancsot, és próbáld újra.

**`Login failed` a `bot.sh` vagy a `traffic.sh` futtatásakor.**
Nem fut a shop a 8080-as porton. Nézd meg: `docker compose ps` vagy
`kubectl get pods -n shop`.

**`jq: parse error` egy `curl` parancs után.**
A válasz nem JSON, valószínűleg hibaüzenet. Futtasd újra a parancsot `| jq`
nélkül, és nézd meg, mit kaptál.

**Minden kérésre `401` jön.** Új terminálban nincs `TOKEN` változó. Ismételd
meg a 2.1-es belépést.

**`502 Bad Gateway` közvetlenül a `docker compose up` után.**
A service-ek még az adatbázisra várnak. Várj néhány másodpercet, és próbáld
újra.

**`502 Bad Gateway` Compose alatt, és fél perc múlva sem múlik el.**
`docker compose -f compose.nginx.yaml restart nginx`.

**A 8080-as porton nem válaszol semmi, közvetlenül a cluster létrehozása után.**
Várj tíz másodpercet, és próbáld újra.

**Nem nyílik meg a Grafana, a Kiali vagy a ledger.**
Futtasd újra: `scripts/dashboards.sh`.

**A `kubectl get pods -n shop` szerint egy pod `Pending` vagy `ImagePullBackOff` állapotban van.**
`kubectl describe pod <név> -n shop`. A kimenet végén az `Events` rész
megmondja, mi a gond. `ImagePullBackOff` esetén futtasd újra a
`scripts/cluster-up.sh` szkriptet.

**Az AuthorizationPolicy után a támadás még mindig `200`.**
Várj tíz másodpercet, és futtasd újra.

**Mindent elrontottam a clusterben, tiszta lappal kezdeném.**

```bash
kind delete cluster --name dedih
scripts/cluster-up.sh
```

---

## 8. Parancsok összefoglalva

| Parancs | Mit csinál |
| --- | --- |
| `docker compose up -d --build` | a shop nyitott változata, gateway nélkül (1. blokk) |
| `docker compose -f compose.nginx.yaml up -d --build` | a shop a gateway mögött (2. blokk) |
| `docker compose down` | leállítás |
| `scripts/bot.sh` | a bot, ami a limitált konzolt próbálja megvenni |
| `scripts/reset-demo.sh` | visszaállítja a shop kiinduló adatait |
| `scripts/cluster-up.sh` | kind cluster, rajta a shop |
| `kubectl get pods -n shop` | mi fut a clusterben |
| `kubectl scale deployment catalog -n shop --replicas=3` | a példányszám beállítása |
| `kubectl set env deployment/catalog -n shop APP_VERSION=v2` | új verzió kiadása |
| `kubectl rollout status deployment/catalog -n shop` | megvárja, amíg a rollout kész |
| `scripts/mesh-up.sh` | az Istio és a monitoring telepítése |
| `kubectl label namespace shop istio-injection=enabled` | a sidecar injection bekapcsolása |
| `kubectl rollout restart deployment -n shop` | minden pod újraindítása |
| `kubectl apply -f mesh/01-strict-mtls.yaml` | csak mTLS-sel lehet bejutni |
| `kubectl apply -f mesh/02-payments-policy.yaml` | csak az `orders` hívhatja a `payments` service-t |
| `scripts/attack-from-catalog.sh` | támadás a feltört catalog podból |
| `scripts/attack-from-outside-mesh.sh` | támadás egy sidecar nélküli podból |
| `scripts/dashboards.sh` | Grafana, Kiali, Prometheus és a belső oldalak |
| `scripts/traffic.sh` | normál forgalom a grafikonokhoz |
| `kind delete cluster --name dedih` | a cluster törlése |
