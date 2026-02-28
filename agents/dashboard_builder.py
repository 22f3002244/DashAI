from datetime import datetime
from database import log_agent
from agents.data_cleaner import _pretty
# A vibrant qualitative color palette
COLORS = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#14b8a6", "#f43f5e", "#6366f1"]

def _build_chartjs(chart_type, keys, cd):
    num   = cd.get("numeric", {})
    stats = cd.get("stats", {})
    bool_ = cd.get("boolean", {})
    str_  = cd.get("string", {})

    if chart_type in ("line","bar","scatter"):
        datasets = []; labels = []
        for ci, key in enumerate(keys[:4]):
            if key not in num: continue
            d = num[key]; vals = d["values"]; tss = d["timestamps"]
            if not labels and tss:
                labels = [datetime.fromtimestamp(t/1000).strftime("%d/%m %H:%M") for t in tss]
            c = COLORS[ci % len(COLORS)]
            ds = {"label": _pretty(key),
                  "data": vals if chart_type != "scatter" else [{"x":i,"y":v} for i,v in enumerate(vals)],
                  "borderColor": c, "backgroundColor": c+"18" if chart_type=="line" else c+"cc",
                  "borderWidth": 1.5, "pointRadius": 0 if len(vals)>80 else 2,
                  "fill": chart_type=="line", "tension": 0.35}
            datasets.append(ds)
        if not datasets: return None
        sc = {"x": {"ticks": {"color":"#bbb","maxTicksLimit":8,"font":{"size":10}}, "grid": {"color":"#f5f5f5"}},
              "y": {"ticks": {"color":"#bbb","font":{"size":10}},                   "grid": {"color":"#f5f5f5"}}}
        return {"type": chart_type, "data": {"labels": labels, "datasets": datasets}, "options": {
            "responsive": True, "maintainAspectRatio": False,
            "plugins": {"legend": {"display": len(datasets)>1, "labels": {"color":"#000","font":{"size":11}}},
                        "tooltip": {"mode":"index","intersect":False}},
            "scales": sc if chart_type in ("line","bar") else {}}}

    if chart_type == "doughnut":
        key = keys[0] if keys else None
        if key and key in bool_:
            b = bool_[key]; tc = sum(1 for e in b["events"] if e["value"]); fc = len(b["events"])-tc
            return {"type":"doughnut","data":{"labels":["ON","OFF"],
                "datasets":[{"data":[tc,fc],"backgroundColor":["#10b981","#e5e7eb"],"borderWidth":0}]},
                "options":{"responsive":True,"maintainAspectRatio":False,"cutout":"65%",
                "plugins":{"legend":{"position":"bottom","labels":{"color":"#000","font":{"size":11}}}}}}
        if key and key in str_:
            freq = str_[key]["freq"]; top = sorted(freq.items(), key=lambda x:-x[1])[:6]
            if not top: return None
            ls, vs = zip(*top)
            return {"type":"doughnut","data":{"labels":list(ls),
                "datasets":[{"data":list(vs),"backgroundColor":COLORS[:len(vs)],"borderWidth":0}]},
                "options":{"responsive":True,"maintainAspectRatio":False,"cutout":"65%",
                "plugins":{"legend":{"position":"bottom","labels":{"color":"#000","font":{"size":11}}}}}}
        return None

    if chart_type in ("radar","polarArea"):
        sv = []; sk2 = []
        for key in keys:
            s = stats.get(key, {})
            if s.get("type") == "numeric" and s.get("max",0) != 0:
                mn, mx, avg = s.get("min",0), s.get("max",1), s.get("avg",0)
                norm = ((avg-mn)/(mx-mn)*100) if mx != mn else 50
                sv.append(round(norm,1)); sk2.append(_pretty(key))
        if len(sk2) < 3: return None
        return {"type": chart_type, "data": {"labels": sk2, "datasets": [{
            "label": "Normalised (0-100%)", "data": sv,
            "backgroundColor": "#3b82f633", "borderColor": "#3b82f6", "borderWidth": 2,
            "pointBackgroundColor": "#3b82f6", "pointRadius": 3}]},
            "options": {"responsive": True, "maintainAspectRatio": False,
            "plugins": {"legend": {"display": False}},
            "scales": {"r": {"ticks": {"color":"#ccc","font":{"size":10}}, "grid": {"color":"#f0f0f0"}}}}}

    return None

