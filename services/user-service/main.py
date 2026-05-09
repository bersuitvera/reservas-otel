import os
from fastapi import FastAPI, HTTPException
from common.apm import setup_apm

SERVICE = os.getenv("SERVICE_NAME", "user-service")

app = FastAPI(title="User Service")
setup_apm(SERVICE, app)

USERS = {
    1: {"id": 1, "name": "Ana", "email": "ana@example.com"},
    2: {"id": 2, "name": "Luis", "email": "luis@example.com"},
    3: {"id": 3, "name": "Marta", "email": "marta@example.com"},
}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    """
    Obtiene la información pública de un usuario por su ID.
    """
    u = USERS.get(user_id)
    if not u:
        raise HTTPException(404, "not found")
    # No meter PII en atributos de trazas/logs en un lab realista
    return {"id": u["id"], "name": u["name"]}

@app.get("/health")
def health():
    return {"ok": True}
