# STI-EPI-FORECAST API Setup

This creates your own AI API backend (Cursor-style), which your dashboard and mobile app can call.

## 1) Environment variables

In `.env` set:

```env
AI_API_KEY=your_key
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
```

Notes:
- `XAI_API_KEY` is also supported as a fallback key name.
- Keep keys private and never commit `.env`.

## 2) Start the API server

From project root:

```bash
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

Open docs:
- `http://localhost:8000/docs`

## 3) Endpoints

- `GET /health`
- `POST /v1/nlp-alerts`
- `POST /v1/forecast/seir`

## 4) Example request (NLP alerts)

```bash
curl -X POST http://localhost:8000/v1/nlp-alerts ^
  -H "Content-Type: application/json" ^
  -d "{\"disease\":\"Cholera\",\"news_mentions\":1800,\"cholera_cases\":42000,\"affected_countries\":24}"
```

## 5) Example request (SEIR forecast)

```bash
curl -X POST http://localhost:8000/v1/forecast/seir ^
  -H "Content-Type: application/json" ^
  -d "{\"disease\":\"Marburg\",\"population\":48000000,\"initial_infected\":15000,\"days\":100,\"intervention_effectiveness\":0.35}"
```
