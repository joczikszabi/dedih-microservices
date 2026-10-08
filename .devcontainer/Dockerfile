# The image this dev container is built from. Not Codespaces specific: the same
# definition runs under VS Code, the devcontainer CLI and JetBrains.

FROM mcr.microsoft.com/devcontainers/base:bookworm

# Pinned rather than "latest", so everyone gets the same versions regardless of
# when they opened their Codespace. Both checked to exist on 2026-10-08.
ARG KIND_VERSION=v0.33.0
ARG ISTIO_VERSION=1.31.1

# jq makes the JSON answers of the API readable in the terminal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

# kind runs a Kubernetes cluster inside Docker. Used from block 3.
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}" \
    && install -m 0755 /tmp/kind /usr/local/bin/kind \
    && rm -f /tmp/kind

# istioctl installs and inspects the service mesh. Used from the end of block 3.
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/istioctl.tar.gz \
       "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istioctl-${ISTIO_VERSION}-linux-${ARCH}.tar.gz" \
    && tar -xzf /tmp/istioctl.tar.gz -C /tmp istioctl \
    && install -m 0755 /tmp/istioctl /usr/local/bin/istioctl \
    && rm -f /tmp/istioctl.tar.gz /tmp/istioctl

# kubectl and helm come from a devcontainer feature instead, see
# devcontainer.json.
