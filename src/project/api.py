# api.py
import os
import json
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = "callradar.db"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="Call-Centre Radar API",
    description="API for Call-Centre speech intelligence, QA metrics, and manager escalation radar.",
    version="1.0.0"
)

# Enable CORS for external frontend or local dev tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------- Dashboard & Metrics Endpoints -----------------

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    """Get high-level executive summary metrics across all ingested calls."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), AVG(attention_score), AVG(duration_seconds) FROM calls")
    total_calls, avg_attention, avg_duration = cursor.fetchone()
    
    cursor.execute("SELECT analysis_json FROM calls")
    rows = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(DISTINCT customer_name) FROM calls")
    total_customers = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT agent_name) FROM calls")
    total_agents = cursor.fetchone()[0] or 0
    
    conn.close()
    
    resolved_count = 0
    high_urgency_count = 0
    
    for row in rows:
        try:
            analysis = json.loads(row["analysis_json"])
            if analysis.get("is_resolved"):
                resolved_count += 1
            if analysis.get("needs_attention_score", 0) >= 70:
                high_urgency_count += 1
        except Exception:
            pass
            
    total = total_calls or 0
    return {
        "total_calls": total,
        "total_customers": total_customers,
        "total_agents": total_agents,
        "avg_attention_score": round(avg_attention or 0, 1),
        "avg_handle_time_sec": round(avg_duration or 0, 1),
        "resolution_rate": round((resolved_count / total * 100), 1) if total > 0 else 0.0,
        "high_urgency_calls": high_urgency_count
    }

@app.get("/api/dashboard/attention-queue")
def get_attention_queue(
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(0, ge=0, le=100)
):
    """Retrieve prioritized manager escalation radar queue."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, agent_name, timestamp, attention_score, duration_seconds, category, analysis_json
        FROM calls
        WHERE attention_score >= ?
        ORDER BY attention_score DESC
        LIMIT ?
    """, (min_score, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        try:
            analysis = json.loads(r["analysis_json"])
            summary = analysis.get("summary", "")
            intent = analysis.get("intent", "")
            is_resolved = analysis.get("is_resolved", False)
            mood = analysis.get("mood_analysis", {})
            escalations = analysis.get("escalation_reasons", [])
            category = r["category"] or analysis.get("category", "General Support")
        except Exception:
            summary, intent, is_resolved, mood, escalations = "", "", False, {}, []
            category = r["category"] or "General Support"
            
        results.append({
            "call_id": r["call_id"],
            "customer": r["customer_name"],
            "agent": r["agent_name"],
            "timestamp": r["timestamp"],
            "duration_seconds": r["duration_seconds"] or 0.0,
            "category": category,
            "attention_score": r["attention_score"],
            "is_resolved": is_resolved,
            "intent": intent,
            "summary": summary,
            "mood": mood,
            "escalation_reasons": escalations
        })
        
    return results

@app.get("/api/dashboard/trending-issues")
def get_trending_issues():
    """Aggregate recurring complaint topics and issue categories across calls."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT category, analysis_json, attention_score FROM calls")
    rows = cursor.fetchall()
    conn.close()
    
    categories = {}
    total = len(rows)
    
    for r in rows:
        cat = r["category"]
        if not cat or cat == "None":
            try:
                analysis = json.loads(r["analysis_json"])
                cat = analysis.get("category", "General Support")
            except Exception:
                cat = "General Support"
                
        if cat not in categories:
            categories[cat] = {
                "category": cat,
                "count": 0,
                "resolved_count": 0,
                "total_attention": 0
            }
            
        categories[cat]["count"] += 1
        categories[cat]["total_attention"] += (r["attention_score"] or 0)
        try:
            analysis = json.loads(r["analysis_json"])
            if analysis.get("is_resolved"):
                categories[cat]["resolved_count"] += 1
        except Exception:
            pass
            
    trending = []
    for cat, data in categories.items():
        count = data["count"]
        trending.append({
            "category": cat,
            "count": count,
            "percentage": round((count / total * 100), 1) if total > 0 else 0,
            "avg_attention_score": round(data["total_attention"] / count, 1) if count > 0 else 0,
            "resolution_rate": round((data["resolved_count"] / count * 100), 1) if count > 0 else 0
        })
        
    trending.sort(key=lambda x: x["count"], reverse=True)
    return trending

