# OpsTranslate Bot

Enterprise Telegram translation bot with an **Asymmetric Term-Policy Engine** (preventing sensitive operational/gaming terminology leaks), **Single-Pass Entity Protection** (preserving URLs, `@mentions`, numbers, and `/commands` verbatim), and a **Vue 3 Admin Control Center**.

---

## Key Features & Architecture

* **Dual Operational Scope**:
  * **Myanmar → English**: Strict policy engine with term masking, approved neutral rendering, and Layer 3 deny-scan with automatic repair and withhold guards.
  * **Global / English → Myanmar**: Relaxed, natural translation preserving tone without over-masking Burmese phrasing.
* **10-Gate Translation Pipeline**:
  * Gate 1: Webhook Secret Token authentication (`X-Telegram-Bot-Api-Secret-Token`).
  * Gate 2: Redis sliding-window idempotency (`update_id` deduplication).
  * Gate 3: Telegram message-type validation (plain text and captions only).
  * Gate 4: Phase 0 Group Gate (restricts private DM translation to verified members of the operations group).
  * Gate 5: Dynamic length cap validation (`MAX_INPUT_CHARS`, default 500 characters).
  * Gate 6: Language detection & automatic directional toggle (MY ↔ EN).
  * Gate 7: Duplicate request detection within 30 seconds.
  * Gate 8: User rate-limiting (sliding window: max 2 messages per 30 seconds) + daily soft cap.
  * Gate 9: Deterministic cache check (keyed by raw text, src, dst, and policy version).
  * Gate 10: Provider router with circuit breaker, timeout protection, and failover.
* **Security & Hardening**:
  * **Encrypted Credentials at Rest**: Third-party AI API keys in PostgreSQL are encrypted using Fernet (AES-128-CBC + HMAC-SHA256).
  * **Brute-Force Rate Limiter**: Admin login endpoint tracks failed attempts per IP (5 failures = 5-minute lockout with HTTP 429).
  * **Timed HMAC Sessions**: Admin session tokens use timestamped HMAC-SHA256 signatures with 7-day expiration.
  * **Privacy Compliance**: No message texts or translation bodies are ever logged; only metadata (`text_hash`, `char_len`, `provider`, `latency_ms`, `policy_hits`).
* **Operational Tooling**:
  * Dual-mode PostgreSQL backup & restore CLI (`scripts/backup_db.py`).
  * 60-second multi-worker provider synchronization in background watchdog.
  * Deterministic 40-case Policy Regression Suite ensuring translation safety.

---

## Telegram Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | Public / Gated | Shows welcome message, operational guidelines, and character limits. |
| `/help` | Public / Gated | Displays usage instructions, rate limits, and privacy guarantees. |
| `/whoami` | Public | Returns your Telegram User ID (exempt from group gate to allow onboarding). |
| `/status` | Admin only | Returns bot status, provider health, circuit breaker states, and uptime. |
| `/tr [text]` | Staff | Translates inline text or replies to a message to translate it. |
| `/report [reason]` | Staff | Replies to any translation to report an error (triggers a P3 Telegram admin alert). |

---

## Admin Control Center (`/admin`)

The bot serves a responsive Single-Page Application (Vue 3, Vite, Tailwind CSS, Naive UI) embedded at `/admin`:

1. **Overview**: Real-time telemetry, latency charts, provider states, and today's spend tracking.
2. **Providers**: Dynamic AI model management, priority routing, circuit breaker override, and connection testing.
3. **Policy & Term Glossary**: Inspect concept masking dictionaries, manage Layer 3 forbidden terms dynamically with regression validation, and run the 40-case regression suite.
4. **Audit Logs**: Real-time Server-Sent Events (SSE) log stream, date-time range picker, and provider filters.
5. **Staff / Users**: Manage Telegram user allowlist, assign roles (`admin` / `staff`), and set daily message caps.
6. **Playground**: Interactive sandbox to test asymmetric translations and entity preservation in real-time.

---

## Quick Start (Local Development)

