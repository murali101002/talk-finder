"""Create/update the Kubernetes Secret from OPENAI_API_KEY in local .env."""

import base64
import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
secret_value = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY", "")
data = {}
if secret_value:
    data["OPENAI_API_KEY"] = base64.b64encode(secret_value.encode()).decode()

manifest = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {"name": "talkfinder-secrets", "namespace": "talkfinder"},
    "type": "Opaque",
    "data": data,
}

subprocess.run(
    ["kubectl", "apply", "-f", "-"],
    input=json.dumps(manifest),
    text=True,
    check=True,
)
