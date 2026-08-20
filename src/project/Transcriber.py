# transcriber.py
from pydub import AudioSegment
from faster_whisper import WhisperModel
import os

model = WhisperModel("base.en", device="cuda" if os.environ.get("USE_GPU") else "cpu", compute_type="float32")

def process_stereo_call(audio_path: str):
    sound = AudioSegment.from_file(audio_path)
    channels = sound.split_to_mono()
    
    # Left = Agent (0), Right = Customer (1)
    agent_path = "/tmp/agent_temp.wav"
    customer_path = "/tmp/customer_temp.wav"
    channels[0].export(agent_path, format="wav")
    channels[1].export(customer_path, format="wav")

    turns = []
    
    # Transcribe Agent
    agent_segments, _ = model.transcribe(agent_path, word_timestamps=True)
    for seg in agent_segments:
        turns.append({
            "speaker": "Agent",
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip()
        })

    # Transcribe Customer
    customer_segments, _ = model.transcribe(customer_path, word_timestamps=True)
    for seg in customer_segments:
        turns.append({
            "speaker": "Customer",
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip()
        })

    # Chronologically sort the conversation turns
    turns.sort(key=lambda x: x["start"])
    return turns