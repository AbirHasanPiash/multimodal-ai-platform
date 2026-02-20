# 🚀 MultiAIModel Backend

Backend service for **MultiAIModel** — a multi-modal AI platform that integrates multiple AI providers (OpenAI, Gemini, Claude, Google TTS, D-ID) into a unified wallet-based system.

Built with **FastAPI**, **PostgreSQL**, **Redis**, and **Celery**, this backend powers real-time AI chat, media generation, payments, and admin analytics.

---

## 📌 Overview

MultiAIModel Backend provides:

- 🔐 Secure Authentication (JWT + OAuth2)
- 💬 Real-time AI Chat (WebSockets + Streaming)
- 🧠 Multi-LLM Routing (Auto model selection)
- 🖼 Image Generation (OpenAI)
- 🔊 Text-to-Speech (Google Cloud)
- 🎥 AI Avatar Video Generation (D-ID)
- 💳 Stripe Payment Integration
- 🏦 Wallet & Credit System
- 📊 Admin Dashboard APIs
- ⚡ Background Task Processing (Celery)
- ☁️ Cloud Storage (Cloudflare R2 / S3 Compatible)

---

# 🏗 Architecture

The backend follows a **Service-Oriented Architecture (SOA)** pattern with clean separation of concerns.
```bash
app/
├── api/ # REST & WebSocket endpoints
├── core/ # Configuration, DB, Redis, Security
├── models/ # SQLAlchemy ORM models
├── schemas/ # Pydantic validation schemas
├── services/ # Business logic & AI integrations
├── workers/ # Celery background tasks
└── main.py # Application entry point
alembic/ # Database migrations
```

---

# 🛠 Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy (Async) |
| Cache / Broker | Redis |
| Background Jobs | Celery |
| Migrations | Alembic |
| Payments | Stripe |
| Storage | Cloudflare R2 (S3 Compatible) |
| AI Providers | OpenAI, Gemini, Claude |
| TTS | Google Cloud |
| Avatar Video | D-ID |

---

# ⚙️ Environment Setup

## 1️⃣ Clone Repository

```bash
git clone https://github.com/your-username/multiaimodel-backend.git
cd multiaimodel-backend
```
## 2️⃣ Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
```
## 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```
## 4️⃣ Environment Variables
```bash
Create a .env file in the root directory:

# App
PROJECT_NAME="Multi-Model-AI"
API_V1_STR="/api/v1"

# Security
SECRET_KEY=""
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Database (Supabase)
DATABASE_URL="postgresql+asyncpg:<your database url>ssl=require"

# Redis (Local Docker)
REDIS_URL="redis://localhost:6379/0"

GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""

# API keys for AI models
OPENAI_API_KEY=""
ANTHROPIC_API_KEY=""
GOOGLE_API_KEY=""
DID_API_KEY=""

GOOGLE_APPLICATION_CREDENTIALS=google_credentials.json

# R2 Configuration
STORAGE_ENDPOINT=
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=
STORAGE_BUCKET_NAME=multimodal-media
STORAGE_REGION=auto
# The public URL to access files in the bucket
STORAGE_PUBLIC_URL=

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

FRONTEND_URL="http://localhost:5173"
```
## 🗄 Database Setup
Initialize Migrations
alembic upgrade head
Create New Migration
alembic revision --autogenerate -m "Description of change"
## ▶️ Running the Application
Start FastAPI Server:

uvicorn app.main:app --reload

Server will run at: http://localhost:8000
Swagger Documentation: http://localhost:8000/docs

## ⚡ Running Background Workers
Start Redis first.

Then run:
celery -A app.workers.celery_app worker --loglevel=info

## 🔐 Authentication Flow
- JWT-based authentication
- OAuth2 Bearer tokens
- Password hashing using secure algorithms
- WebSocket token verification
- Role-based access (Admin / User)

## 💬 Real-Time Chat System
- WebSocket streaming
- Context stored temporarily in Redis
- Persistent chat history in PostgreSQL
- Atomic billing after completion
- Multi-provider routing (Auto mode)

## 🧠 Multi-LLM Router
The system automatically selects the best model based on prompt type:

- Coding -> Claude
- Large Context ->	Gemini
- Logical Reasoning ->	GPT
- Creative Writing ->	Gemini
## 🖼 Media Generation
- Image Generation -> OpenAI Image APIs

- Uploaded to Cloudflare R2 -> Permanent storage URLs

- Text-to-Speech -> Google Cloud TTS

- Audio stored in R2

- Avatar Video -> D-ID Integration

- Multi-step async workflow

- Polling-based completion

- Final video stored in R2

## 💳 Stripe Payment Workflow
User selects package

Backend creates Stripe Checkout Session

Stripe webhook confirms payment

Wallet credits updated atomically

Transaction stored in database

## 🏦 Wallet & Credits System
Precise decimal-based accounting

Atomic transactions

Automatic credit deduction

Profit margin calculation per token

## 👨‍💼 Admin Features
Revenue analytics

User management

Package management

Credit adjustments

Usage statistics

## 🧵 Background Task Architecture
FastAPI → Redis → Celery Worker

Heavy tasks:

Image generation

Video rendering

Media processing

Polling long-running jobs

Ensures:

Non-blocking API

High scalability

Fault tolerance

## 📦 Deployment Notes
Recommended stack:

Backend: Docker + Render / AWS / DigitalOcean

Database: Managed PostgreSQL

Cache: Managed Redis

Storage: Cloudflare R2

SSL: Reverse Proxy (NGINX or Platform Provided)

# Always configure:

Secure CORS origins

HTTPS only

Proper webhook verification

Strong SECRET_KEY

## 🧪 Health Check
GET /
Response:

{
  "message": "AI Platform Backend Running"
}

## 📄 License
This project is proprietary software.

All rights reserved © MultiAIModel.