# ----------------- Customer Endpoints -----------------

@app.get("/api/customers")
def get_customers(search: Optional[str] = None):
    """List all customers with their aggregate statistics and risk scores."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT customer_name, COUNT(*) as call_count, AVG(attention_score) as avg_score,
               MAX(timestamp) as last_call_timestamp
        FROM calls
        WHERE customer_name IS NOT NULL AND customer_name != ''
    """
    params = []
    if search:
        query += " AND customer_name LIKE ?"
        params.append(f"%{search}%")
        
    query += " GROUP BY customer_name ORDER BY call_count DESC, avg_score DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        "customer_name": r["customer_name"],
        "call_count": r["call_count"],
        "avg_attention_score": round(r["avg_score"] or 0, 1),
        "last_call_timestamp": r["last_call_timestamp"]
    } for r in rows]

@app.get("/api/customers/{customer_name}")
def get_customer_history(customer_name: str):
    """Retrieve full multi-call history and transcripts for a specific customer."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, agent_name, timestamp, audio_path, duration_seconds,
               category, attention_score, transcript_json, analysis_json
        FROM calls
        WHERE customer_name = ?
        ORDER BY timestamp ASC
    """, (customer_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise HTTPException(status_code=404, detail=f"No call history found for customer '{customer_name}'")
        
    calls = []
    for r in rows:
        try:
            transcript = json.loads(r["transcript_json"])
        except Exception:
            transcript = []
        try:
            intelligence = json.loads(r["analysis_json"])
        except Exception:
            intelligence = {}
            
        calls.append({
            "call_id": r["call_id"],
            "agent_name": r["agent_name"],
            "timestamp": r["timestamp"],
            "duration_seconds": r["duration_seconds"] or 0.0,
            "category": r["category"] or intelligence.get("category", "General Support"),
            "attention_score": r["attention_score"],
            "audio_url": f"/api/calls/{r['call_id']}/audio",
            "transcript": transcript,
            "intelligence": intelligence
        })
        
    return {
        "customer_name": customer_name,
        "total_calls": len(calls),
        "history": calls
    }

# ----------------- Agent Endpoints -----------------

@app.get("/api/agents")
def get_agents():
    """Retrieve per-agent performance scorecards (volume, handle times, resolution rates)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT agent_name, COUNT(*) as call_count, AVG(attention_score) as avg_score,
               AVG(duration_seconds) as avg_handle_time
        FROM calls
        WHERE agent_name IS NOT NULL AND agent_name != ''
        GROUP BY agent_name
        ORDER BY call_count DESC
    """)
    rows = cursor.fetchall()
    
    # Calculate resolution rate per agent
    cursor.execute("SELECT agent_name, analysis_json FROM calls")
    all_calls = cursor.fetchall()
    conn.close()
    
    resolved_by_agent = {}
    for r in all_calls:
        agent = r["agent_name"]
        if agent not in resolved_by_agent:
            resolved_by_agent[agent] = {"total": 0, "resolved": 0}
        resolved_by_agent[agent]["total"] += 1
        try:
            analysis = json.loads(r["analysis_json"])
            if analysis.get("is_resolved"):
                resolved_by_agent[agent]["resolved"] += 1
        except Exception:
            pass
            
    agents_summary = []
    for r in rows:
        agent = r["agent_name"]
        stats = resolved_by_agent.get(agent, {"total": 1, "resolved": 0})
        res_rate = round((stats["resolved"] / stats["total"] * 100), 1) if stats["total"] > 0 else 0.0
        
        agents_summary.append({
            "agent_name": agent,
            "call_volume": r["call_count"],
            "avg_handle_time_sec": round(r["avg_handle_time"] or 0, 1),
            "avg_attention_score": round(r["avg_score"] or 0, 1),
            "resolution_rate": res_rate
        })
        
    return agents_summary

