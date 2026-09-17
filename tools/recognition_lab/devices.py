"""Bounded in-memory capture and playback; no persistent microphone recordings."""
import threading
import numpy as np
import sounddevice as sd

from app.services.audio_recognition.audio import MAX_SECONDS, from_pcm
from .playback import NativePlayback, playback_wave


class AudioDevices:
    def __init__(self):
        self.input_stream = None
        self.output_stream = None
        self.capture = None
        self.captured = 0
        self.capture_rate = 48000
        self.status = ""
        self.play_begin = 0
        self.play_end = 0
        self.play_rate = 1
        self.lock = threading.Lock()

    @property
    def playing(self):
        return self.output_stream is not None and self.output_stream.active

    @property
    def position(self):
        if self.output_stream is None:
            return self.play_begin
        return min(self.play_end, self.play_begin + round(self.output_stream.position_seconds * self.play_rate))

    @property
    def playback_error(self):
        return self.output_stream.error if self.output_stream is not None else ""

    def start_capture(self):
        self.stop_playback()
        if self.input_stream is not None:
            return
        rate = int(sd.query_devices(kind="input")["default_samplerate"])
        self.capture_rate = rate
        self.capture = np.empty((rate * MAX_SECONDS, 1), np.float32)
        self.captured = 0
        self.status = ""

        def callback(indata, frames, timing, status):
            if status:
                self.status = str(status)
            with self.lock:
                size = min(frames, len(self.capture) - self.captured)
                self.capture[self.captured:self.captured + size] = indata[:size]
                self.captured += size
                full = self.captured == len(self.capture)
            if full:
                raise sd.CallbackStop

        stream = None
        try:
            stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", callback=callback)
            stream.start()
            self.input_stream = stream
        except Exception:
            if stream is not None:
                stream.close()
            self.capture = None
            raise

    def finish_capture(self):
        try:
            if self.input_stream is None:
                raise ValueError("No recording in progress")
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None
            with self.lock:
                samples = self.capture[:self.captured].copy()
            if self.status:
                raise ValueError(f"Capture was interrupted ({self.status}); please record again")
            return from_pcm(samples, self.capture_rate)
        finally:
            self.discard_capture()

    def discard_capture(self):
        try:
            if self.input_stream is not None:
                self.input_stream.abort()
                self.input_stream.close()
        finally:
            self.input_stream = None
            self.capture = None
            self.captured = 0

    def play(self, audio, begin: float, end: float, loop: bool = False):
        self.stop_playback()
        if self.input_stream is not None:
            raise ValueError("Stop recording before playback")
        wave, start, stop = playback_wave(audio, begin, end)
        self.play_begin, self.play_end, self.play_rate = start, stop, audio.info.sample_rate
        self.status = ""
        stream = None
        try:
            stream = NativePlayback(wave, loop)
            stream.start()
            self.output_stream = stream
        except Exception:
            if stream is not None:
                stream.close()
            raise

    def stop_playback(self):
        try:
            if self.output_stream is not None:
                self.output_stream.close()
        finally:
            self.output_stream = None

    def close(self):
        try:
            self.stop_playback()
        finally:
            self.discard_capture()
