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
