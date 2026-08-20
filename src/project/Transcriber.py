# transcriber.py
import os
import av
import numpy as np
from faster_whisper import WhisperModel

model = WhisperModel("base.en", device="cuda" if os.environ.get("USE_GPU") else "cpu", compute_type="float32")

def decode_stereo_channels(audio_path: str, sampling_rate: int = 16000):
    """
    Decodes stereo audio into Left and Right float32 numpy arrays at 16kHz
    using PyAV (no external ffmpeg installation required).
    """
    container = av.open(audio_path)
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=sampling_rate)
    
    left_frames = []
    right_frames = []
    
    for frame in container.decode(audio=0):
        resampled_list = resampler.resample(frame)
        if resampled_list:
            for r in resampled_list:
                arr = r.to_ndarray()
                left_frames.append(arr[0])
                right_frames.append(arr[1])
                
    # Flush remaining frames from resampler
    flushed = resampler.resample(None)
    if flushed:
        for r in flushed:
            arr = r.to_ndarray()
            left_frames.append(arr[0])
            right_frames.append(arr[1])

    left_audio = np.concatenate(left_frames) if left_frames else np.array([], dtype=np.float32)
    right_audio = np.concatenate(right_frames) if right_frames else np.array([], dtype=np.float32)
    
    return left_audio, right_audio

def process_stereo_call(audio_path: str):
    # Split audio directly in-memory: Left = Agent (0), Right = Customer (1)
    left_audio, right_audio = decode_stereo_channels(audio_path)

    turns = []

    # Transcribe Agent (Left channel)
    agent_segments, _ = model.transcribe(left_audio, word_timestamps=True)
    for seg in agent_segments:
        text = seg.text.strip()
        if text:
            turns.append({
                "speaker": "Agent",
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": text
            })

    # Transcribe Customer (Right channel)
    customer_segments, _ = model.transcribe(right_audio, word_timestamps=True)
    for seg in customer_segments:
        text = seg.text.strip()
        if text:
            turns.append({
                "speaker": "Customer",
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": text
            })

    # Chronologically sort the conversation turns
    turns.sort(key=lambda x: x["start"])
    return turns

if __name__ == "__main__":
    sample_file = r"c:\Users\nagap\Downloads\Documents\Audio\callradar-data\audio\0a70acb6ef0c4e89.mp3"
    print(f"Processing call: {sample_file} ...")
    call_turns = process_stereo_call(sample_file)
    for turn in call_turns:
        print(f"[{turn['start']:>6.2f}s - {turn['end']:>6.2f}s] {turn['speaker']}: {turn['text']}")

