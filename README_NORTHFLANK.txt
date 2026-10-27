BITCOIN HERO TRACKER v17 — NORTHFLANK EDITION
==============================================

Features retained / included
- 24/7 server-side Bitcoin Hero simulated-price collector (~3 seconds)
- Persistent SQLite history
- Password protection for dashboard + APIs
- LIVE (5 min), 1H, 1D and ALL charts for all 8 coins
- Hover/touch chart inspection showing price + timestamp
- Observed highs/lows and timestamps
- Potential UP/DOWN percentage range calculations
- Colorful gain-potential rings
- CSV export
- CSV Import & Merge: adds old tracker exports without replacing existing data
- Duplicate price/event detection during import
- Automatic SQLite backup before each import
- Updated protected extrema using cloud snapshot dated 2026-10-27 (latest snapshot at 2026-10-27T17:29:34.192000+00:00 UTC)

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
7. Add a persistent volume mounted at /data. Keep the service at ONE replica because SQLite uses this single-writer volume.
8. Deploy. Northflank will provide an HTTPS *.code.run address for the public port.
9. Open the address. Your browser will request the username/password.
10. Open /api/health after login if you want to verify the collector status.

IMPORTING OLD DATA
- In the dashboard click “Import & Merge CSV”.
- Select any CSV exported by the tracker.
- The server makes a database backup first, then merges price rows and extrema events.
- Duplicate timestamp/price records are skipped.
- You can import multiple snapshots one after another.
- Backups are stored on the /data persistent volume as backup-YYYYMMDD-HHMMSS.sqlite3.

EXISTING DEPLOYMENTS
- The BASE extrema are used only when each symbol is first initialized. If /data already contains the SQLite database, code redeployment will not overwrite extrema already stored in that database. Use the dashboard's CSV import/merge workflow for historical data; do not delete the persistent volume unless you intentionally want to erase stored history.

IMPORTANT
- Bitcoin Hero prices are simulated, not real cryptocurrency market prices.
- Potential-trade percentages are distances to observed tracker extrema, not forecasts.
- A Northflank single-read/write persistent volume means one service replica. Do not scale this SQLite edition horizontally.
