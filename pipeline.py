import hashlib
import time
from typing import TypedDict, List, Dict, Optional

from database import get_db, log_agent
from agents.data_fetcher import agent_data_fetcher
from agents.data_cleaner import agent_data_cleaner
from agents.viz_recommender import agent_viz_recommender
from agents.dashboard_builder import agent_dashboard_builder

class AgentState(TypedDict, total=False):
    session_id: str
    tb_host: str
    tb_token: str
    device_id: str
    device_name: str
    time_range: str
    raw_data: Dict
    cleaned_data: Dict
    patterns: List[Dict]
    viz_recommendations: List[Dict]
    dashboard_data: Dict
    errors: List[str]
    warnings: List[str]
    agent_statuses: Dict[str, str]

def run_pipeline(tb_host, tb_token, device_id, time_range) -> AgentState:
    sid = hashlib.md5(f"{tb_token}{device_id}{time.time()}".encode()).hexdigest()[:12]
    c = get_db()
    c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)",
              (sid, time.time(), tb_host, device_id, time_range))
    c.commit(); c.close()

    state: AgentState = {
        "session_id": sid, "tb_host": tb_host, "tb_token": tb_token,
        "device_id": device_id, "time_range": time_range,
        "raw_data": {}, "cleaned_data": {}, "patterns": [],
        "viz_recommendations": [], "dashboard_data": {},
        "errors": [], "warnings": [],
        "agent_statuses": {
            "DataFetcher": "pending", "DataCleaner": "pending",
            "VizRecommender": "pending", "DashboardBuilder": "pending",
        },
    }
    state = agent_data_fetcher(state)
    state = agent_data_cleaner(state)
    state = agent_viz_recommender(state)
    state = agent_dashboard_builder(state)
    return state
