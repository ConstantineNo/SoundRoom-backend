"""Qt's native audio renderer consumes a QBuffer; no Python real-time callback."""
from io import BytesIO

import numpy as np
import soundfile as sf
from PySide6 import QtCore, QtMultimedia


def playback_wave(audio, begin: float, end: float) -> tuple[bytes, int, int]:
    """Copy a selection with 5 ms edge fades, keeping original channels and timing.

    The envelope affects monitoring only. Analysis PCM and exported results are unchanged.
    """
    rate = audio.info.sample_rate
    start = max(0, round(begin * rate))
    stop = min(audio.info.samples, round(end * rate))
    if stop <= start:
        raise ValueError("Select a nonempty playback range")
    samples = audio.source_pcm[start:stop].copy()
    fade = min(round(.005 * rate), len(samples) // 2)
    if fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    output = BytesIO()
    sf.write(output, samples, rate, format="WAV", subtype="FLOAT")
    return output.getvalue(), start, stop


class NativePlayback:
    def __init__(self, wave: bytes, loop: bool):
        if QtCore.QCoreApplication.instance() is None:
            raise RuntimeError("Native playback requires a running Qt application")
        self.player = QtMultimedia.QMediaPlayer(QtCore.QCoreApplication.instance())
        self.output = QtMultimedia.QAudioOutput(self.player)
        self.buffer = QtCore.QBuffer(self.player)
        self.buffer.setData(QtCore.QByteArray(wave))
        self.buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
        self.player.setAudioOutput(self.output)
        self.player.setLoops(QtMultimedia.QMediaPlayer.Loops.Infinite if loop else 1)
        self.player.setSourceDevice(self.buffer, QtCore.QUrl("memory.wav"))

    @property
    def active(self) -> bool:
        return self.player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState

    @property
    def position_seconds(self) -> float:
        return self.player.position() / 1000

    @property
    def error(self) -> str:
        return self.player.errorString()

    def start(self):
        self.player.play()

    def close(self):
        self.player.stop()
        # Release player + child buffer together in Qt's event loop. Synchronous
        # setSourceDevice(None) can deadlock PySide 6.9.2 while the renderer thread
        # runs QAudioOutput.disconnectNotify and waits for Python's GIL.
        # The application parent retains native ownership until deferred deletion.
        self.player.deleteLater()
