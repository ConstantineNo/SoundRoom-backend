"""Native GUI adapter. Analysis always calls the shared service in a worker thread."""
from pathlib import Path
import json

import librosa
import numpy as np
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg
from pydantic import TypeAdapter

from app.schemas.audio_recognition import Annotation, RecognitionConfig
from app.services.audio_recognition import analyze, load_audio
from .devices import AudioDevices
from .export import export_result


class AnalysisWorker(QtCore.QThread):
    succeeded = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, audio, config, parent=None):
        super().__init__(parent)
        self.audio, self.config = audio, config

    def run(self):
        try:
            self.succeeded.emit(analyze(self.audio, self.config))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class RecognitionWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoundRoom · 单声部识别验证台")
        self.resize(1320, 920)
        self.audio = self.result = self.previous = self.worker = None
        self.annotations = []
        self.devices = AudioDevices()
        self.last_error = ""
        self.last_play_position = 0
        self.setStyleSheet("""
            QWidget {background:#142335; color:#e1eaf3; font-size:12px}
            QPushButton {background:#28445e; border:1px solid #45627e; border-radius:4px; padding:7px}
            QPushButton:hover {background:#355b7c}
            QPushButton:disabled {background:#1c2d40; color:#8394a6}
            QSpinBox, QDoubleSpinBox, QPlainTextEdit {background:#0d1826; color:#eef5fc;
                border:1px solid #496077; padding:3px}
            QCheckBox {spacing:6px}
        """)
        body = QtWidgets.QWidget()
        self.setCentralWidget(body)
        layout = QtWidgets.QVBoxLayout(body)
        bar = QtWidgets.QHBoxLayout()
        layout.addLayout(bar)
        self.open_button = self.button(bar, "导入音频", self.open_dialog)
        self.record_button = self.button(bar, "临时录制", self.toggle_record)
        self.analyze_button = self.button(bar, "分析 / 重新分析", self.start_analysis)
        self.export_button = self.button(bar, "导出结果", self.export_dialog)
        self.button(bar, "导入参数", self.params_dialog)
        self.button(bar, "导入标注", self.annotations_dialog)
        self.button(bar, "导出标注", self.export_annotations_dialog)
        split = QtWidgets.QSplitter()
        layout.addWidget(split, 1)
        settings = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(settings)
        self.controls = {}
        fields = [
            ("fmin", "最低 Hz", 40, 2000, 1), ("fmax", "最高 Hz", 80, 5000, 1),
            ("frame_length", "窗口样本", 512, 8192, 256), ("hop_length", "步长样本", 64, 2048, 16),
            ("sample_rate", "分析采样率", 8000, 48000, 1000),
            ("resolution", "pYIN 半音分辨率", .05, .5, .05),
            ("voiced_threshold", "发声概率门限", 0, 1, .05),
            ("silence_db", "能量门限 dBFS", -100, -6, 1),
            ("min_note_seconds", "最短音符 秒", .02, 1, .01),
            ("pitch_change_cents", "换音阈值 音分", 30, 300, 5),
            ("stable_seconds", "稳定窗口 秒", .02, .5, .01),
            ("onset_ratio", "再起音能量比", 1.5, 10, .25),
        ]
        defaults = RecognitionConfig().model_dump()
        for key, label, low, high, step in fields:
            widget = QtWidgets.QSpinBox() if isinstance(defaults[key], int) else QtWidgets.QDoubleSpinBox()
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setDecimals(3)
            widget.setRange(low, high)
            widget.setSingleStep(step)
            widget.setValue(defaults[key])
            widget.valueChanged.connect(self.params_changed)
            form.addRow(label, widget)
            self.controls[key] = widget
        self.compare = QtWidgets.QCheckBox("叠加上次结果（橙色）")
        self.compare.setChecked(True)
        self.compare.toggled.connect(self.render_result)
        form.addRow(self.compare)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        form.addRow(self.details)
        split.addWidget(settings)
        pg.setConfigOptions(antialias=True, background="#101c2b", foreground="#ccdbea")
        self.graphs = pg.GraphicsLayoutWidget()
        split.addWidget(self.graphs)
        split.setSizes([290, 1000])
        self.wave = self.graphs.addPlot(row=0, col=0, title="波形 · 拖动绿色选区；滚轮缩放；双击定位")
        self.spectrum = self.graphs.addPlot(row=1, col=0, title="频谱 · dB（固定色阶）")
        self.pitch = self.graphs.addPlot(row=2, col=0, title="F0 / 候选音符 · 青色当前 / 橙色上次 / 紫色人工标注")
        self.confidence = self.graphs.addPlot(row=3, col=0, title="发声概率（非正确率） / 起音强度")
        self.plots = [self.wave, self.spectrum, self.pitch, self.confidence]
        for plot in self.plots:
            plot.setLabel("bottom", "解码后音频时间", units="s")
            plot.showGrid(x=True, y=True, alpha=.15)
            if plot is not self.wave:
                plot.setXLink(self.wave)
        self.spectrum.setLabel("left", "Hz")
        self.pitch.setLabel("left", "Hz")
        self.region = pg.LinearRegionItem((0, 1), brush=(60, 200, 140, 40))
        self.wave.addItem(self.region)
        self.region.sigRegionChanged.connect(self.region_changed)
        self.graphs.scene().sigMouseClicked.connect(self.seek_click)
        playbar = QtWidgets.QHBoxLayout()
        layout.addLayout(playbar)
        self.play_button = self.button(playbar, "播放选区", self.play_selection)
        self.play_button.setToolTip("原声道回放；选区首尾各5毫秒淡入淡出，仅影响试听，不改变识别输入。")
        self.button(playbar, "停止回放", self.devices.stop_playback)
        self.loop = QtWidgets.QCheckBox("循环")
        playbar.addWidget(self.loop)
        self.begin = QtWidgets.QDoubleSpinBox()
        self.end = QtWidgets.QDoubleSpinBox()
        for spin in (self.begin, self.end):
            spin.setDecimals(3)
            spin.setRange(0, 60)
            spin.valueChanged.connect(self.range_changed)
        playbar.addWidget(QtWidgets.QLabel("起点 秒"))
        playbar.addWidget(self.begin)
        playbar.addWidget(QtWidgets.QLabel("终点 秒"))
        playbar.addWidget(self.end)
        self.button(playbar, "缩放选区", self.zoom_selection)
        self.button(playbar, "全览", self.fit_audio)
        self.annotation_hz = QtWidgets.QDoubleSpinBox()
        self.annotation_hz.setRange(20, 10000)
        self.annotation_hz.setValue(440)
        playbar.addWidget(self.annotation_hz)
        self.button(playbar, "以选区添加标注 Hz", self.add_annotation)
        self.button(playbar, "删除末条标注", self.remove_annotation)
        self.status = QtWidgets.QLabel("导入 WAV / FLAC / AIFF / OGG，或临时录制（最多60秒，仅驻留内存）。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.cursors = []
        self.reset_cursors()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(80)
        self.update_actions()

    def button(self, layout, text, callback):
        button = QtWidgets.QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def config(self):
        return RecognitionConfig(**{key: widget.value() for key, widget in self.controls.items()})

    def params_changed(self):
        if self.result is not None:
            self.status.setText("参数已改变；图中仍为上次分析结果，点击重新分析。")

    def update_actions(self):
        busy = self.worker is not None
        recording = self.devices.input_stream is not None
        self.open_button.setEnabled(not busy and not recording)
        self.record_button.setEnabled(not busy)
        self.record_button.setText("停止并使用录音" if recording else "临时录制")
        self.analyze_button.setEnabled(self.audio is not None and not busy and not recording)
        self.play_button.setEnabled(self.audio is not None and not recording)
        self.export_button.setEnabled(self.result is not None and not busy)

    def error(self, message):
        self.last_error = message
        self.status.setText(f"失败：{message}")

    def open_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "导入音频", "", "音频 (*.wav *.flac *.aiff *.ogg)")
        if path:
            self.import_file(Path(path))

    def import_file(self, path):
        try:
            self.set_audio(load_audio(path), Path(path).name)
        except Exception as exc:
            self.error(str(exc))

    def set_audio(self, audio, label="临时录音"):
        self.devices.stop_playback()
        self.audio = audio
        self.result = self.previous = None
        self.annotations = []
        self.last_error = ""
        self.wave.clear()
        y = audio.mono
        # Preserve extrema in display buckets instead of dropping narrow transients.
        stride = max(1, len(y) // 20000)
        size = len(y) // stride * stride
        chunks = y[:size].reshape(-1, stride)
        t = np.repeat(np.arange(len(chunks)) * stride / audio.info.sample_rate, 2)
        values = np.column_stack((chunks.min(axis=1), chunks.max(axis=1))).ravel()
        self.wave.plot(t, values, pen="#60c9d7")
        self.wave.addItem(self.region)
        duration = audio.info.duration_seconds
        self.region.setBounds((0, duration))
        self.region.setRegion((0, duration))
        self.begin.setMaximum(duration)
        self.end.setMaximum(duration)
        # A capped display sample rate keeps rendering short even for 60-second input.
        display = librosa.resample(y, orig_sr=audio.info.sample_rate, target_sr=8000)
        spec = np.abs(librosa.stft(display, n_fft=512, hop_length=128))
        db = 20 * np.log10(np.maximum(spec / 256, 1e-6))
        self.spectrum.clear()
        item = pg.ImageItem(db.T, axisOrder="col-major")
        item.setLookupTable(pg.colormap.get("viridis").getLookupTable())
        item.setLevels((-90, 0))
        item.setRect(QtCore.QRectF(-.008, 0, db.shape[1] * .016, 4000))
        self.spectrum.addItem(item)
        self.spectrum.setYRange(0, 2500)
        self.pitch.clear()
        self.confidence.clear()
        self.reset_cursors()
        self.details.setPlainText(f"{label}\n{audio.info.sample_rate} Hz / {audio.info.channels} ch\n{duration:.3f} s\n录音不随结果导出。")
        self.status.setText(f"已载入 {label}；点击分析。")
        if audio.peak == 0:
            self.status.setText(f"已载入 {label}，但数据全零；若为录音，请检查麦克风权限与输入设备。")
        self.fit_audio()
        self.update_actions()

    def toggle_record(self):
        try:
            if self.devices.input_stream is None:
                self.devices.start_capture()
                self.status.setText("录制中；停止后载入（仅内存）。")
            else:
                self.set_audio(self.devices.finish_capture())
        except Exception as exc:
            self.error(str(exc))
        self.update_actions()

    def start_analysis(self):
        if self.audio is None or self.worker is not None:
            return
        try:
            config = self.config()
        except ValueError as exc:
            self.error(str(exc))
            return
        self.last_error = ""
        self.worker = AnalysisWorker(self.audio, config, self)
        self.worker.succeeded.connect(self.analysis_ready)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.analysis_finished)
        self.status.setText("后台分析中（首次 pYIN 编译较慢）；仍可缩放与回放。")
        self.update_actions()
        self.worker.start()

    def analysis_ready(self, result):
        self.previous, self.result = self.result, result
        self.render_result()
        self.details.setPlainText(f"{len(result.notes)} 个候选音符\n{result.run.elapsed_seconds:.3f} 秒 / RTF {result.run.real_time_factor:.2f}\n"
                                  + "\n".join(result.warnings) + "\n\n本次参数：\n" + result.run.config.model_dump_json(indent=2))
        self.status.setText("分析完成；可选择片段、回放、修改参数再分析。光标仅为设备回放近似进度。")

    def analysis_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.update_actions()

    def render_result(self, *_):
        self.pitch.clear()
        self.confidence.clear()
        if self.result is not None:
            for result, color in [(self.previous if self.compare.isChecked() else None, "#efa34b"), (self.result, "#51decc")]:
                if result is None:
                    continue
                times = [f.time_seconds for f in result.frames]
                self.pitch.plot(times, [f.f0_hz if f.f0_hz is not None else np.nan for f in result.frames], pen=color, connect="finite")
            for note in self.result.notes:
                band = self.pitch.plot([note.start_seconds, note.end_seconds], [note.frequency_hz] * 2,
                                       pen=pg.mkPen((230, 240, 255, 70), width=7))
                band.setZValue(-1)
                line = pg.InfiniteLine(note.start_seconds, pen=pg.mkPen("#83a2bd", style=QtCore.Qt.PenStyle.DotLine))
                self.pitch.addItem(line)
            times = [f.time_seconds for f in self.result.frames]
            self.confidence.plot(times, [f.voiced_probability for f in self.result.frames], pen="#51decc")
            self.confidence.plot(times, [f.onset_strength for f in self.result.frames], pen="#efa34b")
            self.confidence.setYRange(0, 1)
        for annotation in self.annotations:
            self.pitch.plot([annotation.start_seconds, annotation.end_seconds], [annotation.frequency_hz] * 2,
                            pen=pg.mkPen("#dc87f3", width=4))
        self.reset_cursors()

    def reset_cursors(self):
        for plot, cursor in self.cursors:
            plot.removeItem(cursor)
        self.cursors = []
        for plot in self.plots:
            cursor = pg.InfiniteLine(0, pen=pg.mkPen("#f3d977", width=1))
            plot.addItem(cursor, ignoreBounds=True)
            self.cursors.append((plot, cursor))

    def region_changed(self):
        start, end = self.region.getRegion()
        for spin, value in ((self.begin, start), (self.end, end)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def range_changed(self):
        if self.end.value() > self.begin.value():
            self.region.setRegion((self.begin.value(), self.end.value()))

    def seek_click(self, event):
        if event.double() and self.audio is not None:
            point = self.wave.vb.mapSceneToView(event.scenePos())
            start = max(0, min(point.x(), self.audio.info.duration_seconds - .01))
            self.region.setRegion((start, self.audio.info.duration_seconds))

    def zoom_selection(self):
        self.wave.setXRange(*self.region.getRegion(), padding=.02)

    def fit_audio(self):
        if self.audio is not None:
            self.wave.setXRange(0, self.audio.info.duration_seconds, padding=.01)

    def play_selection(self):
        if self.audio is not None:
            try:
                self.devices.play(self.audio, *self.region.getRegion(), loop=self.loop.isChecked())
                self.status.setText("回放选区中（光标不是精确音符时钟）。")
            except Exception as exc:
                self.error(str(exc))

    def tick(self):
        if self.devices.input_stream is not None and not self.devices.input_stream.active:
            self.toggle_record()
        if self.devices.playing:
            position = self.devices.position / self.devices.play_rate
            self.last_play_position = position
            for _, cursor in self.cursors:
                cursor.setValue(position)
        if self.devices.status:
            self.status.setText(f"音频设备状态：{self.devices.status}")
        if self.devices.playback_error:
            self.error(self.devices.playback_error)

    def export_dialog(self):
        if self.result is not None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出结果（无音频）", "result.json", "JSON (*.json)")
            if path:
                try:
                    export_result(self.result, Path(path))
                    self.status.setText("已导出 JSON、帧/音符 CSV 和本次分析参数。")
                except OSError as exc:
                    self.error(str(exc))

    def params_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "导入参数", "", "JSON (*.json)")
        if path:
            try:
                config = RecognitionConfig.model_validate_json(Path(path).read_text())
                for key, widget in self.controls.items():
                    widget.setValue(getattr(config, key))
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def add_annotation(self):
        if self.audio is not None:
            try:
                start, end = self.region.getRegion()
                self.annotations.append(Annotation(start_seconds=start, end_seconds=end, frequency_hz=self.annotation_hz.value()))
                self.render_result()
            except ValueError as exc:
                self.error(str(exc))

    def remove_annotation(self):
        if self.annotations:
            self.annotations.pop()
            self.render_result()

    def load_annotations(self, path):
        annotations = TypeAdapter(list[Annotation]).validate_json(Path(path).read_text())
        if self.audio is None or any(a.end_seconds > self.audio.info.duration_seconds for a in annotations):
            raise ValueError("Annotations require loaded audio and must fit its duration")
        self.annotations = annotations
        self.render_result()

    def annotations_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "导入人工标注", "", "JSON (*.json)")
        if path:
            try:
                self.load_annotations(path)
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def save_annotations(self, path):
        Path(path).write_text(json.dumps([a.model_dump() for a in self.annotations], indent=2), encoding="utf-8")

    def export_annotations_dialog(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出人工标注", "annotations.json", "JSON (*.json)")
        if path:
            try:
                self.save_annotations(path)
            except OSError as exc:
                self.error(str(exc))

    def closeEvent(self, event):
        if self.worker is not None:
            self.status.setText("分析结束后可以关闭窗口。")
            event.ignore()
            return
        self.timer.stop()
        self.devices.close()
        self.audio = self.result = self.previous = None
        event.accept()
