"""Exercise the actual visible window and physical playback; capture is opt-in."""
from .runtime import configure_runtime
configure_runtime()
import argparse
import json
from pathlib import Path
import time
from PySide6 import QtCore, QtWidgets
import sounddevice as sd
import shiboken6
from .gui import RecognitionWindow
from .synthetic import cases, write_case
from .export import export_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--record-seconds', type=float, default=0)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--play-seconds', type=float, default=1.4)
    parser.add_argument('--stress', action='store_true', help='Hold the main Python thread for 20ms between GUI updates')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    window = RecognitionWindow()
    window.show()
    report = {'window_visible': window.isVisible(), 'steps': [], 'devices': str(sd.query_devices())}
    playback_positions = []

    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            if window.devices.playing:
                playback_positions.append(window.devices.position / window.devices.play_rate)
            if args.stress:
                busy_until = time.monotonic() + .02
                while time.monotonic() < busy_until:
                    pass
            time.sleep(.01)

    def wait():
        deadline = time.monotonic() + 120
        while window.worker is not None and time.monotonic() < deadline:
            pump(.05)
        if window.worker is not None or window.last_error:
            raise RuntimeError(window.last_error or 'analysis timeout')

    try:
        path = args.input or write_case(cases()[0], args.output)
        window.import_file(path)
        window.analyze_button.click()
        wait()
        assert window.result is not None
        report['steps'].append('file_import_and_background_analysis')
        first_frames = window.result.frames
        window.region.setRegion((.25, .85))
        window.zoom_selection()
        pump(.4)
        report['steps'].append('selection_and_zoom')
        window.loop.setChecked(True)
        window.play_button.click()
        pump(args.play_seconds)
        report['physical_playback'] = {'active': window.devices.playing, 'cursor_seconds': window.last_play_position,
                                       'error': window.last_error or window.devices.playback_error, 'device_status': window.devices.status,
                                       'source_channels': window.audio.info.channels, 'main_thread_stress': args.stress,
                                       'observed_loop_wraps': sum(b < a for a, b in zip(playback_positions, playback_positions[1:]))}
        assert report['physical_playback']['active'], report['physical_playback']
        assert not report['physical_playback']['error'], report['physical_playback']
        player = window.devices.output_stream.player
        window.devices.stop_playback()
        pump(.05)
        assert not shiboken6.isValid(player), 'Qt player must release source buffer after deferred deletion'
        report['steps'].append('native_player_and_memory_buffer_released')
        window.controls['voiced_threshold'].setValue(.2)
        window.analyze_button.click()
        wait()
        assert window.previous.frames == first_frames
        report['steps'].append('parameter_rerun_and_previous_overlay')
        window.add_annotation()
        window.save_annotations(args.output / 'annotations.json')
        window.load_annotations(args.output / 'annotations.json')
        export_result(window.result, args.output / 'result.json')
        report['steps'].append('annotation_and_result_exports')
        window.fit_audio()
        pump(.4)
        window.grab().save(str(args.output / 'window.png'))
        if args.record_seconds > 0:
            window.record_button.click()
            pump(args.record_seconds)
            started = window.devices.input_stream is not None
            if started:
                window.record_button.click()
            report['microphone'] = {'started': started, 'error': window.last_error,
                                    'duration_seconds': window.audio.info.duration_seconds if started else None,
                                    'peak': window.audio.peak if started else None}
        else:
            report['microphone'] = 'not requested'
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        (args.output / 'smoke.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
        if window.worker is not None:
            window.worker.wait()
            app.processEvents()
        window.close()
        app.processEvents()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
