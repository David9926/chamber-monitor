# Chamber Live Monitor — Cloud Deploy Guide
## Google Sheets + Railway (Free, Always On)

---

## STEP 1 — Google Cloud Setup (10 minutes, do once)

1. Go to https://console.cloud.google.com
2. Click **"New Project"** → name it `ChamberMonitor` → Create
3. In the search bar type **"Google Sheets API"** → click it → click **Enable**
4. In the search bar type **"Google Drive API"** → click it → click **Enable**
5. Go to **IAM & Admin → Service Accounts** → click **"Create Service Account"**
   - Name: `chamber-monitor`
   - Click **Create and Continue** → **Done**
6. Click on the service account you just created
7. Go to **Keys** tab → **Add Key** → **Create new key** → JSON → Download
8. **Save the downloaded file as `credentials.json`** inside the `chamber_monitor` folder

---

## STEP 2 — Create Google Sheet (2 minutes)

1. Go to https://sheets.google.com → create a new blank sheet
2. Name it exactly: **`ChamberMonitorState`**
3. Open `credentials.json`, find the `"client_email"` field — copy that email address
4. In your Google Sheet → click **Share** → paste that email → set **Editor** → Share

---

## STEP 3 — Test locally first (1 minute)

```
cd chamber_monitor
pip install gspread google-auth
python app_sheets.py
```

Open http://localhost:5000 — should work exactly like before but data is now in Google Sheets.

---

## STEP 4 — Deploy to Railway (5 minutes, free)

1. Go to https://railway.app → sign up with GitHub (free)
2. Click **"New Project"** → **"Deploy from GitHub repo"**
   - Push the `chamber_monitor` folder to a GitHub repo first (or use Railway's CLI)
3. Railway auto-detects the `Procfile` and deploys

### Set environment variables in Railway:
- `GOOGLE_SHEET_NAME` = `ChamberMonitorState`
- `GOOGLE_CREDENTIALS` = *(paste the entire contents of credentials.json here)*

4. Railway gives you a permanent URL like:
   **`https://chamber-monitor-production.up.railway.app`**

That's your **permanent link** — works 24/7, even when your PC is off.

---

## STEP 5 — Share with team

Send them: `https://chamber-monitor-production.up.railway.app`

- Works on any device, any network, anywhere in the world
- Data stored in Google Sheets — never lost
- You can also view/edit raw data directly in Google Sheets as a bonus

---

## Files in chamber_monitor folder

| File | Purpose |
|---|---|
| `app.py` | Local version (JSON files, for office network use) |
| `app_sheets.py` | Cloud version (Google Sheets database) |
| `credentials.json` | Google service account key (DO NOT share/commit to GitHub) |
| `requirements.txt` | Python packages for cloud |
| `Procfile` | Tells Railway how to start the app |
| `start_monitor.bat` | Double-click to run locally |

---

## IMPORTANT — Keep credentials.json secret!
Never upload `credentials.json` to GitHub. Add it to `.gitignore`:
```
credentials.json
chamber_state.json
activity_log.json
*.pyc
__pycache__/
```
