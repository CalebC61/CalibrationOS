"""CalibrationOS backend — FastAPI bootstrap.

All endpoints live in `routers/*.py`. Shared infrastructure (DB, auth,
helpers, integrations) lives in `deps.py`. Pydantic models live in `models.py`.
"""
import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import terms_service
from deps import client, load_settings
from routers import auth as auth_router
from routers import billing as billing_router
from routers import field as field_router
from routers import jobs as jobs_router
from routers import owner as owner_router
from routers import portal as portal_router
from routers import shops as shops_router
from routers import xero as xero_router
from seed import seed_data

app = FastAPI(title="CalibrationOS", version="1.0.0")
api = APIRouter(prefix="/api")

# Order matters when multiple routers define overlapping path prefixes:
# (FastAPI matches first include). Most-specific routers go first.
api.include_router(field_router.router)
api.include_router(billing_router.router)
api.include_router(xero_router.router)
api.include_router(portal_router.router)
api.include_router(owner_router.router)
api.include_router(jobs_router.router)
api.include_router(shops_router.router)
api.include_router(auth_router.router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    from deps import db
    await seed_data()
    await load_settings()
    await terms_service.ensure_terms_seeded(db)


@app.on_event("shutdown")
async def shutdown():
    client.close()
