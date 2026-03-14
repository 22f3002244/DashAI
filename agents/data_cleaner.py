from datetime import datetime
import json
import math
import requests
from config import GROQ_API_KEY
from database import log_agent

def _groq_data_cleaner(system, user, model="llama-3.1-8b-instant"):
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        return None
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "system", "content": system},
              {"role": "user", "content": user}], "temperature": 0.2, "max_tokens": 1024},
        timeout=15)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def _classify(v) -> str:
    if v is None: return "null"
    if isinstance(v, bool): return "boolean"
    s = str(v).strip().lower()
    if s in ("true","false","on","off","yes","no","1","0"): return "boolean"
    try: float(v); return "numeric"
    except: pass
    if s.startswith("{"):
        try: json.loads(s); return "json"
        except: pass
    return "string"

def _sf(v):
    try: return float(v)
    except: return None

def _unit(k: str) -> str:
    k = k.lower()
    for words, u in [
        (["temp","temperature"], "°C"),
        (["humid","rh","humidity"], "%"),
        (["press","pressure"], "hPa"),
        (["volt","voltage"], "V"),
        (["current","amp"], "A"),
        (["power","watt"], "W"),
        (["energy","kwh"], "kWh"),
        (["speed","velocity"], "m/s"),
        (["co2","carbon"], "ppm"),
        (["pm2","pm10","dust","particle"], "µg/m³"),
        (["rssi","signal","dbm"], "dBm"),
        (["batt","battery","soc"], "%"),
        (["freq","frequency"], "Hz"),
        (["lux","illumin","light"], "lux"),
        (["flow","rate"], "L/min"),
        (["level","depth"], "cm"),
        (["ph"], "pH"),
    ]:
        if any(w in k for w in words): return u
    return ""

def _pretty(k: str) -> str:
    return k.replace("_"," ").replace("."," › ").title()

