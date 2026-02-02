from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import auth, users, chat, media, packages, payments, admin_stats, manage_user
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

origins = [
    "https://multiaimodel.com",
    "https://www.multiaimodel.com",
    "https://multimodal-ai-five.vercel.app",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:5173",
]

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(chat.router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])
app.include_router(media.router, prefix=f"{settings.API_V1_STR}/media", tags=["media"])
app.include_router(packages.router, prefix=f"{settings.API_V1_STR}/packages", tags=["packages"])
app.include_router(payments.router, prefix=f"{settings.API_V1_STR}/payments", tags=["payments"])
app.include_router(admin_stats.router, prefix=f"{settings.API_V1_STR}/admin/stats", tags=["admin_stats"])
app.include_router(manage_user.router, prefix=f"{settings.API_V1_STR}/admin/users", tags=["admin_manage_users"])

@app.get("/")
def read_root():
    return {"message": "AI Platform Backend Running"}