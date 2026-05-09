import os, httpx
from fastapi import FastAPI, HTTPException
from common.apm import setup_apm
from common.logger import log

app = FastAPI(title="API Gateway - Library Rooms")
SERVICE = os.getenv("SERVICE_NAME", "api-gateway")
setup_apm(SERVICE, app)

ROOM = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")
RES = os.getenv("RESERVATION_SERVICE_URL", "http://reservation-service:8000")
USR = os.getenv("USER_SERVICE_URL", "http://user-service:8000")

client = httpx.AsyncClient(timeout=5.0)

@app.get("/rooms")
async def rooms(date: str | None = None, capacity: int | None = None):
    r = await client.get(f"{ROOM}/rooms", params={"date": date, "capacity": capacity})
    return r.json()

@app.get("/availability")
async def availability(room_id: int, start: str, end: str):
    r = await client.get(f"{RES}/availability", params={"room_id": room_id, "start": start, "end": end})
    return r.json()

@app.post("/reservations")
async def create_reservation(payload: dict):
    # Validate user exists (adds dependency + traces)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(400, "user_id required")
    ur = await client.get(f"{USR}/users/{user_id}")
    if ur.status_code != 200:
        raise HTTPException(400, "user not found")

    rr = await client.post(f"{RES}/reservations", json=payload)
    if rr.status_code >= 400:
        log("warn", "reservation failed", status=rr.status_code, body=rr.text)
        raise HTTPException(rr.status_code, rr.text)
    return rr.json()

@app.get("/health")
async def health():
    return {"ok": True}
