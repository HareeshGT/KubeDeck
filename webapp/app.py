"""KubeDeck Web — a lightweight mobile-friendly companion to the desktop
KubeDeck app.

The desktop app manages a cluster by SSHing into a box and running
`kubectl ... -o json` over that connection (see kubernetes_tab.py /
workers.py in the main repo). This does exactly the same thing, just
from a small HTTP API instead of a Qt UI, so it can be opened from a
phone browser instead of needing the desktop app installed.

Run it:

    pip install -r requirements.txt
    cp .env.example .env      # fill in your SSH + kubectl details
    uvicorn app:app --host 0.0.0.0 --port 8000

Then open http://<this-machine's-ip>:8000 on your phone (same Wi-Fi/
VPN, or behind a reverse proxy — see README.md for exposing it safely
over the internet).
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import threading
from pathlib import Path
from typing import Optional

import paramiko
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

load_dotenv()

APP_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------
# Config (all from environment / .env — see .env.example)
# --------------------------------------------------------------------
SSH_HOST = os.environ.get("SSH_HOST", "")
SSH_PORT = int(os.environ.get("SSH_PORT", "22"))
SSH_USER = os.environ.get("SSH_USER", "")
SSH_KEY_PATH = os.environ.get("SSH_KEY_PATH", "")
SSH_PASSWORD = os.environ.get("SSH_PASSWORD", "")
KUBECONTEXT = os.environ.get("KUBECONTEXT", "")  # optional: kubectl --context=

APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

if not SSH_HOST or not SSH_USER:
    raise RuntimeError(
        "SSH_HOST and SSH_USER must be set (see .env.example). "
        "This app has nothing to manage without them."
    )

if not APP_USERNAME or not APP_PASSWORD:
    raise RuntimeError(
        "APP_USERNAME and APP_PASSWORD must be set. This dashboard can "
        "delete pods and restart deployments — it must not be reachable "
        "without a login, especially if you expose it to the internet."
    )


# --------------------------------------------------------------------
# One persistent SSH connection, reconnected lazily if it drops.
# A phone dashboard is low-traffic (one person, occasional taps), so a
# single lock-guarded connection is simpler and plenty — no need for
# the desktop app's multi-connection pool.
# --------------------------------------------------------------------
class SSHSession:
    def __init__(self) -> None:
        self._client: Optional[paramiko.SSHClient] = None
        self._lock = threading.Lock()

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict = {
            "hostname": SSH_HOST,
            "port": SSH_PORT,
            "username": SSH_USER,
            "timeout": 10,
        }

        if SSH_KEY_PATH:
            kwargs["key_filename"] = SSH_KEY_PATH
        if SSH_PASSWORD:
            kwargs["password"] = SSH_PASSWORD
        if not SSH_KEY_PATH and not SSH_PASSWORD:
            kwargs["look_for_keys"] = True
            kwargs["allow_agent"] = True

        client.connect(**kwargs)
        return client

    def run(self, command: str, timeout: int = 30) -> tuple[int, str, str]:
        """Run one shell command over the SSH connection, reconnecting
        once if the existing connection turned out to be dead."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._client is None:
                        self._client = self._connect()

                    transport = self._client.get_transport()
                    if transport is None or not transport.is_active():
                        self._client = self._connect()

                    _stdin, stdout, stderr = self._client.exec_command(
                        command, timeout=timeout
                    )
                    exit_code = stdout.channel.recv_exit_status()
                    out = stdout.read().decode("utf-8", errors="replace")
                    err = stderr.read().decode("utf-8", errors="replace")
                    return exit_code, out, err
                except (paramiko.SSHException, OSError):
                    self._client = None
                    if attempt == 2:
                        raise
        raise RuntimeError("unreachable")  # pragma: no cover


ssh = SSHSession()


def run_kubectl(args: str, timeout: int = 30) -> dict | list:
    """Run `kubectl <args> -o json` on the remote box and return the
    parsed JSON. Raises HTTPException on any failure so route handlers
    stay simple."""
    context_flag = f"--context={shlex.quote(KUBECONTEXT)} " if KUBECONTEXT else ""
    command = f"kubectl {context_flag}{args}"

    try:
        exit_code, out, err = ssh.run(command, timeout=timeout)
    except (paramiko.SSHException, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"SSH connection failed: {exc}")

    if exit_code != 0:
        raise HTTPException(status_code=502, detail=err.strip() or "kubectl command failed")

    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="kubectl returned non-JSON output")


