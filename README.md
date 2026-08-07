# Fintrack-Ai
FinTrack AI is a FastAPI application with one responsive HTML/CSS/JavaScript chatbot frontend. Every signup, login, profile, goal, saving-history, analytics, and logout step happens inside the chat window.

The composer also accepts ordinary typed questions. Until an LLM is integrated, free-text questions receive a safe fixed response while all guided financial flows remain fully operational.

There is no Flask, Jinja runtime, Streamlit, OpenAI API, LLM, or natural-language classifier.

Architecture
Browser
  └── FastAPI-served chatbot (frontend/index.html + app.css + app.js)
        └── Same-origin JSON calls to /api/*
              ├── persistent OTP and bearer authentication
              ├── income and expense profiles
              ├── goals and monthly saving history
              ├── recommendation engine
              └── analytics
                    └── SQLite fintrackai.db
See structure.md for the complete UI state machine, API contracts, database writes, and calculation flow.

Setup
Python 3.11 or newer is recommended.

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
Load the local environment:

set -a
source .env
set +a
Required for authenticated sessions and real OTP delivery:

FINTRACK_SECRET_KEY
BREVO_API_KEY
BREVO_SENDER_EMAIL
BREVO_SENDER_EMAIL must be an active sender in the configured Brevo account. FINTRACK_DB_PATH is optional and defaults to the repository's fintrackai.db through a path based on db.py.

Run
Only one server is required:

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
Open:

Chatbot: http://localhost:8000
API docs: http://localhost:8000/docs
Health: http://localhost:8000/api/health
Chatbot behavior
Unauthenticated options:

Log in
Create an account and verify OTP
Authenticated menu:

Income profile
Expense profile
Goals and savings
Financial analytics
Logout
All multi-field writes show a summary and require explicit confirmation. Forms, results, warnings, progress tables, and CSS charts are rendered inside the compact assistant chat panel. The surrounding white-and-orange page explains FinTrack AI but never displays account data or moves financial actions outside the chatbot.

Any ordinary composer message receives the current placeholder:

Thanks for your question. General AI responses are coming soon. For now, I can record the query and keep guiding you through the available FinTrack actions.

The composer remains visible during every guided step. Ordinary questions and their fixed responses appear after the current step, so the response is immediately visible without resetting form values. The handler is isolated so a future LLM endpoint can replace the fixed response without changing the guided state machine.

Database and security
Existing records in fintrackai.db are preserved.
Additive migrations create persistent PENDING_SIGNUP, AUTH_SESSION, and migration metadata.
Pending passwords and OTPs are hashed; no plaintext OTP is stored.
Raw bearer tokens are held only in the browser tab's sessionStorage; SQLite stores a keyed hash.
Protected endpoints derive ownership from the bearer session and never accept an email/user ID for financial operations.
All value SQL is parameterized.
Foreign keys and a busy timeout are enabled on every application connection.
Legacy case-insensitive duplicate emails return a safe conflict instead of being merged.
The browser never displays raw database or stack-trace errors.
The pre-migration database backup is stored at:

backups/fintrackai-pre-fastapi-20260806T044635Z.db
backups/ and .env are gitignored.

Tests
Tests use isolated temporary SQLite files and mocked Brevo delivery. They do not modify real records or send email.

node --check frontend/app.js
python3 -m compileall -q app.py db.py errors.py recommendation.py schemas.py services tests
python3 -m pytest -q
Coverage includes authentication persistence, OTP expiry/attempts, legacy Werkzeug hashes, ownership, profile CRUD, goal recommendations, saving history, analytics scoping, static frontend delivery, responsive chatbot assets, free-query placeholder behavior, and removal of the unsafe /users endpoint.
