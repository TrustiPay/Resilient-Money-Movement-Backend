import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import engine
from app.models import Base
from app.routers import transactions, devices

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TrustiPay: creating database tables…")
    Base.metadata.create_all(bind=engine)
    logger.info("TrustiPay: ready ✓")
    yield
    logger.info("TrustiPay: shutting down…")


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="TrustiPay Central Ledger API",
    description="""
## TrustiPay Central Ledger Backend

TrustiPay is an **offline-first peer-to-peer digital payment prototype** where mobile devices 
exchange transactions offline and later synchronise with this central settlement server.

### Key capabilities

| Feature | Description |
|---|---|
| Transaction settlement | Full validation + fraud detection pipeline |
| Tamper-evident chain | SHA-256 hash chain for approved transactions |
| Double-spend prevention | Duplicate tx_id detection |
| Balance management | Atomic balance updates on settlement |
| Fraud detection | Configurable rule-based engine (stub) |
| Ledger sync | Mobile devices reconcile after reconnecting |
| Full ledger export | For external AI fraud & behaviour analytics |

### Signature note
For prototype testing use `"signature": "BYPASS"` to skip real cryptographic verification.

### Status codes

| Status | Meaning |
|---|---|
| `approved` | Settled and chain extended |
| `rejected` | Failed validation or hard fraud rule |
| `fraud_review` | Flagged for manual / ML review |
| `duplicate` | tx_id already exists in ledger |
""",
    version="1.0.0",
    contact={"name": "TrustiPay Research Team"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(transactions.router)
app.include_router(devices.router)


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({
        "service": "TrustiPay Central Ledger",
        "version": "1.0.0",
        "docs":    "/docs",
        "openapi": "/openapi.json",
    })


@app.get("/health", tags=["Health"])
def health():
    """Service health check."""
    return {"status": "ok", "service": "trustipay-ledger"}
