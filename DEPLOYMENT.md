# Local Kubernetes deployment

This guide deploys TalkFinder to Docker Desktop Kubernetes. Elasticsearch
remains in its existing Docker Compose container and volume. The app is
private to the cluster; use port-forwarding for local access.

## Prerequisites and current behavior

- Docker Desktop with Kubernetes enabled and `kubectl` using the
  `docker-desktop` context.
- Python 3.14 or newer and the project dependencies installed (the existing
  `.venv` works).
- Elasticsearch running from the existing Compose project on host port 9200.
- A local `.env` file. Its `OPENAI_API_KEY`, if present, is copied directly
  into a Kubernetes Secret by the deploy script; secret values are not printed
  or written to tracked files.

The current retriever uses index `talks`. It does not use `talks_dev`; both
indices existed locally during deployment preparation. The deployment does
not change either index or Elasticsearch data.

## Build the local image

From the repository root:

```sh
docker build -t talkfinder:local .
```

The image uses Python 3.14, runs as a non-root user, and starts Uvicorn on
`0.0.0.0:8000`. `.dockerignore` excludes `.env`, virtual environments, tests,
seed data, and local caches. The image is not pushed to a registry. It includes
the agenda dependencies (`builder.py`, `explain.py`, `models.py`, and
`scoring.py`) and the `static/` frontend as well as the earlier API files.

## Kubernetes configuration and deployment

Check the target context and the existing Elasticsearch container:

```sh
kubectl config current-context
docker compose ps
curl -fsS http://127.0.0.1:9200/
```

The context must be `docker-desktop`. The deployment script refuses to run
against another context. The ConfigMap uses `http://host.docker.internal:9200`
for host Elasticsearch; after rollout, the script verifies connectivity from
inside the TalkFinder Pod and checks the existing `talks` index.

Deploy in order (build an image with a unique commit/time-based local tag,
namespace, ConfigMap, Secret, Deployment, Service, wait for readiness, then
smoke-test Elasticsearch, the frontend, and API route registration):

```sh
PYTHON=.venv/bin/python ./scripts/deploy-k8s.sh
```

If dependencies are installed for a different Python, set `PYTHON` to that
interpreter. `scripts/apply_secret.py` reads only `OPENAI_API_KEY` from `.env`
and sends the generated Secret manifest to `kubectl` over standard input. It
does not print or persist the key. If the key is absent, BM25-only search can
still run; embeddings will be unavailable. Do not put credentials in the
ConfigMap or commit a Secret manifest.

The unique image tag prevents `IfNotPresent` from reusing a stale local image.
The Deployment uses a rolling update with `maxUnavailable: 0`, so the prior
Pod remains until the new Pod passes readiness. If rollback is needed:

```sh
kubectl rollout undo deployment/talkfinder -n talkfinder
kubectl rollout status deployment/talkfinder -n talkfinder
```

The automated agenda smoke check deliberately submits an empty topic list,
which should return HTTP 400 before embedding or OpenAI calls. It does not
validate the OpenAI key or make a billable request.

The image has `imagePullPolicy: IfNotPresent`, resource requests/limits, a
non-root/read-only-root-filesystem security context, and probes:

- `GET /livez` is an application-only liveness check.
- `GET /readyz` checks Elasticsearch and returns 503 when it is unavailable.
- Existing `GET /health` behavior and business endpoints are unchanged.

The Service is `ClusterIP`; no ingress, NodePort, or load balancer is created.
The deployment intentionally does not set OTLP/Dash0 variables yet.

## Access the app

Start a local port-forward (port 8001 avoids the usual local dev server on
8000):

```sh
kubectl port-forward -n talkfinder svc/talkfinder 8001:8000
```

In another terminal:

```sh
curl -i http://127.0.0.1:8001/livez
curl -i http://127.0.0.1:8001/readyz
curl -sS http://127.0.0.1:8001/talks
curl -sS http://127.0.0.1:8001/topics
```

Swagger UI is at `http://127.0.0.1:8001/docs`.

## Radar walkthrough

Confirm the context and open the already-running Radar UI at
`http://127.0.0.1:9280`. On this machine the Radar process is already serving
there; a second `kubectl radar` launch reports that port 9280 is occupied, so
reuse the existing UI instead of starting another instance:

```sh
kubectl config current-context
open http://127.0.0.1:9280
```

In Radar, select the `docker-desktop` context and filter to namespace
`talkfinder`. The namespace view should show this ownership chain:

`Service (selector app=talkfinder)` → `Pod (label app=talkfinder)` ←
`ReplicaSet` ← `Deployment`.

Select the namespace to inspect the Deployment, ReplicaSet, Pod, Service,
events, logs, and resource usage. The Service selects the Pod by label; the
Deployment owns the ReplicaSet; the ReplicaSet maintains the requested Pod
count. CLI alternatives:

```sh
kubectl get deployment,replicaset,pods,service -n talkfinder -o wide
kubectl describe deployment talkfinder -n talkfinder
kubectl describe pod -n talkfinder -l app=talkfinder
kubectl get events -n talkfinder --sort-by=.lastTimestamp
kubectl logs -n talkfinder deployment/talkfinder
kubectl top pod -n talkfinder
```

`kubectl top` requires Metrics Server data; Radar can also show resource
metrics when available in the cluster.

### Controlled image-pull failure demonstration

This creates a separate Pod and does not change TalkFinder or Elasticsearch.
Keep Radar open on namespace `talkfinder`, then create a Pod with an invalid
image:

```sh
kubectl run radar-image-failure -n talkfinder \
  --image=example.invalid/talkfinder-demo:missing \
  --restart=Never --command -- sleep 3600
kubectl get pod radar-image-failure -n talkfinder -w
```

In Radar, inspect that Pod and its events/logs. The expected diagnosis is an
image-pull error such as `ErrImagePull` followed by `ImagePullBackOff`; the
event should identify the invalid image/registry resolution. Correct just
this demo Pod and wait for it to become Ready:

```sh
kubectl set image pod/radar-image-failure -n talkfinder \
  radar-image-failure=busybox:1.36
kubectl wait --for=condition=Ready pod/radar-image-failure \
  -n talkfinder --timeout=120s
kubectl get pod radar-image-failure -n talkfinder
```

The cluster needs access to pull `busybox:1.36`. Delete the demonstration Pod
after observing the recovery:

```sh
kubectl delete pod radar-image-failure -n talkfinder
```

### Radar MCP and coding-agent connection

The installed Radar CLI is version 1.20.2. Its UI currently reports the MCP
server as live at `http://127.0.0.1:9280/mcp`. Clicking **Connect your agent**
in Radar displayed this exact VS Code (GitHub Copilot) workspace configuration
for `.vscode/mcp.json`:

```json
{
  "servers": {
    "radar": {
      "type": "http",
      "url": "http://127.0.0.1:9280/mcp"
    }
  }
}
```

Add it to `.vscode/mcp.json` (or use the current URL and snippet displayed in
Radar), then reload VS Code and accept the MCP server connection. This
workspace has not yet been configured with that file, and Copilot has not
connected; the live Radar MCP endpoint alone does not establish a client
connection. Keep Radar running while using the client. The endpoint is
loopback-only and may change if Radar is restarted with different settings.

Radar's connection dialog describes tools for cluster inspection and
investigation, and warns that write tools (such as restart, scale, apply, and
node drain) can modify the cluster. The installed CLI help offers
`-mcp-read-only`; use it when starting Radar if the agent should only inspect.
Avoid enabling opt-in execution tools unless needed.

## OpenAI and Dash0 verification

The Secret mounts `OPENAI_API_KEY` only when it is present in local `.env`.
The current HTTP routes do not expose an embedding-backed search operation,
so deployment can verify key presence without making a billable OpenAI API
request:

```sh
kubectl exec -n talkfinder deployment/talkfinder -- python -c \
  'import os; print("OPENAI_API_KEY configured:", bool(os.getenv("OPENAI_API_KEY")))'
```

This does not validate the key or confirm OpenAI service access. To validate
the credential, use an intentional application request that requires an
embedding after confirming the expected API cost.

Dash0 is not configured in Kubernetes by this deployment. The existing
`telemetry.py` already reads OTLP endpoint, protocol, headers, and dataset
from environment variables. Once ingestion settings are confirmed, provide
non-secret OTLP settings through a ConfigMap and authorization headers through
a Kubernetes Secret; do not add a second instrumentation layer.

## Troubleshooting

```sh
kubectl get pods -n talkfinder -o wide
kubectl describe pod -n talkfinder -l app=talkfinder
kubectl logs -n talkfinder deployment/talkfinder --all-containers
kubectl get events -n talkfinder --sort-by=.lastTimestamp
kubectl get configmap talkfinder-config -n talkfinder -o yaml
kubectl get secret talkfinder-secrets -n talkfinder
```

If readiness fails, check host Elasticsearch and Pod-to-host connectivity:

```sh
curl -fsS http://127.0.0.1:9200/
kubectl exec -n talkfinder deployment/talkfinder -- python -c \
  'import os; from elasticsearch import Elasticsearch; es=Elasticsearch(os.environ["ES_URL"]); print("reachable:", es.ping()); print("talks index:", es.indices.exists(index="talks"))'
```

Do not paste Secret output or `.env` contents into logs, tickets, or chat. If
`host.docker.internal` cannot be resolved/reached from a Pod, stop and inspect
the Docker Desktop host-gateway behavior before changing Elasticsearch or
Compose networking.

## Cleanup

Delete only the TalkFinder Kubernetes namespace; this removes its app,
ConfigMap, and Secret, but leaves the Compose Elasticsearch container and
volume untouched:

```sh
kubectl delete namespace talkfinder
```

The `talkfinder:local` image can be removed separately after no longer needed:

```sh
docker image rm talkfinder:local
```
