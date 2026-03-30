"""
Chamber Live Monitor - Flask App (Google Sheets Edition)
All state is stored in Google Sheets — works on cloud, data never lost.

Setup steps (do once):
  1. Go to https://console.cloud.google.com
  2. Create a project > Enable "Google Sheets API" + "Google Drive API"
  3. Create a Service Account > download JSON key > save as 'credentials.json' in this folder
  4. Create a Google Sheet named "ChamberMonitorState"
  5. Share that sheet with the service account email (Editor access)
  6. Set env var: GOOGLE_SHEET_NAME=ChamberMonitorState  (or leave default)

Run locally:  python app_sheets.py
Deploy:       push to Railway / Render, set GOOGLE_CREDENTIALS env var (contents of credentials.json)
"""

from flask import Flask, render_template, request, jsonify
import json, os, threading, socket
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ── Google Sheets setup ────────────────────────────────────────────────────────
SCOPES       = ["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"]
SHEET_NAME   = os.environ.get("GOOGLE_SHEET_NAME", "ChamberMonitorState")
_gs_lock     = threading.Lock()
_gc          = None   # gspread client (lazy init)

CHAMBERS_DEF = {
    "TI01":   {"type": "Temperature", "temp_range": "0°C – 80°C"},
    "TI02":   {"type": "Temperature", "temp_range": "0°C – 80°C"},
    "AI01":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "AI02":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "AI03":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "AI04":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "AI05":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "AI06":   {"type": "Ambient",     "temp_range": "25°C (RT)"},
    "SOAK-1": {"type": "Soak",        "temp_range": "25°C (soak)"},
    "SOAK-2": {"type": "Soak",        "temp_range": "25°C (soak)"},
}

MAX_ACTIVITY   = 200
VISITOR_WINDOW = 5
_visitors = {}
_vlock    = threading.Lock()

ALL_SCRIPTS = [
    "Script_mochi-ss_ws_02a_01_endurance_eol_ht",
    "Script_mochi-ss_ws_02a_03_endurance_mol_ht",
    "Script_mochi-ss_ws_02a_08_htdr_load_mol",
    "Script_mochi-ss_ws_02a_08_htdr_load_mol_nocheck",
    "Script_mochi-ss_ws_02a_08_htdr_verify_mol",
    "Script_mochi-ss_ws_02a_09_htdr_load_eol",
    "Script_mochi-ss_ws_02a_09_htdr_verify_eol",
    "Script_mochi-ss_ws_02a_10_blockrd_eol_ht",
    "Script_mochi-ss_ws_02a_10_blockrd_eol_ht_disable_check",
    "Script_mochi-ss_ws_02a_11_wlrd_eol_ht",
    "Script_mochi-ss_ws_02a_11_wlrd_eol_ht_disable_check",
    "Script_mochi-ss_ws_02a_14_crosstemp_eol_1cycle_no_check",
    "Script_mochi-ss_ws_02a_14_crosstemp_eol_2cycles",
    "Script_mochi-ss_ws_02a_14_crosstemp_eol_6cycles_",
    "Script_mochi-ss_ws_02a_15_endurance_eol_rt",
    "Script_mochi-ss_ws_02a_16_endurance_mol_rt",
    "Script_mochi-ss_ws_02a_16_endurance_mol_rt_debug",
    "Script_mochi-ss_ws_02a_18_rtdr_load_eol",
    "Script_mochi-ss_ws_02a_18_rtdr_verify_eol",
    "Script_mochi-ss_ws_02a_21_blockrd_mol_rt",
    "Script_mochi-ss_ws_02a_21_blockrd_mol_rt_disable_check",
    "Script_mochi-ss_ws_02a_22_wlrd_mol_rt",
    "Script_mochi-ss_ws_02a_22_wlrd_mol_rt_disable_check",
    "Script_mochi_ws_02a_02_endurance_bol_lt",
    "Script_mochi_ws_02a_02_endurance_bol_lt_debug",
    "Script_mochi_ws_02a_04_endurance_bol_ht",
    "Script_mochi_ws_02a_05_poweronoff_ht",
    "Script_mochi_ws_02a_06_poweronoff_lt",
    "Script_mochi_02a_01_07_htdr_load_bol",
    "Script_mochi_ws_02a_07_htdr_load_bol_nocheck",
    "Script_mochi_ws_02a_07_htdr_verify_bol",
    "Script_mochi_ws_02a_07_htdr_verify_bol_nocheck",
    "Script_mochi_ws_02a_12_4c",
    "Script_mochi_ws_02a_12_4c_1cycles",
    "Script_mochi_ws_02a_12_4c_17cycles",
    "Script_mochi_ws_02a_13_crosstemp_bol",
    "Script_mochi_ws_02a_13_crosstemp_bol_1cycle",
    "Script_mochi_ws_02a_13_crosstemp_bol_24cycles",
    "Script_mochi_ws_02a_17_poweronoff_rt",
    "Script_mochi_ws_02a_17_poweronoff_rt_short",
    "Script_mochi_ws_02a_19_blockrd_bol_rt",
    "Script_mochi_ws_02a_20_wlrd_bol_rt",
    "Script_mochi-ss_datacollection_cvd",
    "Script_mochi-ss_diskcode",
    "Script_mochi-ss_e6",
    "Script_mochi-ss_fa",
    "Script_mochi_cvd",
    "Script_mochi_check",
    "Script_mochi_datacollection_cvd",
    "Script_mochi_diskcode",
    "Script_mochi_e6",
    "Script_mochi_fa",
    "Script_kulfi_spc_smart_pcba",
]