@app.get("/api/agents/{agent_name}")
def get_agent_details(agent_name: str):
    """Get all calls and breakdown for a specific agent."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, timestamp, duration_seconds, category,
               attention_score, analysis_json
        FROM calls
        WHERE agent_name = ?
        ORDER BY attention_score DESC
    """, (agent_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
    calls = []
    for r in rows:
        try:
            analysis = json.loads(r["analysis_json"])
            summary = analysis.get("summary", "")
            is_resolved = analysis.get("is_resolved", False)
        except Exception:
            summary, is_resolved = "", False
            
        calls.append({
            "call_id": r["call_id"],
            "customer_name": r["customer_name"],
            "timestamp": r["timestamp"],
            "duration_seconds": r["duration_seconds"] or 0.0,
            "category": r["category"] or "General Support",
            "attention_score": r["attention_score"],
            "is_resolved": is_resolved,
            "summary": summary
        })
        
    return {
        "agent_name": agent_name,
        "total_calls": len(calls),
        "calls": calls
    }

# ----------------- Call Inspector & Search Endpoints -----------------

@app.get("/api/calls")
def list_calls(
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Search and filter calls across multiple criteria."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT call_id, customer_name, agent_name, timestamp, duration_seconds,
               category, attention_score, analysis_json
        FROM calls
        WHERE attention_score >= ?
    """
    params = [min_score]
    
    if category:
        query += " AND category = ?"
        params.append(category)
        
    if search:
        query += " AND (customer_name LIKE ? OR agent_name LIKE ? OR call_id LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
        
    query += " ORDER BY attention_score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        try:
            analysis = json.loads(r["analysis_json"])
            summary = analysis.get("summary", "")
            is_resolved = analysis.get("is_resolved", False)
            intent = analysis.get("intent", "")
        except Exception:
            summary, is_resolved, intent = "", False, ""
            
        results.append({
            "call_id": r["call_id"],
            "customer_name": r["customer_name"],
            "agent_name": r["agent_name"],
            "timestamp": r["timestamp"],
            "duration_seconds": r["duration_seconds"] or 0.0,
            "category": r["category"] or "General Support",
            "attention_score": r["attention_score"],
            "is_resolved": is_resolved,
            "intent": intent,
            "summary": summary
        })
        
    return results

@app.get("/api/calls/{call_id}")
def get_call_details(call_id: str):
    """Get full details including transcript turns and evidence citations for a single call."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, agent_name, timestamp, audio_path, duration_seconds,
               category, transcript_json, analysis_json, attention_score
        FROM calls
        WHERE call_id = ?
    """, (call_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Call '{call_id}' not found")
        
    try:
        transcript = json.loads(row["transcript_json"])
    except Exception:
        transcript = []
        
    try:
        intelligence = json.loads(row["analysis_json"])
    except Exception:
        intelligence = {}
        
    return {
        "call_id": row["call_id"],
        "customer_name": row["customer_name"],
        "agent_name": row["agent_name"],
        "timestamp": row["timestamp"],
        "audio_path": row["audio_path"],
        "audio_url": f"/api/calls/{row['call_id']}/audio",
        "duration_seconds": row["duration_seconds"] or 0.0,
        "category": row["category"] or intelligence.get("category", "General Support"),
        "attention_score": row["attention_score"],
        "transcript": transcript,
        "intelligence": intelligence
    }

@app.get("/api/calls/{call_id}/audio")
def stream_call_audio(call_id: str):
    """Stream the call MP3 audio file."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT audio_path FROM calls WHERE call_id = ?", (call_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not row["audio_path"]:
        raise HTTPException(status_code=404, detail=f"Audio for call '{call_id}' not found")
        
    audio_path = row["audio_path"]
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
        
    return FileResponse(audio_path, media_type="audio/mpeg", filename=os.path.basename(audio_path))

# ----------------- Static Web Dashboard Serving -----------------

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.api:app", host="127.0.0.1", port=8000, reload=True, app_dir="src")

