"""FastAPI entrypoint. Routers are added per milestone; /health is the compose smoke test."""

from fastapi import FastAPI

from engine import config

app = FastAPI(title="Algo Trading Mentor engine", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "provider": config.DATA_PROVIDER, "sim_now": None}
