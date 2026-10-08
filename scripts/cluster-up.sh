#!/usr/bin/env bash
#
# Block 3: the shop on Kubernetes.
#
#   scripts/cluster-up.sh
#
# 1. creates the kind cluster "dedih" (one node, port 8080 mapped to Nginx)
# 2. builds the six images and loads them into the cluster (no registry)
# 3. creates the ConfigMaps from db/init.sql and nginx/gateway.conf
# 4. applies everything in k8s/ into the namespace "shop" and waits for it
#
# Run `docker compose down` first: Compose and the cluster both want 8080.

set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=dedih
IMAGES="catalog orders payments invoicing einvoice-mock"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  if [ -n "$(docker ps -q --filter publish=8080)" ]; then
    echo "Port 8080 is already in use by a container, probably the Compose stack:"
    docker ps --filter publish=8080 --format '  {{.Names}}'
    echo "Run this first, then try again:"
    echo "  docker compose down"
    exit 1
  fi
  echo "==> Creating the kind cluster \"$CLUSTER\""
  kind create cluster --config kind/kind-config.yaml
else
  echo "==> Cluster \"$CLUSTER\" already exists, reusing it"
fi

echo "==> Building the images (fast if Compose already built them)"
for name in $IMAGES; do
  docker build -q -t "retro-shop/$name:v1" "services/$name" >/dev/null
done
docker build -q -t retro-shop/web:v1 web >/dev/null

echo "==> Loading the images into the cluster"
for name in $IMAGES web; do
  kind load docker-image "retro-shop/$name:v1" --name "$CLUSTER"
done

echo "==> Applying k8s/"
kubectl apply -f k8s/00-namespace.yaml
kubectl create configmap db-init -n shop --from-file=init.sql=db/init.sql \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap nginx-gateway -n shop --from-file=gateway.conf=nginx/gateway.conf \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/

echo "==> Waiting for the pods"
kubectl rollout status statefulset/postgres -n shop --timeout=180s
for name in $IMAGES web nginx; do
  kubectl rollout status "deployment/$name" -n shop --timeout=180s
done

echo
kubectl get pods -n shop
echo
echo "The shop is running on Kubernetes: open port 8080."