# ── Google Sheets helpers ──────────────────────────────────────────────────────

def get_gc():
    """Lazy-init gspread client from env var or local credentials.json."""
    global _gc
    if _gc:
        return _gc
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
    else:
        creds_file = os.path.join(os.path.dirname(__file__), "credentials.json")
        with open(creds_file, "r") as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    _gc = gspread.authorize(creds)
    return _gc


def get_or_create_worksheet(spreadsheet, title, headers):
    """Return existing worksheet or create it with headers."""
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=500, cols=len(headers))
        ws.append_row(headers)
    return ws


def init_sheets():
    """Ensure all required worksheets exist with correct headers."""
    gc = get_gc()
    try:
        sh = gc.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)
        print(f"  Created new spreadsheet: {SHEET_NAME}")

    get_or_create_worksheet(sh, "ChamberState", [
        "chamber", "type", "temp_range",
        "running_script", "running_operator", "running_dut", "running_notes", "running_start",
        "dut_count", "pass", "fail", "operator", "notes"
    ])
    get_or_create_worksheet(sh, "CompletedHistory", [
        "chamber", "script", "operator", "dut_count", "notes",
        "start_time", "end_time", "result", "pass", "fail"
    ])
    get_or_create_worksheet(sh, "ActivityLog", [
        "time", "action", "chamber", "script", "operator", "result", "client_ip"
    ])

    # Seed chamber rows if empty
    sh2 = gc.open(SHEET_NAME)
    ws = sh2.worksheet("ChamberState")
    rows = ws.get_all_records()
    existing = {r["chamber"] for r in rows}
    for ch, info in CHAMBERS_DEF.items():
        if ch not in existing:
            ws.append_row([
                ch, info["type"], info["temp_range"],
                "", "", 0, "", "",
                0, 0, 0, "", ""
            ])
    print("  Google Sheets initialized OK")


# ── State read/write ───────────────────────────────────────────────────────────

def read_state():
    with _gs_lock:
        gc  = get_gc()
        sh  = gc.open(SHEET_NAME)
        ws_state = sh.worksheet("ChamberState")
        ws_hist  = sh.worksheet("CompletedHistory")

        state_rows = ws_state.get_all_records()
        hist_rows  = ws_hist.get_all_records()

        chambers = {}
        for r in state_rows:
            ch = r["chamber"]
            running = None
            if r.get("running_script"):
                running = {
                    "script":    r["running_script"],
                    "operator":  r["running_operator"],
                    "dut_count": r["running_dut"],
                    "notes":     r["running_notes"],
                    "start_time":r["running_start"],
                    "result":    "Running"
                }
            completed = [
                {
                    "script":    h["script"],
                    "operator":  h["operator"],
                    "dut_count": h["dut_count"],
                    "notes":     h["notes"],
                    "start_time":h["start_time"],
                    "end_time":  h["end_time"],
                    "result":    h["result"],
                    "pass":      h["pass"],
                    "fail":      h["fail"],
                }
                for h in hist_rows if h["chamber"] == ch
            ]
            completed.reverse()  # newest first
            chambers[ch] = {
                "type":       r["type"],
                "temp_range": r["temp_range"],
                "running":    running,
                "completed":  completed,
                "dut_count":  r["dut_count"],
                "pass":       r["pass"],
                "fail":       r["fail"],
                "operator":   r["operator"],
                "notes":      r["notes"],
            }
        return {"chambers": chambers}


