#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON:-python3}"
if [[ -z "${PYTHON:-}" && -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi

context="$(kubectl config current-context)"
if [[ "$context" != "docker-desktop" ]]; then
  echo "Refusing deployment: expected context docker-desktop, got: $context" >&2
  exit 1
fi

image_tag="local-$(git rev-parse --short=12 HEAD)-$(date +%Y%m%d%H%M%S)"
image="talkfinder:${image_tag}"
docker build -t "$image" .
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
"$PYTHON_BIN" scripts/apply_secret.py
sed "s|image: talkfinder:local$|image: ${image}|" k8s/deployment.yaml \
  | kubectl apply -f -
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/talkfinder -n talkfinder --timeout=180s

echo
kubectl get deployment,replicaset,pods,service -n talkfinder -o wide
echo
echo "Deployed image: ${image}"

echo
echo "Checking Elasticsearch connectivity and the existing talks index:"
kubectl exec -n talkfinder deployment/talkfinder -- python -c '
import os
from elasticsearch import Elasticsearch

es = Elasticsearch(os.environ["ES_URL"])
connected = es.ping()
index_exists = es.indices.exists(index="talks") if connected else False
print(f"Elasticsearch reachable: {connected}")
print(f"Existing talks index available: {index_exists}")
if not connected or not index_exists:
    raise SystemExit(1)
'

echo
echo "Checking frontend and application routes (without making an OpenAI request):"
kubectl exec -n talkfinder deployment/talkfinder -- python -c '
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8000"
with urlopen(base + "/openapi.json", timeout=5) as response:
    paths = json.load(response)["paths"]
required = {"/agenda", "/talks", "/topics", "/health", "/livez", "/readyz"}
missing = required - paths.keys()
if missing:
    raise SystemExit(f"Missing API paths: {sorted(missing)}")
with urlopen(base + "/", timeout=5) as response:
    if response.status != 200 or "text/html" not in response.headers["Content-Type"]:
        raise SystemExit("Frontend root did not return HTML")
request = Request(
    base + "/agenda",
    data=b"{\"topics\": []}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    urlopen(request, timeout=5)
except HTTPError as error:
    if error.code != 400:
        raise
else:
    raise SystemExit("Empty agenda smoke request unexpectedly succeeded")
print("Frontend served; all expected routes registered; agenda validation returned HTTP 400.")
'