def agent_data_cleaner(state):
    if state["agent_statuses"].get("DataFetcher") == "error":
        state["agent_statuses"]["DataCleaner"] = "skipped"; return state

    sid = state["session_id"]
    log_agent(sid, "DataCleaner", "running", "Analysing sensor data and finding patterns...")

    try:
        raw       = state["raw_data"]
        telemetry = raw.get("telemetry", {})
        attrs     = raw.get("attributes", {})

        num_keys, bool_keys, str_keys, json_keys = [], [], [], []
        cleaned_num, cleaned_bool, cleaned_str   = {}, {}, {}
        stats    = {}
        patterns = []

        for key, records in telemetry.items():
            if not records: continue
            first = next((r.get("value") for r in records if r.get("value") is not None), None)
            dtype = _classify(first)

            if dtype == "numeric":
                num_keys.append(key)
                vals, tss = [], []
                for r in records:
                    fv = _sf(r.get("value"))
                    if fv is not None and math.isfinite(fv):
                        vals.append(fv); tss.append(r["ts"])
                if not vals: continue

                n   = len(vals)
                avg = sum(vals) / n
                mn, mx = min(vals), max(vals)
                var = sum((x-avg)**2 for x in vals) / n
                std = math.sqrt(var)

                if n >= 3:
                    xm  = (n-1) / 2
                    num = sum((i-xm)*(v-avg) for i,v in enumerate(vals))
                    den = sum((i-xm)**2 for i in range(n))
                    slope = num/den if den else 0
                    pct   = (slope/avg*100) if avg else 0
                    trend = "rising" if pct>1 else ("falling" if pct<-1 else "stable")
                else:
                    slope, trend = 0, "stable"

                anomalies = [i for i,v in enumerate(vals) if std>0 and abs(v-avg)>2.5*std]
                val_slice = vals[-300:]
                ts_slice = tss[-300:]
                anomaly_flags = [(std>0 and abs(v-avg)>2.5*std) for v in val_slice]
                
                cleaned_num[key] = {"values": val_slice, "timestamps": ts_slice, "anomaly_flags": anomaly_flags, "count": n, "unit": _unit(key)}
                stats[key] = {"type":"numeric","avg":round(avg,4),"min":round(mn,4),"max":round(mx,4),
                              "std":round(std,4),"trend":trend,"slope":round(slope,6),
                              "anomaly_count":len(anomalies),"count":n,"unit":_unit(key)}

                if trend in ("rising","falling"):
                    patterns.append({"key":key,"type":"trend","severity":"info",
                        "description":f"'{_pretty(key)}' is trending {trend} over the selected period."})
                if len(anomalies) > 0:
                    recent = anomalies[-3:]
                    details = ", ".join(f"{round(vals[i],2)} at {datetime.fromtimestamp(tss[i]/1000).strftime('%H:%M')}" for i in recent)
                    patterns.append({"key":key,"type":"anomaly","severity":"warning",
                        "description":f"'{_pretty(key)}' has {len(anomalies)} unusual reading(s) outside normal range. Recent anomalies: {details}."})
                if std == 0 and n > 1:
                    patterns.append({"key":key,"type":"constant","severity":"info",
                        "description":f"'{_pretty(key)}' has been constant at {vals[0]} {_unit(key)} throughout the period."})

            elif dtype == "boolean":
                bool_keys.append(key)
                events = []
                for r in records:
                    bv = str(r.get("value","")).lower() in ("true","1","yes","on")
                    events.append({"ts": r["ts"], "value": bv})
                tc = sum(1 for e in events if e["value"])
                fc = len(events) - tc
                cleaned_bool[key] = {"events": events[-200:], "count": len(events)}
                stats[key] = {"type":"boolean","true_count":tc,"false_count":fc,
                              "last_value": events[-1]["value"] if events else False,
                              "count": len(events)}
                if tc == 0:
                    patterns.append({"key":key,"type":"status","severity":"info",
                        "description":f"'{_pretty(key)}' was OFF/inactive for the entire period."})
                elif fc == 0:
                    patterns.append({"key":key,"type":"status","severity":"info",
                        "description":f"'{_pretty(key)}' was ON/active for the entire period."})

            elif dtype in ("string","json"):
                if dtype == "json": json_keys.append(key)
                else: str_keys.append(key)

                if dtype == "json":
                    json_extracted_keys = []
                    for r in records:
                        try:
                            obj = json.loads(str(r.get("value","{}")))
                            if isinstance(obj, dict):
                                for sk, sv in obj.items():
                                    fv = _sf(sv)
                                    if fv is not None:
                                        fkey = f"{key}.{sk}"
                                        if fkey not in cleaned_num:
                                            cleaned_num[fkey] = {"values":[],"timestamps":[],"count":0,"unit":""}
                                            num_keys.append(fkey)
                                            json_extracted_keys.append(fkey)
                                            stats[fkey] = {"type":"numeric","avg":0,"min":fv,"max":fv,
                                                           "std":0,"trend":"stable","slope":0,
                                                           "anomaly_count":0,"count":0,"unit":""}
                                        cleaned_num[fkey]["values"].append(fv)
                                        cleaned_num[fkey]["timestamps"].append(r["ts"])
                                        cleaned_num[fkey]["count"] += 1
                        except: pass
                    for fkey in json_extracted_keys:
                        d2 = cleaned_num.get(fkey, {})
                        v2 = d2.get("values", [])
                        if v2:
                            a2 = sum(v2)/len(v2)
                            stats[fkey].update({"avg":round(a2,4),"min":round(min(v2),4),
                                                "max":round(max(v2),4),"count":len(v2)})

                freq = {}
                for r in records:
                    v = str(r.get("value",""))
                    freq[v] = freq.get(v,0) + 1
                cleaned_str[key] = {"freq":freq,"latest":str(records[-1].get("value","")),"count":len(records)}
                stats[key] = {"type":"string" if dtype=="string" else "json",
                              "unique_values":len(freq),"latest":str(records[-1].get("value",""))[:120],
                              "count":len(records)}
                if len(freq) <= 8:
                    patterns.append({"key":key,"type":"categorical","severity":"info",
                        "description":f"'{_pretty(key)}' switches between {len(freq)} states: " + ", ".join(list(freq)[:4])})

        attr_stats = {}
        for k, meta in attrs.items():
            v = meta.get("value")
            attr_stats[k] = {"value":str(v)[:200] if v is not None else "—",
                             "scope":meta.get("scope","device"),
                             "dtype":_classify(v),
                             "lastUpdateTs":meta.get("lastUpdateTs")}

        state["cleaned_data"] = {
            "numeric":cleaned_num,"boolean":cleaned_bool,"string":cleaned_str,
            "stats":stats,"attr_stats":attr_stats,
            "numeric_keys":num_keys,"boolean_keys":bool_keys,
            "string_keys":str_keys,"json_keys":json_keys}
            
        # --- Cross-Device Correlation AI Pass ---
        if stats and len(stats) >= 2 and GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
            try:
                log_agent(sid, "DataCleaner", "running", "Deep AI scan for cross-device & cross-sensor correlations...")
                sys_p = """You are an IoT Data Analyst. Review the provided stats and detect any potential logical correlations between different sensors or devices (e.g. 'When Device A temp rises, Device B cooling status is ON'). Provide 1 to 3 insightful correlations. Return ONLY a valid JSON list of objects. Like this: [{"key": "Cross-Device Insight", "type": "correlation", "severity": "info", "description": "Your insight here."}]"""
                num_s = {k: {"trend": v.get("trend","?"), "anomalies": v.get("anomaly_count",0)} for k, v in stats.items() if v.get("type") == "numeric"}
                usr_p = f"Stats summary:\n{json.dumps(num_s)}\n\nExisting raw algorithmic patterns:\n{json.dumps(patterns[:5])}"
                import re
                ai_resp = _groq_data_cleaner(sys_p, usr_p)
                if ai_resp:
                    match = re.search(r'\[[\s\S]*\]', ai_resp)
                    if match:
                        ai_patterns = json.loads(match.group())
                        for ap in ai_patterns:
                            if isinstance(ap, dict) and 'description' in ap:
                                patterns.append(ap)
            except Exception as e:
                pass # Non-critical fallback
                
        state["patterns"] = patterns
        state["agent_statuses"]["DataCleaner"] = "done"
        log_agent(sid,"DataCleaner","done",
                  f"Analysis complete: {len(num_keys)} numeric sensors. {len(patterns)} patterns detected.")

    except Exception as e:
        import traceback; traceback.print_exc()
        state["errors"].append(f"Analysis error: {e}")
        state["agent_statuses"]["DataCleaner"] = "error"

    return state
