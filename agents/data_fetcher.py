import requests
from database import log_agent
from config import get_time_bounds

def tb_headers(token):
    return {"X-Authorization": f"Bearer {token}"}

def tb_get(host, token, path, params=None, timeout=30):
    r = requests.get(f"{host}{path}", headers=tb_headers(token), params=params, timeout=timeout)
    return r

def agent_data_fetcher(state):
    sid = state["session_id"]
    log_agent(sid, "DataFetcher", "running", "Connecting to ThingsBoard and fetching data...")

    try:
        host   = state["tb_host"]
        token  = state["tb_token"]
        dev_id = state["device_id"]
        start_ts, end_ts = get_time_bounds(state["time_range"])

        r = tb_get(host, token, f"/api/device/{dev_id}")
        if r.status_code == 401:
            state["errors"].append("Session expired. Please log in again.")
            state["agent_statuses"]["DataFetcher"] = "error"; return state
        if r.status_code == 404:
            state["errors"].append("Device not found. It may have been deleted.")
            state["agent_statuses"]["DataFetcher"] = "error"; return state
        if r.status_code != 200:
            state["errors"].append(f"Could not load device (HTTP {r.status_code}).")
            state["agent_statuses"]["DataFetcher"] = "error"; return state

        dev    = r.json()
        d_name = dev.get("name", dev_id)
        d_type = dev.get("type", "")
        d_label = dev.get("label", "")
        log_agent(sid, "DataFetcher", "running", f"Found device: '{d_name}'")

        r2 = tb_get(host, token, f"/api/plugins/telemetry/DEVICE/{dev_id}/keys/timeseries")
        tele_keys = r2.json() if r2.status_code == 200 else []

        r3 = tb_get(host, token, f"/api/plugins/telemetry/DEVICE/{dev_id}/keys/attributes")
        attr_keys = r3.json() if r3.status_code == 200 else []

        log_agent(sid, "DataFetcher", "running",
                  f"Discovered {len(tele_keys)} sensor readings, {len(attr_keys)} device attributes.")

        telemetry = {}
        if tele_keys:
            batch = tele_keys[:20]
            from config import TIME_RANGES
            r4 = tb_get(host, token, f"/api/plugins/telemetry/DEVICE/{dev_id}/values/timeseries",
                        params={"keys": ",".join(batch),
                                "startTs": start_ts, "endTs": end_ts,
                                "limit": 1000, "agg": "NONE"}, timeout=60)
            if r4.status_code == 200:
                telemetry = r4.json()
                pts = sum(len(v) for v in telemetry.values())
                log_agent(sid, "DataFetcher", "running",
                          f"Retrieved {pts:,} data points across {len(telemetry)} sensors.")
            else:
                state["warnings"].append(f"Could not fetch sensor readings (HTTP {r4.status_code}).")

        attributes = {}
        for scope in ("client", "server", "shared"):
            r5 = tb_get(host, token, f"/api/plugins/telemetry/DEVICE/{dev_id}/values/attributes/{scope}")
            if r5.status_code == 200:
                for a in r5.json():
                    attributes[a.get("key", "")] = {
                        "value": a.get("value"), "scope": scope,
                        "lastUpdateTs": a.get("lastUpdateTs")}
        if not attributes:
            r6 = tb_get(host, token, f"/api/plugins/telemetry/DEVICE/{dev_id}/values/attributes")
            if r6.status_code == 200:
                for a in r6.json():
                    attributes[a.get("key", "")] = {
                        "value": a.get("value"), "scope": "device",
                        "lastUpdateTs": a.get("lastUpdateTs")}

        from config import TIME_RANGES
        from datetime import datetime
        state["raw_data"] = {
            "device_id": dev_id, "device_name": d_name,
            "device_type": d_type, "device_label": d_label,
            "time_range": state["time_range"],
            "time_range_label": TIME_RANGES[state["time_range"]][0],
            "start_ts": start_ts, "end_ts": end_ts,
            "telemetry_keys": tele_keys, "attribute_keys": attr_keys,
            "telemetry": telemetry, "attributes": attributes,
            "fetched_at": datetime.now().isoformat(),
        }
        state["agent_statuses"]["DataFetcher"] = "done"
        log_agent(sid, "DataFetcher", "done",
                  f"Fetch complete: {len(telemetry)} sensor types, {len(attributes)} attributes.")

    except requests.exceptions.ConnectionError:
        state["errors"].append(f"Cannot reach '{state['tb_host']}'. Check the server address.")
        state["agent_statuses"]["DataFetcher"] = "error"
    except requests.exceptions.Timeout:
        state["errors"].append("Connection timed out. The server may be slow or offline.")
        state["agent_statuses"]["DataFetcher"] = "error"
    except Exception as e:
        import traceback; traceback.print_exc()
        state["errors"].append(f"Error fetching data: {e}")
        state["agent_statuses"]["DataFetcher"] = "error"

    return state
