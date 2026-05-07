# Pathogen Economy Epiforecast Mobile (Expo Go)

## Run locally

1. Install Node.js LTS.
2. Install dependencies:
   - `npm install`
3. Start Expo (recommended — avoids port **8081** clashes with other Metro/React Native apps):
   - `npm run start:expo`
4. **QR code**: it is printed in that same terminal (ASCII QR). Open **Expo Go** on your phone and tap **Scan QR code**.

### If you do not see a QR code

- Do **not** set `CI=1` when starting Expo — that skips prompts but can also skip starting the dev server if a port conflict needs confirmation.
- If something already uses **8081**, keep using `npm run start:expo` (uses **8082**).
- If you are on a different Wi‑Fi than your PC, use tunnel mode instead:
  - `npm run start:expo:tunnel` (first run may install `@expo/ngrok`).

## What this prototype includes

- Disease selector (Cholera, Malaria, Typhoid, Marburg)
- Simulated global NLP alerts
- Travel risk bars (Entebbe, Malaba, Mpondwe, Elegu)
- SEIR-style 100-day projection snapshot
- Dynamic Uganda action plan (Buy / Prevent / Invest)

## Next integration step

Replace simulated values with backend API endpoints from the Streamlit analytics layer or a dedicated FastAPI service.

## API connection

This mobile app now calls:
- `POST /v1/nlp-alerts`

Default URL is set in `App.js`:
- `API_BASE_URL = "http://127.0.0.1:8000"`

If testing on a physical phone, replace `127.0.0.1` with your PC LAN IP (for example `http://192.168.1.10:8000`).

You can now change the API URL directly inside the app:
- Open **API Settings**
- Paste your backend URL
- Tap **Apply API URL**