def agent_dashboard_builder(state):
    if not state.get("cleaned_data"):
        state["agent_statuses"]["DashboardBuilder"] = "error"; return state

    sid = state["session_id"]
    log_agent(sid, "DashboardBuilder", "running", "Building your dashboard...")

    try:
        cd   = state["cleaned_data"]
        raw  = state["raw_data"]
        recs = sorted(state.get("viz_recommendations",[]), key=lambda x: x.get("priority",99))
        pats = state.get("patterns",[])
        stats = cd.get("stats",{})
        num   = cd.get("numeric",{})
        bool_ = cd.get("boolean",{})
        str_  = cd.get("string",{})

        kpi_cards = [{"key":k,"label":_pretty(k),
                      "avg":v["avg"],"min":v["min"],"max":v["max"],"std":v["std"],
                      "trend":v.get("trend","stable"),"anomaly_count":v.get("anomaly_count",0),
                      "count":v["count"],"unit":v.get("unit","")}
                     for k,v in stats.items() if v.get("type")=="numeric"][:8]

        bool_cards = [{"key":k,"label":_pretty(k),
                       "true_count":v.get("true_count",0),"false_count":v.get("false_count",0),
                       "true_pct":round(v.get("true_count",0)/max(v.get("count",1),1)*100,1),
                       "last_value":v.get("last_value",False),"count":v.get("count",0)}
                      for k,v in stats.items() if v.get("type")=="boolean"]

        string_cards = []
        for k, sc in str_.items():
            freq = sc.get("freq",{}); top = sorted(freq.items(), key=lambda x:-x[1])[:6]
            string_cards.append({"key":k,"label":_pretty(k),"latest":sc.get("latest",""),
                                  "top":[{"v":kk,"c":vv} for kk,vv in top],
                                  "total":sc.get("count",0),"unique":len(freq)})

        chart_blocks = []; seen = set()
        for rec in recs[:10]:
            ct  = rec.get("type","line"); ks = rec.get("keys",[])
            cid = rec.get("id", f"c{len(chart_blocks)}")
            if cid in seen: cid += f"_{len(chart_blocks)}"
            seen.add(cid)
            title = rec.get("title","Chart"); desc = rec.get("description","")

            if ct == "kpi":
                k = ks[0] if ks else None; s = stats.get(k,{}) if k else {}
                if s.get("type") == "numeric":
                    chart_blocks.append({"render_type":"kpi_single","id":cid,"title":title,"desc":desc,
                                         "key":k,"value":s.get("avg"),"unit":s.get("unit",""),
                                         "trend":s.get("trend","stable"),"count":s.get("count",0)})
                continue

            if ct == "boolean_status":
                k = ks[0] if ks else None; b = bool_.get(k); s = stats.get(k,{})
                if b:
                    tc = s.get("true_count",0); tot = max(s.get("count",1),1)
                    chart_blocks.append({"render_type":"boolean_status","id":cid,"title":title,"desc":desc,
                                         "key":k,"true_pct":round(tc/tot*100,1),
                                         "false_pct":round((tot-tc)/tot*100,1),
                                         "last_value":s.get("last_value",False)})
                continue

            if ct == "string_freq":
                k = ks[0] if ks else None; sc = str_.get(k)
                if sc:
                    freq = sc.get("freq",{}); top = sorted(freq.items(), key=lambda x:-x[1])[:8]
                    if top:
                        ls2, vs2 = zip(*top)
                        cfg = {"type":"bar","data":{"labels":list(ls2),
                            "datasets":[{"label":"Count","data":list(vs2),"backgroundColor":COLORS[0],"borderWidth":0}]},
                            "options":{"responsive":True,"maintainAspectRatio":False,"indexAxis":"y",
                            "plugins":{"legend":{"display":False}},
                            "scales":{"x":{"ticks":{"color":"#bbb","font":{"size":10}},"grid":{"color":"#f5f5f5"}},
                                      "y":{"ticks":{"color":"#333","font":{"size":11}},"grid":{"display":False}}}}}
                        chart_blocks.append({"render_type":"chartjs","id":cid,"title":title,"desc":desc,
                                             "chart_type":"bar","config":cfg})
                continue

            cfg = _build_chartjs(ct, ks, cd)
            if cfg:
                chart_blocks.append({"render_type":"chartjs","id":cid,"title":title,"desc":desc,
                                     "chart_type":ct,"config":cfg})

        attr_table = [{"key":k,"label":_pretty(k),"value":m.get("value",""),
                       "scope":m.get("scope",""),"dtype":m.get("dtype","")}
                      for k,m in cd.get("attr_stats",{}).items()]

        state["dashboard_data"] = {
            "device_name":raw["device_name"],"device_id":raw["device_id"],
            "device_type":raw.get("device_type",""),"device_label":raw.get("device_label",""),
            "time_range_label":raw["time_range_label"],"fetched_at":raw["fetched_at"],
            "kpi_cards":kpi_cards,"bool_cards":bool_cards,"string_cards":string_cards,
            "chart_blocks":chart_blocks,"attr_table":attr_table,"patterns":pats,
            "total_tele_keys":len(raw.get("telemetry_keys",[])),
            "total_attr_keys":len(raw.get("attribute_keys",[])),
            "total_points":sum(d.get("count",0) for d in stats.values() if d.get("type")=="numeric"),
            "numeric_count":len(cd.get("numeric_keys",[])),
            "boolean_count":len(cd.get("boolean_keys",[])),
            "string_count":len(cd.get("string_keys",[])),
        }
        state["agent_statuses"]["DashboardBuilder"] = "done"
        log_agent(sid,"DashboardBuilder","done",
                  f"Dashboard ready with {len(kpi_cards)} KPI cards, {len(chart_blocks)} charts, "
                  f"{len(bool_cards)} status indicators, and {len(string_cards)} data panels.")

    except Exception as e:
        import traceback; traceback.print_exc()
        state["errors"].append(f"Dashboard build error: {e}")
        state["agent_statuses"]["DashboardBuilder"] = "error"

    return state
