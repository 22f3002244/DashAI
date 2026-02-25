import json
import re
import requests
from config import GROQ_API_KEY
from database import log_agent
from agents.data_cleaner import _pretty

def _groq(system, user, model="mixtral-8x7b-32768"):
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise ValueError("Groq API key not configured on server.")
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "system", "content": system},
              {"role": "user", "content": user}], "temperature": 0.2, "max_tokens": 4096},
        timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def _fallback_viz(state):
    cd = state["cleaned_data"]
    nk = cd.get("numeric_keys", []); bk = cd.get("boolean_keys", []); sk = cd.get("string_keys", [])
    recs = []
    for i, k in enumerate(nk[:4]):
        recs.append({"id": f"line_{i}", "title": _pretty(k), "type": "line", "keys": [k],
                     "description": f"Sensor readings over time for {_pretty(k)}", "priority": i+1})
    if len(nk) >= 3:
        recs.append({"id": "radar_0", "title": "Multi-Sensor Overview", "type": "radar", "keys": nk[:6],
                     "description": "Compare all sensors at a glance", "priority": 9})
    if len(nk) >= 2:
        recs.append({"id": "bar_avg", "title": "Sensor Averages", "type": "bar", "keys": nk[:8],
                     "description": "Average value per sensor for the selected period", "priority": 8})
    for i, k in enumerate(bk[:3]):
        recs.append({"id": f"bool_{i}", "title": f"{_pretty(k)} Status", "type": "boolean_status", "keys": [k],
                     "description": f"How often {_pretty(k)} was on vs off", "priority": 5})
    for i, k in enumerate(sk[:1]):
        recs.append({"id": f"str_{i}", "title": f"{_pretty(k)} Values", "type": "string_freq", "keys": [k],
                     "description": f"Most common values for {_pretty(k)}", "priority": 6})
    if nk:
        recs.append({"id": "kpi_0", "title": _pretty(nk[0]), "type": "kpi", "keys": [nk[0]],
                     "description": "Latest sensor reading", "priority": 0})
    return recs

def agent_viz_recommender(state):
    if state["agent_statuses"].get("DataCleaner") in ("error", "skipped"):
        state["agent_statuses"]["VizRecommender"] = "skipped"; return state

    sid = state["session_id"]
    log_agent(sid, "VizRecommender", "running", "AI is choosing the best charts for your data...")

    try:
        cd    = state["cleaned_data"]
        raw   = state["raw_data"]
        stats = cd.get("stats", {})
        pats  = state.get("patterns", [])

        sys_p = """You are an expert IoT data visualization AI.
Return ONLY a valid JSON array — no markdown fences, no explanation whatsoever.
Choose from these chart types: "line","bar","doughnut","scatter","radar","polarArea","kpi","boolean_status","string_freq"
Each object must have: {"id":str,"title":str,"type":str,"keys":[str,...],"description":str,"priority":int}
Rules:
- line: best for time-series numeric trends (group 2-3 related sensors together)
- bar: compare averages across multiple numeric sensors, or horizontal for string value counts
- doughnut: boolean on/off ratios, or categorical with ≤6 values
- scatter: 2 correlated numeric sensors (put both in keys)
- radar: 3-6 numeric sensors for a multi-dimensional sensor profile
- polarArea: 3-6 numeric sensors with similar scales
- kpi: single most critical numeric value (latest/avg)
- boolean_status: on/off status with percentage bar
- string_freq: horizontal bar of value frequencies
Generate 6-9 visualizations. Use only keys that exist in the provided data. Prioritize keys with trends or anomalies."""

        num_s = {k: {"avg": v["avg"], "min": v["min"], "max": v["max"], "trend": v.get("trend","?"),
                     "anomalies": v.get("anomaly_count",0), "unit": v.get("unit",""), "n": v["count"]}
                 for k, v in stats.items() if v.get("type") == "numeric"}
        bool_s = {k: {"on_pct": round(v.get("true_count",0)/max(v.get("count",1),1)*100,1), "n": v.get("count",0)}
                  for k, v in stats.items() if v.get("type") == "boolean"}
        str_s  = {k: {"unique": v.get("unique_values",0), "latest": v.get("latest",""), "n": v["count"]}
                  for k, v in stats.items() if v.get("type") in ("string","json")}

        usr_p = f"""Device: {raw['device_name']} (type: {raw.get('device_type','unknown')})
Time window: {raw['time_range_label']}
Detected patterns: {json.dumps(pats[:8])}
Numeric sensors ({len(num_s)}): {json.dumps(num_s)}
On/Off sensors ({len(bool_s)}): {json.dumps(bool_s)}
Text/state sensors ({len(str_s)}): {json.dumps(str_s)}
Return the JSON array of 6-9 visualizations."""

        ai = _groq(sys_p, usr_p)
        match = re.search(r'\[[\s\S]*\]', ai)
        if not match: raise ValueError("No JSON array in AI response")
        viz_list = json.loads(match.group())
        valid_t = {"line","bar","doughnut","scatter","radar","polarArea","kpi","boolean_status","string_freq"}
        viz_list = [v for v in viz_list
                    if isinstance(v, dict) and v.get("type") in valid_t
                    and isinstance(v.get("keys"), list) and v["keys"]]

        state["viz_recommendations"] = viz_list
        state["agent_statuses"]["VizRecommender"] = "done"
        log_agent(sid, "VizRecommender", "done", f"AI selected {len(viz_list)} visualizations for your data.")

    except Exception as e:
        log_agent(sid, "VizRecommender", "warning", f"AI unavailable ({e}). Using smart defaults.")
        state["viz_recommendations"] = _fallback_viz(state)
        state["agent_statuses"]["VizRecommender"] = "done"

    return state
