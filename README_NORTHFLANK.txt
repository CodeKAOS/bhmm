BITCOIN HERO TRACKER v19 — NORTHFLANK EDITION
==============================================

Features retained / included
- 24/7 server-side Bitcoin Hero simulated-price collector (~3 seconds)
- Persistent SQLite history and hourly OHLC candles
- Branded username/password login with HttpOnly session cookies protecting dashboard APIs
- Candlestick charts with Open, High, Low, Close (OHLC) hover details
- LIVE (last 5 minutes), 1H (1-minute candles), 4H (5-minute candles), 1D (15-minute candles), ALL (saved hourly candles)
- Live 1-minute and current hourly candles update from normal 3-second price polls
- Hourly candles are stored in SQLite and survive restarts/redeployments when the existing /data volume is retained
- On first startup, existing raw price history is converted into hourly candles without deleting existing price records
- Recent minute candles are restored from existing raw observations at startup
- Observed highs/lows and timestamps remain independently protected and update on each poll
- Potential UP/DOWN percentage range calculations
- Cryptocurrency logos in place of gain-potential rings
- CSV export
- CSV Import & Merge: adds old tracker exports without replacing existing data
- Duplicate price/event detection during import
- Automatic SQLite backup before each import
- Existing persistent database and observed extrema are preserved on upgrade

NORTHFLANK DEPLOYMENT
1. Extract this ZIP and upload the CONTENTS to the root of a private GitHub repository.
2. In Northflank create a Developer Sandbox project.
3. Create Service -> Combined service, select your repository and main branch.
4. Build option: Dockerfile. Dockerfile path: /Dockerfile (root).
5. Add runtime environment variables:
      TRACKER_USERNAME = choose-a-username
      TRACKER_PASSWORD = choose-a-long-random-password
      DATA_DIR = /data
      PORT = 8000
   Do not put the password in GitHub.
6. Networking: expose port 8000, protocol HTTP, accessibility Public.
7. Add/retain a persistent volume mounted at /data. Keep the service at ONE replica because SQLite uses this single-writer volume.
8. Deploy. Northflank will provide an HTTPS *.code.run address for the public port.
9. Open the address. Your browser will request the username/password.
10. The dashboard uses a branded sign-in page. Sessions expire after 12 hours; /api/health is available after login.

IMPORTING OLD DATA
- In the dashboard click “Import & Merge CSV”.
- Select any CSV exported by the tracker.
- The server makes a database backup first, then merges price rows and extrema events.
- Duplicate timestamp/price records are skipped.
- Imported history is also folded into hourly candles.
- Backups are stored on the /data persistent volume as backup-YYYYMMDD-HHMMSS.sqlite3.

EXISTING DEPLOYMENTS — IMPORTANT
- Keep the existing /data persistent volume mounted. Do not delete or replace it during deployment.
- The first v19 startup adds candle tables and backfills hourly candles from existing raw prices. It does not delete existing raw prices, observed extrema, or events.
- Existing extrema are not overwritten by BASE defaults when a database already exists.
- The first candle backfill can take a little time if the database contains a long raw-price history.

IMPORTANT
- Bitcoin Hero prices are simulated, not real cryptocurrency market prices.
- Potential-trade percentages are distances to observed tracker extrema, not forecasts.
- A Northflank single-read/write persistent volume means one service replica. Do not scale this SQLite edition horizontally.
