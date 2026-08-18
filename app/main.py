from fastapi import FastAPI

from app.config import settings
from app.routers import alert, auth, drone, mission, telemetry

app = FastAPI(
    title=settings.app_name,
    description="İHA filosu için telemetri toplama ve görev yönetim REST API'si.",
    version="0.1.0",
)


@app.get("/health", tags=["sistem"])
def health_check() -> dict:
    """Basit sağlık kontrolü uç noktası."""
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(drone.router)
app.include_router(mission.router)
app.include_router(telemetry.router)
app.include_router(alert.router)