### 1. Requirements
* Python 3.12+
* Node.js 18+ (for building the frontend)
* PostgreSQL (Optional - SQLite / in-memory fallback available)
* Redis (Optional - in-memory fallback available)

### 2. Installation
```bash
git clone https://github.com/RyanWez/OpsTranslate.git
cd OpsTranslate

# Python virtual environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend build (if modifying admin dashboard)
npm --prefix frontend install
npm --prefix frontend run build
```

### 3. Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

Key environment variables:
```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql://...  # REQUIRED: providers live in DB, managed via /admin Providers page
REDIS_URL=redis://...          # Optional: Redis connection string
MODE=polling                   # polling for local test, webhook for production
ADMIN_PASSWORD=strong_password # password for /admin dashboard
```

### 4. Database Setup & Seeding
```bash
# Run migrations
.venv/bin/alembic upgrade head

# Seed initial admin user and default policy
.venv/bin/python -m app.store.seed
```

### 5. Running the Application
```bash
# Start API and Bot in local polling mode
.venv/bin/python -m uvicorn app.main:app --port 8000 --reload
```
Access the Admin Dashboard at: `http://localhost:8000/admin`

---

## Testing & Quality Assurance

The codebase includes a comprehensive test suite (192+ automated tests) covering all gates, security features, and regression sets.

### Running Pytest

```bash
# Run the entire test suite with verbose output
.venv/bin/pytest -v

# Run the entire test suite quickly
.venv/bin/pytest -q

# Run specific functional test suites:
# 1. Pipeline & Gates 3-10
.venv/bin/pytest tests/test_pipeline.py -v

# 2. 40-case Policy Regression Suite
.venv/bin/pytest tests/test_regression_set.py -v

# 3. Admin API, Auth & Rate Limiting
.venv/bin/pytest tests/test_admin_api.py -v

# 4. Credential Encryption at Rest (Fernet AES)
.venv/bin/pytest tests/test_crypto.py -v

# 5. Database Backup CLI & Pruning
.venv/bin/pytest tests/test_backup.py -v

# 6. Telegram Handlers & /report Command
.venv/bin/pytest tests/test_handlers.py -v

# 7. Phase 0 Group Membership Gate
.venv/bin/pytest tests/test_groupgate.py -v

# 8. Rate Limiting & Countdown
.venv/bin/pytest tests/test_ratelimit.py -v
```

### Frontend Typecheck & Build Test
```bash
cd frontend
npm run build   # Runs vue-tsc --noEmit && vite build
```

### Live Environment Connectivity Check
```bash
.venv/bin/python scripts/live_check.py
```

---

## Database Backup & Maintenance (`scripts/backup_db.py`)

Automate backups for Neon Serverless or self-hosted PostgreSQL:

```bash
# Create a new compressed backup (.sql.gz with SHA-256 metadata)
.venv/bin/python scripts/backup_db.py --backup

# List all available backups
.venv/bin/python scripts/backup_db.py --list

# Clean up backups older than 7 days
.venv/bin/python scripts/backup_db.py --prune --keep-days 7

# Verify integrity of a specific backup file
.venv/bin/python scripts/backup_db.py --verify data/backups/backup_20260922_085728.sql.gz
```

---

## Production Deployment (Webhook Mode)

### 1. Docker / Koyeb Deployment
Build and run using the included `Dockerfile`:
```bash
docker build -t opstranslate-bot .
docker run -p 8000:8000 --env-file .env opstranslate-bot
```

### 2. Webhook Configuration
In production (`MODE=webhook`):
* Set `PUBLIC_URL=https://your-domain.com`
* Set `WEBHOOK_PATH_SECRET=random_secret_path`
* Set `WEBHOOK_SECRET=random_header_token`
* The bot registers its webhook on startup with Telegram and validates the `X-Telegram-Bot-Api-Secret-Token` header.

### 3. Monitoring & Dead-Man's Switch
Point an external monitoring service (BetterStack / UptimeRobot) at `/healthz`.
The `/healthz` endpoint verifies:
* Database connection status.
* Redis / cache availability.
* AI provider circuit breaker states.
* Policy engine load status.
