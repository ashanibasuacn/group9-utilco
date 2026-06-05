"""
Utilico Energy — Billing Reconciliation Agent
FastAPI application entry point.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database.connection import close_database, get_database, ping_database
from database.seed import seed_all
from api.routes.csr import router as csr_router
from api.routes.dri import router as dri_router
from api.routes.analyst_manager import router as analyst_manager_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await ping_database()

    db = get_database()
    account_count = await db["accounts"].count_documents({})
    if account_count == 0:
        print("[STARTUP] No accounts found — seeding database...")
        await seed_all(db)
    else:
        print(f"[STARTUP] Database already seeded ({account_count} accounts found)")

    yield

    # Shutdown
    await close_database()


app = FastAPI(
    title="Utilico Energy — Billing Reconciliation Agent",
    version="1.0.0",
    description=(
        "AI-powered billing reconciliation pipeline for Utilico Energy. "
        "Detects post-disconnect billing conflicts across CC&B, MDM, OMS, CRM, and GL systems."
    ),
    lifespan=lifespan,
)

# Include routers
app.include_router(csr_router)
app.include_router(dri_router)
app.include_router(analyst_manager_router)

# Serve the frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
async def frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok"}


@app.get("/seed", tags=["System"])
async def force_reseed() -> dict:
    """Force reseed of the database with fresh mock data."""
    db = get_database()
    await seed_all(db)
    return {"seeded": True, "message": "Database reseeded with 3 test accounts and 10 collections"}


@app.get("/data/{collection}", tags=["System"])
async def browse_collection(collection: str, limit: int = 10) -> list:
    """Browse any seeded collection. Useful for inspecting in-memory mock data."""
    allowed = {
        "accounts", "ccb_stubs", "mdm_stubs", "oms_stubs", "crm_stubs",
        "gl_stubs", "users", "escalations", "audit_trail", "analyst_executions",
    }
    if collection not in allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown collection. Choose from: {sorted(allowed)}")
    db = get_database()
    docs = await db[collection].find({}, {"_id": 0}).to_list(length=limit)
    return docs


@app.get("/data", tags=["System"])
async def collection_counts() -> dict:
    """Return document counts across all 10 collections."""
    db = get_database()
    collections = [
        "accounts", "ccb_stubs", "mdm_stubs", "oms_stubs", "crm_stubs",
        "gl_stubs", "users", "escalations", "audit_trail", "analyst_executions",
    ]
    return {col: await db[col].count_documents({}) for col in collections}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
