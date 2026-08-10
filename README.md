# JustSpeak (ஒன்று பேசு)

> Voice-first Tamil digital literacy agent for old-age pension applications.  
> Zero reading or typing required — end-to-end voice only.

---

## Setup

### 1. Get your API Keys

| Service | URL | What to copy |
|---|---|---|
| Gemini | [aistudio.google.com](https://aistudio.google.com) | API Key |
| Supabase | [supabase.com](https://supabase.com) → Settings → API | Project URL + anon key |

### 2. Supabase Database Setup

1. Create a new project on Supabase
2. Go to **SQL Editor** → **New Query**
3. Paste the contents of `backend/supabase_schema.sql` and click **Run**

### 3. Backend Setup

```bash
cd backend
cp .env.example .env
# Edit .env with your GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY

pip install -r requirements.txt
uvicorn main:app --reload
# Backend runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 4. Frontend Setup

```bash
cd frontend
# .env already has VITE_API_URL=http://localhost:8000
npm install
npm run dev
# Frontend runs at http://localhost:5173
```

### 5. Run Tests

```bash
cd backend
python tests/test_mishear_fixtures.py
```

---

## Architecture

```
Browser (React/Vite)
  │  MediaRecorder → audio/webm blob
  ↓
FastAPI Backend
  │  State Machine: GREETING → INTENT_CAPTURE → SLOT_FILLING → CONFIRMATION → SUBMIT
  │  Gemini API (single call): STT + slot extraction → JSON + confidence
  │  Gemini TTS: Tamil speech synthesis
  ↓
Supabase (session state + submissions)
```

## State Machine

```
GREETING         → welcome in Tamil
INTENT_CAPTURE   → confirm pension application intent
SLOT_FILLING     → collect 8 fields, one at a time (with mishear recovery)
CONFIRMATION     → full readback, voice correction loop
SUBMIT           → write to Supabase, speak reference number
```

## Mishear Recovery

- Confidence `low` → re-ask same question
- 2 failed attempts → offer graceful skip
- Validation failure (e.g. age < 60) → spoken explanation + re-ask
- Never silent failure — always spoken response

## Debug Panel

Press **Ctrl+D** on the frontend to toggle the judges debug panel.  
Shows: session state, current slot, transcripts, confidence scores, all collected values.

---

## Deployment

### Backend → Render
1. Connect your GitHub repo to [render.com](https://render.com)
2. Create **New Web Service** → select the `backend/` directory
3. Set env vars: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `FRONTEND_ORIGIN`
4. Deploy — Render uses `render.yaml` automatically

### Frontend → Vercel
1. Import your repo at [vercel.com](https://vercel.com)
2. Set root directory to `frontend/`
3. Set env var: `VITE_API_URL=https://your-render-url.onrender.com`
4. Deploy — Vercel uses `vercel.json` automatically