def _find_chamber_row(ws, chamber):
    """Return 1-based row index of chamber in ChamberState sheet."""
    col = ws.col_values(1)  # chamber column
    for i, val in enumerate(col):
        if val == chamber:
            return i + 1
    return None


def set_running(chamber, script, operator, dut, notes):
    with _gs_lock:
        gc = get_gc()
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("ChamberState")
        row = _find_chamber_row(ws, chamber)
        if not row:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Columns: running_script=4, operator=5, dut=6, notes=7, start=8
        ws.update(f"D{row}:H{row}", [[script, operator, dut, notes, now]])
        ws.update_cell(row, 9, dut)    # dut_count
        ws.update_cell(row, 12, operator)
        return True


def clear_running(chamber, result, passed, failed, notes_extra):
    with _gs_lock:
        gc = get_gc()
        sh = gc.open(SHEET_NAME)
        ws_state = sh.worksheet("ChamberState")
        ws_hist  = sh.worksheet("CompletedHistory")

        row = _find_chamber_row(ws_state, chamber)
        if not row:
            return None
        # Read current running info
        running_data = ws_state.row_values(row)
        # Indices (0-based): script=3, op=4, dut=5, notes=6, start=7
        script    = running_data[3] if len(running_data) > 3 else ""
        operator  = running_data[4] if len(running_data) > 4 else ""
        dut       = running_data[5] if len(running_data) > 5 else 0
        notes     = notes_extra or (running_data[6] if len(running_data) > 6 else "")
        start     = running_data[7] if len(running_data) > 7 else ""
        now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Append to history
        ws_hist.append_row([chamber, script, operator, dut, notes, start, now, result, passed, failed])

        # Clear running columns, update pass/fail totals
        ws_state.update(f"D{row}:H{row}", [["", "", 0, "", ""]])
        old_pass = int(running_data[9])  if len(running_data) > 9  and running_data[9]  else 0
        old_fail = int(running_data[10]) if len(running_data) > 10 and running_data[10] else 0
        ws_state.update_cell(row, 10, old_pass + int(passed))
        ws_state.update_cell(row, 11, old_fail + int(failed))

        return {"script": script, "operator": operator}


def clear_history_for_chamber(chamber):
    with _gs_lock:
        gc = get_gc()
        sh = gc.open(SHEET_NAME)
        ws_state = sh.worksheet("ChamberState")
        ws_hist  = sh.worksheet("CompletedHistory")

        # Reset pass/fail
        row = _find_chamber_row(ws_state, chamber)
        if row:
            ws_state.update_cell(row, 10, 0)
            ws_state.update_cell(row, 11, 0)

        # Delete history rows for this chamber (iterate backwards)
        hist_rows = ws_hist.get_all_values()
        rows_to_delete = [i+1 for i, r in enumerate(hist_rows) if i > 0 and r[0] == chamber]
        for r in reversed(rows_to_delete):
            ws_hist.delete_rows(r)


def append_activity(action, chamber, script, operator, result="", client_ip=""):
    with _gs_lock:
        gc = get_gc()
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("ActivityLog")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.insert_row([now, action, chamber, script, operator, result, client_ip], index=2)
        # Keep only last MAX_ACTIVITY rows
        all_rows = ws.get_all_values()
        if len(all_rows) > MAX_ACTIVITY + 1:
            ws.delete_rows(MAX_ACTIVITY + 2, len(all_rows))


def read_activity(limit=50):
    with _gs_lock:
        gc = get_gc()
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("ActivityLog")
        rows = ws.get_all_records()
        return rows[:limit]


# ── Visitor tracking (in-memory, resets on restart — that's fine) ─────────────

