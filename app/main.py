import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine
from app.models import Base
from app.routers import devices, transactions
from app.services.queue_processor_service import run_queue_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TrustiPay: creating database tables...")
    Base.metadata.create_all(bind=engine)

    stop_event = asyncio.Event()
    worker_task = None

    if settings.ENABLE_QUEUE_WORKER:
        worker_task = asyncio.create_task(run_queue_worker(stop_event))
        logger.info("TrustiPay: queue worker enabled")
    else:
        logger.warning("TrustiPay: queue worker disabled by ENABLE_QUEUE_WORKER=false")

    app.state.queue_worker_stop_event = stop_event
    app.state.queue_worker_task = worker_task

    logger.info("TrustiPay: ready")
    try:
        yield
    finally:
        if worker_task:
            stop_event.set()
            await worker_task
        logger.info("TrustiPay: shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="""
## TrustiPay Central Ledger Backend (Fraud Callback Mode)

TrustiPay is an offline-first peer-to-peer payment prototype where mobile clients submit transactions
online or sync offline batches, and the central ledger processes them asynchronously.

### Processing lifecycle
1. Mobile submits to `/v1/transactions/online` or `/v1/transactions/offline-sync`.
2. Online items are written to central ledger with status `queued`.
3. Background worker processes queue one-by-one.
4. Offline items are validated (hash/signature/double-spend/duplicate/balance).
5. Worker dispatches eligible items to external fraud component.
6. Fraud component posts final decision to `/v1/transactions/fraud-callback`.
7. Callback finalizes ledger and device history updates.

### Public statuses
- `queued`
- `processing`
- `retry_balance`
- `fraud_detection_pending`
- `security_review`
- `approved`
- `rejected`
- `duplicate`

### Eventual consistency
Enqueue endpoints return immediately. Settlement is asynchronous.
Clients must poll transaction status for the final decision.
""",
    version=settings.APP_VERSION,
    contact={"name": "TrustiPay Research Team"},
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router)
app.include_router(devices.router)


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse(
        {
            "service": "TrustiPay Central Ledger",
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }
    )


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": "trustipay-ledger",
        "queue_worker_enabled": settings.ENABLE_QUEUE_WORKER,
        "fraud_endpoint_configured": bool(settings.FRAUD_ENDPOINT_URL),
    }
