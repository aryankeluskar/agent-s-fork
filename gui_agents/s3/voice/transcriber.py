"""
Wispr Flow Transcriber

Handles speech transcription using Wispr Flow WebSocket API.
Provides high-quality dictation with context awareness.
"""

import asyncio
import base64
import io
import json
import os
import wave
from typing import Callable, List, Optional

import numpy as np

# Wispr Flow API configuration
WISPR_API_KEY = os.environ.get("WISPR_API_KEY")


class WisprTranscriber:
    """
    Handles speech transcription using Wispr Flow WebSocket API.
    Provides high-quality dictation with context awareness.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or WISPR_API_KEY
        self.ws_url = f"wss://platform-api.wisprflow.ai/api/v1/dash/ws?api_key=Bearer%20{self.api_key}"
        self.sample_rate = 16000
        self.channels = 1
        self.sample_width = 2  # 16-bit audio

    def _create_wav_chunk(self, pcm_data: bytes) -> str:
        """
        Convert raw PCM data to WAV format and return as base64.
        Wispr expects 16kHz, 16-bit, mono WAV audio.
        """
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)
        
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')

    def _calculate_volume(self, pcm_data: bytes) -> float:
        """Calculate normalized volume level from PCM data."""
        if not pcm_data:
            return 0.0
        audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array ** 2))
        # Normalize to 0-1 range
        return min(1.0, rms / 3000)

    async def transcribe_audio(
        self, 
        audio_frames: List[bytes], 
        on_partial: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Transcribe audio frames using Wispr Flow WebSocket API.
        
        Args:
            audio_frames: List of raw PCM audio bytes (16kHz, 16-bit, mono)
            on_partial: Optional callback for partial transcription updates
            
        Returns:
            Final transcription text
        """
        import websockets
        
        if not audio_frames:
            return ""

        # Combine all frames into single audio buffer
        combined_audio = b''.join(audio_frames)
        
        try:
            async with websockets.connect(self.ws_url) as ws:
                # Send auth message with context
                auth_message = {
                    "type": "auth",
                    "access_token": self.api_key,
                    "language": ["en"],
                    "context": {
                        "app": {
                            "name": "Agent-S Voice Assistant",
                            "type": "ai"
                        },
                        "dictionary_context": [
                            "Agent-S", "Jarvis", "Instagram", "YouTube", "Spotify",
                            "Chrome", "Safari", "Firefox", "Gmail", "Canvas"
                        ]
                    }
                }
                await ws.send(json.dumps(auth_message))
                
                # Wait for auth confirmation
                auth_response = await ws.recv()
                auth_data = json.loads(auth_response)
                
                if auth_data.get("status") != "auth":
                    print(f"Wispr auth failed: {auth_data}")
                    return ""
                
                # Prepare audio packets - send in chunks for streaming
                samples_per_packet = self.sample_rate  # 1 second
                bytes_per_packet = samples_per_packet * self.sample_width
                
                packets = []
                volumes = []
                
                for i in range(0, len(combined_audio), bytes_per_packet):
                    chunk = combined_audio[i:i + bytes_per_packet]
                    if len(chunk) > 0:
                        wav_b64 = self._create_wav_chunk(chunk)
                        packets.append(wav_b64)
                        volumes.append(self._calculate_volume(chunk))
                
                if not packets:
                    return ""
                
                # Send audio packets
                append_message = {
                    "type": "append",
                    "position": 0,
                    "audio_packets": {
                        "packets": packets,
                        "volumes": volumes,
                        "packet_duration": 1.0,
                        "audio_encoding": "wav",
                        "byte_encoding": "base64"
                    }
                }
                await ws.send(json.dumps(append_message))
                
                # Send commit to signal end of audio
                commit_message = {
                    "type": "commit",
                    "total_packets": len(packets)
                }
                await ws.send(json.dumps(commit_message))
                
                # Receive transcription results
                final_text = ""
                
                while True:
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        data = json.loads(response)
                        
                        if data.get("status") == "text":
                            text = data.get("body", {}).get("text", "")
                            is_final = data.get("final", False)
                            
                            if text:
                                if on_partial and not is_final:
                                    on_partial(text)
                                final_text = text
                            
                            if is_final:
                                break
                                
                        elif data.get("status") == "error":
                            print(f"Wispr error: {data}")
                            break
                            
                        elif data.get("status") == "info":
                            continue
                            
                    except asyncio.TimeoutError:
                        print("Wispr response timeout")
                        break
                
                return final_text.strip()
                
        except Exception as e:
            print(f"Wispr transcription error: {e}")
            return ""

    def transcribe_sync(
        self, 
        audio_frames: List[bytes], 
        on_partial: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Synchronous wrapper for transcribe_audio.
        Creates a new event loop if needed.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.transcribe_audio(audio_frames, on_partial)
                    )
                    return future.result(timeout=15)
            else:
                return loop.run_until_complete(
                    self.transcribe_audio(audio_frames, on_partial)
                )
        except RuntimeError:
            return asyncio.run(self.transcribe_audio(audio_frames, on_partial))