def record_visitor(ip, name=""):
    with _vlock:
        existing = _visitors.get(ip, {})
        _visitors[ip] = {
            "last_seen": datetime.now(),
            "name": name or existing.get("name", ""),
        }


def get_online_visitors():
    cutoff = datetime.now() - timedelta(minutes=VISITOR_WINDOW)
    with _vlock:
        online = [
            {"ip": ip, "name": v["name"],
             "last_seen": v["last_seen"].strftime("%H:%M:%S")}
            for ip, v in _visitors.items()
            if v["last_seen"] >= cutoff
        ]
    online.sort(key=lambda x: x["last_seen"], reverse=True)
    return online


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return get_local_ip()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    state = read_state()
    return render_template("dashboard.html",
                           chambers=state["chambers"],
                           all_scripts=ALL_SCRIPTS,
                           network_ip=get_hostname(),
                           network_ip_fallback=get_local_ip(),
                           now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@app.route("/api/state")
def api_state():
    record_visitor(request.remote_addr or "unknown")
    state = read_state()
    state["server_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(state)


@app.route("/api/visitors")
def api_visitors():
    v = get_online_visitors()
    return jsonify({"visitors": v, "count": len(v)})


@app.route("/api/activity")
def api_activity():
    limit = int(request.args.get("limit", 50))
    return jsonify(read_activity(limit))


@app.route("/api/start", methods=["POST"])
def api_start():
    data      = request.json
    chamber   = data.get("chamber")
    script    = data.get("script")
    operator  = data.get("operator", "")
    dut       = int(data.get("dut_count", 0))
    notes     = data.get("notes", "")
    client_ip = request.remote_addr or ""
    record_visitor(client_ip, operator)

    if not chamber or not script:
        return jsonify({"ok": False, "error": "chamber and script required"}), 400

    state = read_state()
    ch = state["chambers"].get(chamber)
    if not ch:
        return jsonify({"ok": False, "error": "unknown chamber"}), 404

    # If something running, interrupt it first
    if ch["running"]:
        prev = ch["running"]
        clear_running(chamber, "Interrupted", 0, 0, "")
        append_activity("Interrupted", chamber, prev["script"], prev.get("operator", ""), "Interrupted", client_ip)

    set_running(chamber, script, operator, dut, notes)
    append_activity("Started", chamber, script, operator, "Running", client_ip)
    return jsonify({"ok": True})


@app.route("/api/complete", methods=["POST"])
def api_complete():
    data      = request.json
    chamber   = data.get("chamber")
    result    = data.get("result", "Pass")
    passed    = int(data.get("pass", 0))
    failed    = int(data.get("fail", 0))
    notes     = data.get("notes", "")
    client_ip = request.remote_addr or ""

    if not chamber:
        return jsonify({"ok": False, "error": "chamber required"}), 400

    state = read_state()
    ch = state["chambers"].get(chamber)
    if not ch:
        return jsonify({"ok": False, "error": "unknown chamber"}), 404
    if not ch["running"]:
        return jsonify({"ok": False, "error": "no script running"}), 400

    entry = clear_running(chamber, result, passed, failed, notes)
    append_activity("Completed", chamber, entry["script"], entry.get("operator", ""), result, client_ip)
    return jsonify({"ok": True})


@app.route("/api/clear_history", methods=["POST"])
def api_clear_history():
    data      = request.json
    chamber   = data.get("chamber")
    operator  = data.get("operator", "")
    client_ip = request.remote_addr or ""

    if not chamber:
        return jsonify({"ok": False, "error": "chamber required"}), 400
    clear_history_for_chamber(chamber)
    append_activity("ClearedHistory", chamber, "", operator, "", client_ip)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("")
    print("  ========================================================")
    print("   CHAMBER LIVE MONITOR  -  Google Sheets Edition")
    print("  ========================================================")
    print("  Connecting to Google Sheets...")
    try:
        init_sheets()
    except Exception as e:
        print(f"  ERROR connecting to Google Sheets: {e}")
        print("  Make sure credentials.json exists or GOOGLE_CREDENTIALS env var is set.")
        exit(1)
    hostname = get_hostname()
    ip       = get_local_ip()
    print(f"  Local:     http://localhost:5000")
    print(f"  HOSTNAME:  http://{hostname}:5000")
    print(f"  IP:        http://{ip}:5000")
    print("  ========================================================")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
