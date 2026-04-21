from database import log_agent
from agents.data_cleaner import _pretty


def agent_dashboard_builder(state):
    if not state.get("cleaned_data"):
        state["agent_statuses"]["DashboardBuilder"] = "error"
        return state

    sid = state["session_id"]
    log_agent(sid, "DashboardBuilder", "running", "Building your dashboard...")

    try:
        cd    = state["cleaned_data"]
        raw   = state["raw_data"]
        pats  = state.get("patterns", [])
        stats = cd.get("stats", {})
        num   = cd.get("numeric", {})
        bool_ = cd.get("boolean", {})
        str_  = cd.get("string", {})

        def _find_extremes(key):
            """Return (min_val, min_ts, max_val, max_ts) from the raw cleaned numeric data."""
            d    = num.get(key, {})
            vals = d.get("values", [])
            tss  = d.get("timestamps", [])
            if not vals:
                return None, None, None, None
            min_i = vals.index(min(vals))
            max_i = vals.index(max(vals))
            return (
                vals[min_i], tss[min_i] if min_i < len(tss) else None,
                vals[max_i], tss[max_i] if max_i < len(tss) else None,
            )

        # ── KPI Cards (numeric sensors) ──────────────────────────────────
        kpi_cards = []
        for k, v in stats.items():
            if v.get("type") != "numeric":
                continue
            mn_v, mn_ts, mx_v, mx_ts = _find_extremes(k)

            raw_data = []
            if k in num and "timestamps" in num[k] and "values" in num[k]:
                ts_all = num[k]["timestamps"]
                v_all  = num[k]["values"]
                total  = len(ts_all)
                MAX_PTS = 300   # enough resolution for any chart without browser lag
                if total <= MAX_PTS:
                    indices = range(total)
                else:
                    # Evenly space indices across the full range so no period is skipped
                    step = (total - 1) / (MAX_PTS - 1)
                    indices = [round(i * step) for i in range(MAX_PTS)]
                raw_data = [(ts_all[i], v_all[i]) for i in indices]

            kpi_cards.append({
                "key":           k,
                "label":         _pretty(k),
                "avg":           v["avg"],
                "min":           v["min"],
                "max":           v["max"],
                "std":           v["std"],
                "trend":         v.get("trend", "stable"),
                "anomaly_count": v.get("anomaly_count", 0),
                "count":         v["count"],
                "unit":          v.get("unit", ""),
                "min_ts":        mn_ts,
                "max_ts":        mx_ts,
                "raw_data":      raw_data,
            })
        kpi_cards = kpi_cards[:8]

        # ── Boolean Status Cards ─────────────────────────────────────────
        bool_cards = [
            {
                "key":         k,
                "label":       _pretty(k),
                "true_count":  v.get("true_count", 0),
                "false_count": v.get("false_count", 0),
                "true_pct":    round(v.get("true_count", 0) / max(v.get("count", 1), 1) * 100, 1),
                "last_value":  v.get("last_value", False),
                "count":       v.get("count", 0),
            }
            for k, v in stats.items() if v.get("type") == "boolean"
        ]

        # ── String / Categorical Cards ───────────────────────────────────
        string_cards = []
        for k, sc in str_.items():
            freq = sc.get("freq", {})
            top  = sorted(freq.items(), key=lambda x: -x[1])[:6]
            string_cards.append({
                "key":    k,
                "label":  _pretty(k),
                "latest": sc.get("latest", ""),
                "top":    [{"v": kk, "c": vv} for kk, vv in top],
                "total":  sc.get("count", 0),
                "unique": len(freq),
            })

        # ── Attribute Table ──────────────────────────────────────────────
        attr_table = [
            {
                "key":   k,
                "label": _pretty(k),
                "value": m.get("value", ""),
                "scope": m.get("scope", ""),
                "dtype": m.get("dtype", ""),
            }
            for k, m in cd.get("attr_stats", {}).items()
        ]

        # ── Assemble Final Dashboard Payload ─────────────────────────────
        state["dashboard_data"] = {
            "device_name":      raw["device_name"],
            "device_id":        raw["device_id"],
            "device_type":      raw.get("device_type", ""),
            "device_label":     raw.get("device_label", ""),
            "time_range_label": raw["time_range_label"],
            "fetched_at":       raw["fetched_at"],
            "kpi_cards":        kpi_cards,
            "bool_cards":       bool_cards,
            "string_cards":     string_cards,
            "attr_table":       attr_table,
            "patterns":         pats,
            "total_tele_keys":  len(raw.get("telemetry_keys", [])),
            "total_attr_keys":  len(raw.get("attribute_keys", [])),
            "total_points":     sum(
                d.get("count", 0) for d in stats.values() if d.get("type") == "numeric"
            ),
            "numeric_count":  len(cd.get("numeric_keys", [])),
            "boolean_count":  len(cd.get("boolean_keys", [])),
            "string_count":   len(cd.get("string_keys", [])),
        }

        state["agent_statuses"]["DashboardBuilder"] = "done"
        log_agent(
            sid, "DashboardBuilder", "done",
            f"Dashboard ready — {len(kpi_cards)} KPI cards, "
            f"{len(bool_cards)} status indicators, {len(string_cards)} data panels.",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        state["errors"].append(f"Dashboard build error: {e}")
        state["agent_statuses"]["DashboardBuilder"] = "error"

    return state
