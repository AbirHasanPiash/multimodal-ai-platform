from fastapi import FastAPI
from app.api.v1.endpoints import auth
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])

@app.get("/")
def read_root():
    return {"message": "AI Platform Backend Running"}