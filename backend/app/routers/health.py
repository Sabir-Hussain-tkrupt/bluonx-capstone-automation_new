"""Health check endpoint. No authentication required."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "bluonx-api", "version": "0.1.0"}
