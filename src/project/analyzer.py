# analyzer.py
import os
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

class Evidence(BaseModel):
    timestamp_start: float = Field(description="Start time in seconds where evidence begins")
    timestamp_end: float = Field(description="End time in seconds where evidence ends")
    quote: str = Field(description="Exact verbatim words spoken from the transcript")

class MoodShift(BaseModel):
    initial_mood: str = Field(description="Starting mood (e.g., Neutral, Frustrated, Anxious)")
    final_mood: str = Field(description="Ending mood (e.g., Relieved, Angry, Satisfied)")
    shift_occurred: bool = Field(description="True if customer mood changed significantly during the call")
    shift_timestamp: Optional[float] = Field(default=None, description="Timestamp in seconds where the mood pivot occurred")
    evidence: Optional[Evidence] = Field(default=None, description="Quote and timestamp justifying the mood shift")

class CallIntelligence(BaseModel):
    category: str = Field(default="General Support", description="Primary topic category (e.g., 'Card Services', 'Checkbook Order', 'Account Inquiry', 'Fraud & Security', 'Fee Dispute', 'Transfer & Payments', 'General Support')")
    intent: str = Field(description="Core reason for the call (1-2 sentences)")
    intent_evidence: Evidence = Field(description="Exact quote establishing intent")
    mood_analysis: MoodShift = Field(description="Customer mood progression and pivot points")
    is_resolved: bool = Field(description="Whether the customer's issue was definitively resolved")
    resolution_evidence: Evidence = Field(description="Quote proving resolution or lack thereof")
    summary: str = Field(description="Concise summary strictly 40 words or fewer")
    needs_attention_score: int = Field(description="Score from 0-100 indicating manager escalation urgency")
    escalation_reasons: List[str] = Field(default_factory=list, description="Bullet points for why this call needs manager review")


# Prompt setup
ANALYZER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a rigorous QA Analyst for a consumer bank.
Analyze the provided timestamped call transcript. Every claim MUST be backed by exact quotes and timestamps.

Scoring Rules for 'needs_attention_score' (0-100):
- High scores (70-100): Unresolved issues, escalated frustration, agent compliance failure, repeated customer contacts.
- Medium scores (40-69): Resolved with high friction or long handle times.
- Low scores (0-39): Smooth, routine resolutions with satisfied customers.

Constraint: The summary MUST NOT exceed 40 words."""),
    ("human", "Metadata: {metadata}\n\nTranscript:\n{transcript}")
])

def analyze_transcript(transcript_turns: list, metadata: dict = None) -> CallIntelligence:
    if metadata is None:
        metadata = {}
        
    formatted_transcript = "\n".join(
        [f"[{t['start']}s - {t['end']}s] {t['speaker']}: {t['text']}" for t in transcript_turns]
    )
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(CallIntelligence)
    
    chain = ANALYZER_PROMPT | structured_llm
    return chain.invoke({"metadata": metadata, "transcript": formatted_transcript})

if __name__ == "__main__":
    from project.Transcriber import process_stereo_call
    
    sample_file = r"c:\Users\nagap\Downloads\Documents\Audio\callradar-data\audio\0a70acb6ef0c4e89.mp3"
    print("Transcribing audio...")
    turns = process_stereo_call(sample_file)
    
    print("\nAnalyzing call intelligence with OpenAI...")
    analysis = analyze_transcript(turns, metadata={"call_id": "0a70acb6ef0c4e89", "channel": "Phone"})
    
    print("\n=== Call Analysis Results ===")
    print(f"Summary: {analysis.summary}")
    print(f"Intent: {analysis.intent} (Evidence: \"{analysis.intent_evidence.quote}\" @ {analysis.intent_evidence.timestamp_start}s)")
    print(f"Resolved: {analysis.is_resolved}")
    print(f"Mood: {analysis.mood_analysis.initial_mood} -> {analysis.mood_analysis.final_mood}")
    print(f"Needs Attention Score: {analysis.needs_attention_score}/100")
    if analysis.escalation_reasons:
        print("Escalation Reasons:", analysis.escalation_reasons)