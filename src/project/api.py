# api.py
import os
import json
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

DB_PATH = "callradar.db"

app = FastAPI(
    title="Call-Centre Radar API",
    description="API for Call-Centre speech intelligence, QA metrics, and manager escalation radar.",
    version="1.0.0"
)

# Enable CORS for frontend integrations
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

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Call-Centre Radar API",
        "docs_url": "/docs"
    }

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    """Get high-level summary metrics across all ingested calls."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), AVG(attention_score) FROM calls")
    total_calls, avg_attention = cursor.fetchone()
    
    cursor.execute("SELECT analysis_json FROM calls")
    rows = cursor.fetchall()
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
        "avg_attention_score": round(avg_attention or 0, 1),
        "resolution_rate": round((resolved_count / total * 100), 1) if total > 0 else 0.0,
        "high_urgency_calls": high_urgency_count
    }

@app.get("/api/dashboard/attention-queue")
def get_attention_queue(
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(0, ge=0, le=100)
):
    """Retrieve calls prioritized by manager attention score."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, agent_name, timestamp, attention_score, analysis_json
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
        except Exception:
            summary, intent, is_resolved, mood = "", "", False, {}
            
        results.append({
            "call_id": r["call_id"],
            "customer": r["customer_name"],
            "agent": r["agent_name"],
            "timestamp": r["timestamp"],
            "attention_score": r["attention_score"],
            "is_resolved": is_resolved,
            "intent": intent,
            "summary": summary,
            "mood": mood
        })
        
    return results

@app.get("/api/calls/{call_id}")
def get_call_details(call_id: str):
    """Get full details including transcript turns and intelligence analysis for a single call."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT call_id, customer_name, agent_name, timestamp, audio_path, transcript_json, analysis_json, attention_score
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
        "attention_score": row["attention_score"],
        "transcript": transcript,
        "intelligence": intelligence
    }

@app.get("/api/calls/{call_id}/audio")
def stream_call_audio(call_id: str):
    """Stream or download the call MP3 audio file."""
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.api:app", host="127.0.0.1", port=8000, reload=True)