def run_kubectl_raw(args: str, timeout: int = 30) -> str:
    """Same as run_kubectl, but for commands with plain-text output
    (logs, rollout restart, delete, …) instead of `-o json`."""
    context_flag = f"--context={shlex.quote(KUBECONTEXT)} " if KUBECONTEXT else ""
    command = f"kubectl {context_flag}{args}"

    try:
        exit_code, out, err = ssh.run(command, timeout=timeout)
    except (paramiko.SSHException, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"SSH connection failed: {exc}")

    if exit_code != 0:
        raise HTTPException(status_code=502, detail=err.strip() or "kubectl command failed")

    return out


# --------------------------------------------------------------------
# Auth — HTTP Basic. Simple on purpose: this is a single-user personal
# dashboard, not a multi-tenant product. Put it behind HTTPS (see
# README.md) before using it outside a trusted network.
# --------------------------------------------------------------------
security = HTTPBasic()


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user_ok = secrets.compare_digest(credentials.username, APP_USERNAME)
    pass_ok = secrets.compare_digest(credentials.password, APP_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


app = FastAPI(title="KubeDeck Web")


# --------------------------------------------------------------------
# Helpers to shrink raw k8s API objects down to what the mobile UI
# actually shows — keeps payloads small on a phone connection.
# --------------------------------------------------------------------
def _pod_ready(status_obj: dict) -> str:
    statuses = status_obj.get("containerStatuses") or []
    ready = sum(1 for c in statuses if c.get("ready"))
    return f"{ready}/{len(statuses)}"


def _pod_restarts(status_obj: dict) -> int:
    statuses = status_obj.get("containerStatuses") or []
    return sum(c.get("restartCount", 0) for c in statuses)


def _shape_pod(item: dict) -> dict:
    meta = item.get("metadata", {})
    status_obj = item.get("status", {})
    spec = item.get("spec", {})
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "phase": status_obj.get("phase"),
        "ready": _pod_ready(status_obj),
        "restarts": _pod_restarts(status_obj),
        "node": spec.get("nodeName"),
        "containers": [c.get("name") for c in spec.get("containers", [])],
        "startTime": status_obj.get("startTime"),
    }


def _shape_deployment(item: dict) -> dict:
    meta = item.get("metadata", {})
    status_obj = item.get("status", {})
    spec = item.get("spec", {})
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "replicas": spec.get("replicas", 0),
        "ready": status_obj.get("readyReplicas", 0),
        "available": status_obj.get("availableReplicas", 0),
        "updated": status_obj.get("updatedReplicas", 0),
    }


def _shape_service(item: dict) -> dict:
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ports = [
        f"{p.get('port')}:{p.get('targetPort')}/{p.get('protocol', 'TCP')}"
        for p in spec.get("ports", [])
    ]
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "type": spec.get("type"),
        "clusterIP": spec.get("clusterIP"),
        "ports": ports,
    }


def _shape_node(item: dict) -> dict:
    meta = item.get("metadata", {})
    status_obj = item.get("status", {})
    conditions = {c.get("type"): c.get("status") for c in status_obj.get("conditions", [])}
    capacity = status_obj.get("capacity", {})
    return {
        "name": meta.get("name"),
        "ready": conditions.get("Ready") == "True",
        "cpu": capacity.get("cpu"),
        "memory": capacity.get("memory"),
        "version": status_obj.get("nodeInfo", {}).get("kubeletVersion"),
    }


def _shape_event(item: dict) -> dict:
    involved = item.get("involvedObject", {})
    return {
        "type": item.get("type"),
        "reason": item.get("reason"),
        "message": item.get("message"),
        "object": f"{involved.get('kind', '')}/{involved.get('name', '')}",
        "namespace": item.get("metadata", {}).get("namespace"),
        "lastTimestamp": item.get("lastTimestamp") or item.get("eventTime"),
        "count": item.get("count", 1),
    }


NS_QUERY = "-A"


