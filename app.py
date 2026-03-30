"""
Chamber Live Monitor - Flask App  (Team Edition)
Run:  python app.py
Share: http://<YOUR-IP>:5000  (shown on startup)
"""

from flask import Flask, render_template, request, jsonify
import json, os, threading, socket
from datetime import datetime, timedelta

app = Flask(__name__)
BASE = os.path.dirname(__file__)
STATE_FILE    = os.path.join(BASE, "chamber_state.json")
ACTIVITY_FILE = os.path.join(BASE, "activity_log.json")
_lock = threading.Lock()

MAX_ACTIVITY   = 200   # keep last N activity entries
VISITOR_WINDOW = 5    # minutes — consider a visitor "online" if seen within this window

# in-memory visitor tracker  { ip: {"last_seen": datetime, "name": str} }
_visitors = {}
_vlock    = threading.Lock()


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


def read_state():
    with _lock:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def write_state(state):
    with _lock:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


def read_activity():
    if not os.path.exists(ACTIVITY_FILE):
        return []
    with _lock:
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def append_activity(action, chamber, script, operator, result="", client_ip=""):
    entries = read_activity()
    entries.insert(0, {
        "time":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action":    action,
        "chamber":   chamber,
        "script":    script,
        "operator":  operator,
        "result":    result,
        "client_ip": client_ip,
    })
    entries = entries[:MAX_ACTIVITY]
    with _lock:
        with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    state = read_state()
    hostname   = get_hostname()
    current_ip = get_local_ip()
    return render_template("dashboard.html",
                           chambers=state["chambers"],
                           all_scripts=ALL_SCRIPTS,
                           network_ip=hostname,
                           network_ip_fallback=current_ip,
                           now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@app.route("/api/state")
def api_state():
    record_visitor(request.remote_addr or "unknown")
    state = read_state()
    state["server_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(state)


@app.route("/api/visitors")
def api_visitors():
    return jsonify({"visitors": get_online_visitors(), "count": len(get_online_visitors())})


@app.route("/api/activity")
def api_activity():
    limit = int(request.args.get("limit", 50))
    return jsonify(read_activity()[:limit])


@app.route("/api/start", methods=["POST"])
def api_start():
    """Mark a script as RUNNING in a chamber."""
    data = request.json
    chamber  = data.get("chamber")
    script   = data.get("script")
    operator = data.get("operator", "")
    dut      = int(data.get("dut_count", 0))
    notes    = data.get("notes", "")

    client_ip = request.remote_addr or ""
    record_visitor(client_ip, data.get("operator", ""))
    if not chamber or not script:
        return jsonify({"ok": False, "error": "chamber and script required"}), 400

    state = read_state()
    ch = state["chambers"].get(chamber)
    if not ch:
        return jsonify({"ok": False, "error": "unknown chamber"}), 404

    # If something was already running, push it to completed as interrupted
    if ch["running"]:
        prev = ch["running"]
        prev["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prev["result"]   = "Interrupted"
        ch["completed"].insert(0, prev)
        append_activity("Interrupted", chamber, prev["script"], prev.get("operator",""), "Interrupted", client_ip)

    ch["running"] = {
        "script":     script,
        "operator":   operator,
        "dut_count":  dut,
        "notes":      notes,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "result":     "Running"
    }
    ch["dut_count"] = dut
    ch["operator"]  = operator
    ch["notes"]     = notes

    write_state(state)
    append_activity("Started", chamber, script, operator, "Running", client_ip)
    return jsonify({"ok": True})


@app.route("/api/complete", methods=["POST"])
def api_complete():
    """Mark the running script as COMPLETED in a chamber."""
    data    = request.json
    chamber = data.get("chamber")
    result  = data.get("result", "Pass")   # Pass | Fail | Error
    passed  = int(data.get("pass", 0))
    failed  = int(data.get("fail", 0))
    notes   = data.get("notes", "")

    if not chamber:
        return jsonify({"ok": False, "error": "chamber required"}), 400

    state = read_state()
    ch = state["chambers"].get(chamber)
    if not ch:
        return jsonify({"ok": False, "error": "unknown chamber"}), 404

    if not ch["running"]:
        return jsonify({"ok": False, "error": "no script running"}), 400

    client_ip = request.remote_addr or ""
    entry = ch["running"]
    entry["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry["result"]   = result
    entry["pass"]     = passed
    entry["fail"]     = failed
    if notes:
        entry["notes"] = notes

    ch["completed"].insert(0, entry)
    ch["pass"] += passed
    ch["fail"] += failed
    ch["running"] = None

    write_state(state)
    append_activity("Completed", chamber, entry["script"], entry.get("operator",""), result, client_ip)
    return jsonify({"ok": True})


@app.route("/api/clear_history", methods=["POST"])
def api_clear_history():
    """Clear completed history for a chamber."""
    data    = request.json
    chamber = data.get("chamber")
    state   = read_state()
    ch = state["chambers"].get(chamber)
    if not ch:
        return jsonify({"ok": False, "error": "unknown chamber"}), 404
    operator = data.get("operator", "")
    client_ip = request.remote_addr or ""
    ch["completed"] = []
    ch["pass"] = 0
    ch["fail"] = 0
    write_state(state)
    append_activity("ClearedHistory", chamber, "", operator, "", client_ip)
    return jsonify({"ok": True})


if __name__ == "__main__":
    hostname = get_hostname()
    ip       = get_local_ip()
    print("")
    print("  ========================================================")
    print("   CHAMBER LIVE MONITOR  -  Team Edition")
    print("  ========================================================")
    print(f"   Local:     http://localhost:5050")
    print(f"   HOSTNAME:  http://{hostname}:5050   <-- PERMANENT LINK")
    print(f"   IP:        http://{ip}:5050         (changes daily)")
    print("  ========================================================")
    print("   Press Ctrl+C to stop")
    print("")
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, host="0.0.0.0", port=port)
