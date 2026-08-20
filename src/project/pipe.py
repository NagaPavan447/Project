# pipe.py
import json
import os
import glob
import sqlite3
from project.Transcriber import process_stereo_call
from project.analyzer import analyze_transcript

def init_db(db_path="callradar.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            call_id TEXT PRIMARY KEY,
            customer_name TEXT,
            agent_name TEXT,
            timestamp TEXT,
            audio_path TEXT,
            transcript_json TEXT,
            analysis_json TEXT,
            attention_score INTEGER
        )
    """)
    conn.commit()
    return conn

def extract_meta_fields(meta: dict):
    # Support both flat metadata and nested CallRadar structure
    customer_name = (
        meta.get("customer_name")
        or meta.get("caller", {}).get("metadata", {}).get("first and last name")
        or meta.get("caller", {}).get("metadata", {}).get("caller_name")
        or "Unknown Customer"
    )
    agent_name = (
        meta.get("agent_name")
        or meta.get("agent", {}).get("metadata", {}).get("agent_name")
        or "Unknown Agent"
    )
    timestamp = str(
        meta.get("timestamp")
        or meta.get("start_time_ms")
        or ""
    )
    return customer_name, agent_name, timestamp

def run_ingestion(data_dir: str, db_path: str = "callradar.db", limit: int = None):
    conn = init_db(db_path)
    cursor = conn.cursor()
    
    audio_pattern = os.path.join(data_dir, "audio", "*.mp3")
    audio_files = glob.glob(audio_pattern)
    
    if not audio_files:
        print(f"No audio files found in: {audio_pattern}")
        return
        
    print(f"Found {len(audio_files)} audio file(s) in {data_dir}")
    if limit:
        audio_files = audio_files[:limit]
        
    processed_count = 0
    for i, audio_path in enumerate(audio_files, start=1):
        call_id = os.path.splitext(os.path.basename(audio_path))[0]
        meta_path = os.path.join(data_dir, "metadata", f"{call_id}.json")
        
        # Check if already processed
        cursor.execute("SELECT call_id FROM calls WHERE call_id = ?", (call_id,))
        if cursor.fetchone():
            print(f"[{i}/{len(audio_files)}] Skipping (already ingested): {call_id}")
            continue
            
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                try:
                    meta = json.load(f)
                except Exception as e:
                    print(f"Warning: Could not parse metadata for {call_id}: {e}")
                    
        customer_name, agent_name, timestamp = extract_meta_fields(meta)
        
        print(f"[{i}/{len(audio_files)}] Processing call: {call_id} (Customer: {customer_name}, Agent: {agent_name})...")
        try:
            turns = process_stereo_call(audio_path)
            analysis = analyze_transcript(turns, meta)
            
            cursor.execute("""
                INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                call_id, customer_name, agent_name,
                timestamp, audio_path, json.dumps(turns),
                analysis.model_dump_json(), analysis.needs_attention_score
            ))
            conn.commit()
            processed_count += 1
            print(f"  -> Ingested: {call_id} (Attention Score: {analysis.needs_attention_score}/100)")
        except Exception as e:
            print(f"  -> Error processing {call_id}: {e}")
            
    conn.close()
    print(f"\nIngestion complete. Added {processed_count} call(s) to database.")

if __name__ == "__main__":
    dataset_dir = r"c:\Users\nagap\Downloads\Documents\Audio\callradar-data"
    run_ingestion(dataset_dir, limit=1)