def _ns_flag(namespace: Optional[str]) -> str:
    if namespace and namespace != "all":
        return f"-n {shlex.quote(namespace)}"
    return NS_QUERY


# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------
@app.get("/api/health")
def health(_: None = Depends(require_login)) -> dict:
    exit_code, _out, _err = ssh.run("kubectl version --client=true -o json 2>&1", timeout=10)
    return {"ssh_ok": exit_code == 0, "host": SSH_HOST}


@app.get("/api/namespaces")
def list_namespaces(_: None = Depends(require_login)) -> list:
    data = run_kubectl("get namespaces -o json")
    return [item["metadata"]["name"] for item in data.get("items", [])]


@app.get("/api/pods")
def list_pods(namespace: Optional[str] = None, _: None = Depends(require_login)) -> list:
    data = run_kubectl(f"get pods {_ns_flag(namespace)} -o json")
    return [_shape_pod(item) for item in data.get("items", [])]


@app.get("/api/deployments")
def list_deployments(namespace: Optional[str] = None, _: None = Depends(require_login)) -> list:
    data = run_kubectl(f"get deployments {_ns_flag(namespace)} -o json")
    return [_shape_deployment(item) for item in data.get("items", [])]


@app.get("/api/services")
def list_services(namespace: Optional[str] = None, _: None = Depends(require_login)) -> list:
    data = run_kubectl(f"get services {_ns_flag(namespace)} -o json")
    return [_shape_service(item) for item in data.get("items", [])]


@app.get("/api/nodes")
def list_nodes(_: None = Depends(require_login)) -> list:
    data = run_kubectl("get nodes -o json")
    return [_shape_node(item) for item in data.get("items", [])]


@app.get("/api/events")
def list_events(namespace: Optional[str] = None, _: None = Depends(require_login)) -> list:
    data = run_kubectl(f"get events {_ns_flag(namespace)} --sort-by=.lastTimestamp -o json")
    events = [_shape_event(item) for item in data.get("items", [])]
    return list(reversed(events))[:100]


@app.get("/api/logs/{namespace}/{pod}")
def pod_logs(
    namespace: str,
    pod: str,
    container: Optional[str] = None,
    tail: int = 200,
    _: None = Depends(require_login),
) -> dict:
    tail = max(1, min(tail, 2000))
    container_flag = f"-c {shlex.quote(container)} " if container else ""
    out = run_kubectl_raw(
        f"logs {shlex.quote(pod)} -n {shlex.quote(namespace)} {container_flag}--tail={tail} 2>&1",
        timeout=20,
    )
    return {"logs": out}


class ScaleRequest(BaseModel):
    replicas: int


@app.post("/api/deployments/{namespace}/{name}/restart")
def restart_deployment(namespace: str, name: str, _: None = Depends(require_login)) -> dict:
    out = run_kubectl_raw(
        f"rollout restart deployment/{shlex.quote(name)} -n {shlex.quote(namespace)} 2>&1"
    )
    return {"ok": True, "output": out.strip()}


@app.post("/api/deployments/{namespace}/{name}/scale")
def scale_deployment(
    namespace: str, name: str, body: ScaleRequest, _: None = Depends(require_login)
) -> dict:
    if body.replicas < 0 or body.replicas > 100:
        raise HTTPException(status_code=400, detail="replicas must be between 0 and 100")
    out = run_kubectl_raw(
        f"scale deployment/{shlex.quote(name)} -n {shlex.quote(namespace)} "
        f"--replicas={body.replicas} 2>&1"
    )
    return {"ok": True, "output": out.strip()}


@app.post("/api/pods/{namespace}/{name}/delete")
def delete_pod(namespace: str, name: str, _: None = Depends(require_login)) -> dict:
    out = run_kubectl_raw(f"delete pod {shlex.quote(name)} -n {shlex.quote(namespace)} 2>&1")
    return {"ok": True, "output": out.strip()}


# --------------------------------------------------------------------
# Static mobile UI — a single self-contained page (see static/index.html)
# --------------------------------------------------------------------
@app.get("/")
def index(_: None = Depends(require_login)) -> FileResponse:
    return FileResponse(str(APP_DIR / "static" / "index.html"))
