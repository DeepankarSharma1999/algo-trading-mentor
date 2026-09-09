"""Engine configuration. Everything comes from the environment with local defaults."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://atm:atm@localhost:55432/atm")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "synthetic")
DATA_DIR = Path(os.getenv("DATA_DIR", str(REPO / "data")))
SCHEMA_DIR = Path(os.getenv("SCHEMA_DIR", str(REPO / "packages" / "schema")))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
PAPER_SPEED = int(os.getenv("PAPER_SPEED", "2"))

# SQLAlchemy wants the psycopg3 driver name.
SQLALCHEMY_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
