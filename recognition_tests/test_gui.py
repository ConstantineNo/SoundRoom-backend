import time
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from app.services.audio_recognition import analyze, load_audio
from tools.recognition_lab.gui import RecognitionWindow
from tools.recognition_lab.synthetic import cases, write_case
from tools.recognition_lab.devices import AudioDevices


@pytest.fixture(scope='module')
def qt():
    app = QApplication.instance() or QApplication([])
    yield app


def wait_worker(window, qt):
    deadline = time.monotonic() + 120
    ticks = 0
    while window.worker is not None and time.monotonic() < deadline:
        qt.processEvents()
        ticks += 1
        time.sleep(.01)
    assert window.worker is None
    assert not window.last_error
    assert ticks > 1


def test_gui_shared_core_and_interactions(qt, tmp_path):
    path = write_case(cases()[0], tmp_path)
    window = RecognitionWindow()
    window.show()
    try:
        window.import_file(path)
        assert window.audio is not None
        window.start_analysis()
        wait_worker(window, qt)
        direct = analyze(load_audio(path), window.config())
        assert window.result.frames == direct.frames
        assert window.result.notes == direct.notes
        window.region.setRegion((.3, .8))
        window.zoom_selection()
        assert window.begin.value() == pytest.approx(.3)
        assert window.end.value() == pytest.approx(.8)
        window.add_annotation()
        target = tmp_path / 'annotations.json'
        window.save_annotations(target)
        window.remove_annotation()
        assert not window.annotations
        window.load_annotations(target)
        assert len(window.annotations) == 1
        window.controls['voiced_threshold'].setValue(.2)
        window.start_analysis()
        wait_worker(window, qt)
        assert window.previous is not None
        assert window.result.run.config.voiced_threshold == .2
        window.fit_audio()
        window.controls['fmin'].setValue(1800)
        window.controls['fmax'].setValue(1000)
        window.start_analysis()
        assert window.worker is None and window.last_error
    finally:
        window.close()
        qt.processEvents()


def test_recording_start_failure_clears_memory(monkeypatch):
    from tools.recognition_lab import devices
    monkeypatch.setattr(devices.sd, 'query_devices', lambda **_: {'default_samplerate': 48000})
    def fail(**kwargs):
        raise RuntimeError('microphone unavailable')
    monkeypatch.setattr(devices.sd, 'InputStream', fail)
    device = AudioDevices()
    with pytest.raises(RuntimeError):
        device.start_capture()
    assert device.capture is None and device.input_stream is None


class FakeStream:
    active = True
    def __init__(self, **kwargs):
        self.callback = kwargs['callback']
        self.closed = False
    def start(self):
        pass
    def stop(self):
        self.active = False
    abort = stop
    def close(self):
        self.closed = True


def test_capture_success_overflow_cleanup(monkeypatch):
    from tools.recognition_lab import devices
    monkeypatch.setattr(devices.sd, 'query_devices', lambda **_: {'default_samplerate': 8000})
    monkeypatch.setattr(devices.sd, 'InputStream', FakeStream)
    device = AudioDevices()
    device.start_capture()
    stream = device.input_stream
    stream.callback(np.ones((80, 1), np.float32) * .1, 80, None, '')
    audio = device.finish_capture()
    assert audio.info.samples == 80 and audio.info.sample_rate == 8000
    assert stream.closed and device.capture is None
    device.start_capture()
    device.input_stream.callback(np.zeros((80, 1), np.float32), 80, None, 'input overflow')
    with pytest.raises(ValueError, match='interrupted'):
        device.finish_capture()
    assert device.capture is None and device.input_stream is None


def test_playback_selection_and_loop(monkeypatch):
    from io import BytesIO
    import soundfile as sf
    from tools.recognition_lab import devices
    from app.services.audio_recognition import from_pcm

    class FakeNative:
        def __init__(self, wave, loop):
            self.wave, self.loop = wave, loop
            self.active, self.position_seconds, self.error = False, 0, ""
        def start(self):
            self.active = True
        def close(self):
            self.active = False

    monkeypatch.setattr(devices, 'NativePlayback', FakeNative)
    device = AudioDevices()
    audio = from_pcm(np.linspace(-.5, .5, 8000), 8000)
    device.play(audio, .1, .2, loop=True)
    stream = device.output_stream
    samples, sr = sf.read(BytesIO(stream.wave), dtype='float32')
    assert len(samples) == 800 and sr == 8000 and stream.loop
    np.testing.assert_array_equal(samples[40:-40], audio.mono[840:1560])
    assert samples[0] == samples[-1] == 0
    stream.position_seconds = .025
    assert device.position == 1000 and device.playing
    device.stop_playback()
    assert not stream.active and not device.playing and device.output_stream is None
    device.play(audio, .1, .2)
    assert not device.output_stream.loop
    device.output_stream.error = 'device disconnected'
    assert device.playback_error == 'device disconnected'
    device.close()


def test_playback_keeps_stereo_and_analysis_samples():
    from io import BytesIO
    import soundfile as sf
    from app.services.audio_recognition import from_pcm
    from tools.recognition_lab.playback import playback_wave
    source = np.column_stack((np.full(8000, .4), np.full(8000, -.2))).astype(np.float32)
    audio = from_pcm(source, 8000)
    original_mono = audio.mono.copy()
    source[:] = 0  # source ownership is independent of the caller
    wave, start, stop = playback_wave(audio, .1, .3)
    samples, rate = sf.read(BytesIO(wave), dtype='float32', always_2d=True)
    assert rate == 8000 and samples.shape == (1600, 2) and (start, stop) == (800, 2400)
    np.testing.assert_array_equal(samples[40:-40], audio.source_pcm[840:2360])
    np.testing.assert_array_equal(audio.mono, original_mono)
    assert np.max(np.abs(samples[0])) == np.max(np.abs(samples[-1])) == 0
    assert not audio.source_pcm.flags.writeable
    # The join between consecutive loops is zero on both sides, without dropped samples.
    looped = np.concatenate((samples, samples))
    assert np.max(abs(looped[1600] - looped[1599])) == 0
    with pytest.raises(ValueError, match='nonempty'):
        playback_wave(audio, .5, .4)


def test_playback_start_failure_releases_buffer(monkeypatch):
    from tools.recognition_lab import devices
    from app.services.audio_recognition import from_pcm
    instances = []
    class BrokenNative:
        def __init__(self, *args):
            self.closed = False
            instances.append(self)
        def start(self):
            raise RuntimeError('output unavailable')
        def close(self):
            self.closed = True
    monkeypatch.setattr(devices, 'NativePlayback', BrokenNative)
    device = AudioDevices()
    with pytest.raises(RuntimeError, match='output unavailable'):
        device.play(from_pcm(np.zeros(8000), 8000), 0, .5)
    assert instances[0].closed and device.output_stream is None and not device.playing
