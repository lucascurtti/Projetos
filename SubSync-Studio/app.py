from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import time
from dataclasses import replace
from importlib.metadata import version, PackageNotFoundError

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QSlider, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.argos_engine import ArgosError, install_en_pt_model, model_installed, translate_srt
from core.ollama_engine import OllamaError, choose_default_model, improve_subtitle, list_models
from core.subtitles import (
    SubtitleEntry, apply_safe_fixes, find_entry_at, match_reference_entry,
    quick_review, read_srt, write_srt,
)
from core.sync_engine import SyncError, make_output_path, sync_subtitle


APP_VERSION = "0.5.0"
VIDEO_FILTER = "Vídeos (*.mkv *.mp4 *.avi *.mov *.webm *.m4v);;Todos os arquivos (*.*)"
SRT_FILTER = "Legendas SRT (*.srt);;Todos os arquivos (*.*)"


class DropLineEdit(QLineEdit):
    def __init__(self, suffixes: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.suffixes = tuple(s.lower() for s in suffixes)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            p = urls[0].toLocalFile().lower()
            if not self.suffixes or p.endswith(self.suffixes):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        self.setText(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


class FilePicker(QWidget):
    changed = Signal(str)

    def __init__(self, title: str, file_filter: str, suffixes: tuple[str, ...], optional: bool = False):
        super().__init__()
        self.file_filter = file_filter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = title + (" — opcional" if optional else "")
        layout.addWidget(QLabel(f"<b>{header}</b>"))
        row = QHBoxLayout()
        self.edit = DropLineEdit(suffixes)
        self.edit.setPlaceholderText("Arraste um arquivo aqui ou clique em Procurar")
        self.edit.textChanged.connect(self.changed.emit)
        browse = QPushButton("Procurar")
        browse.clicked.connect(self.browse)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        if optional:
            clear = QPushButton("Limpar")
            clear.clicked.connect(self.edit.clear)
            row.addWidget(clear)
        layout.addLayout(row)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo", "", self.file_filter)
        if path:
            self.edit.setText(path)

    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, path: str):
        self.edit.setText(path)


class SyncWorker(QThread):
    progress = Signal(int)
    done = Signal(str, dict, float)
    failed = Signal(str)

    def __init__(self, video: str, srt: str, mode: str, safe: bool):
        super().__init__()
        self.video, self.srt, self.mode, self.safe = video, srt, mode, safe

    def run(self):
        started = time.perf_counter()
        try:
            out, result = sync_subtitle(
                self.video, self.srt, mode=self.mode, safe=self.safe,
                progress_callback=lambda f: self.progress.emit(int(f * 100)),
            )
            self.done.emit(str(out), result, time.perf_counter() - started)
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelInstallWorker(QThread):
    status = Signal(str)
    done = Signal()
    failed = Signal(str)

    def run(self):
        try:
            install_en_pt_model(self.status.emit)
            self.done.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    done = Signal(str, str, float)
    failed = Signal(str)

    def __init__(self, video: str, english_srt: str, sync_first: bool, normalize: bool, mode: str, safe: bool):
        super().__init__()
        self.video = video
        self.english_srt = english_srt
        self.sync_first = sync_first
        self.normalize = normalize
        self.mode = mode
        self.safe = safe

    def run(self):
        started = time.perf_counter()
        try:
            source = Path(self.english_srt)
            synced_path = ""
            if self.sync_first:
                if not self.video:
                    raise ValueError("Selecione o vídeo para sincronizar antes da tradução.")
                self.status.emit("Sincronizando a legenda em inglês...")
                synced, _ = sync_subtitle(
                    self.video, source, mode=self.mode, safe=self.safe,
                    progress_callback=lambda f: self.progress.emit(int(f * 35)),
                )
                source = synced
                synced_path = str(synced)
            else:
                self.progress.emit(35)

            output = source.with_name(source.stem.replace(".sincronizada", "") + ".pt-BR.srt")
            counter = 2
            base = output
            while output.exists():
                output = base.with_name(f"{base.stem}-{counter}{base.suffix}")
                counter += 1

            self.status.emit("Traduzindo offline com Argos Translate...")
            translate_srt(
                source,
                output,
                ptbr_normalization=self.normalize,
                progress_callback=lambda i, total: self.progress.emit(35 + int((i / max(total, 1)) * 65)),
            )
            self.progress.emit(100)
            self.done.emit(str(output), synced_path, time.perf_counter() - started)
        except Exception as exc:
            self.failed.emit(str(exc))


class AIWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, current: str, previous: str, following: str, english: str, model: str):
        super().__init__()
        self.args = (current, previous, following, english, model)

    def run(self):
        try:
            current, previous, following, english, model = self.args
            self.done.emit(improve_subtitle(current, previous, following, english, model))
        except Exception as exc:
            self.failed.emit(str(exc))


class PlayerDialog(QDialog):
    def __init__(self, video_path: str, srt_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Testar sincronização — SubSync Studio")
        self.resize(960, 680)
        self.entries = read_srt(srt_path) if srt_path and Path(srt_path).exists() else []
        self.dragging = False

        layout = QVBoxLayout(self)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(430)
        layout.addWidget(self.video, 1)
        self.subtitle = QLabel(" ")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setMinimumHeight(54)
        self.subtitle.setStyleSheet("font-size: 18px; font-weight: 600; padding: 8px; background: #0d1117;")
        layout.addWidget(self.subtitle)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.audio.setVolume(0.75)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶ Reproduzir")
        self.play_btn.clicked.connect(self.toggle_play)
        back = QPushButton("−10 s")
        back.clicked.connect(lambda: self.seek_relative(-10_000))
        forward = QPushButton("+10 s")
        forward.clicked.connect(lambda: self.seek_relative(10_000))
        controls.addWidget(back)
        controls.addWidget(self.play_btn)
        controls.addWidget(forward)
        self.time_label = QLabel("00:00 / 00:00")
        controls.addWidget(self.time_label)
        controls.addStretch(1)
        self.jump = QLineEdit()
        self.jump.setPlaceholderText("15:30 ou 01:15:30")
        self.jump.setMaximumWidth(150)
        go = QPushButton("Ir para")
        go.clicked.connect(self.go_to_time)
        controls.addWidget(self.jump)
        controls.addWidget(go)
        layout.addLayout(controls)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(lambda: setattr(self, "dragging", True))
        self.slider.sliderReleased.connect(self.slider_released)
        layout.addWidget(self.slider)

        quick = QHBoxLayout()
        for label, frac in (("Início", 0.0), ("25%", .25), ("50%", .50), ("75%", .75), ("90%", .90)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=frac: self.seek_fraction(f))
            quick.addWidget(btn)
        quick.addStretch(1)
        layout.addLayout(quick)

        self.player.durationChanged.connect(self.on_duration)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_play)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self.seek_relative(-5_000))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.seek_relative(5_000))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def on_state(self, state):
        self.play_btn.setText("⏸ Pausar" if state == QMediaPlayer.PlayingState else "▶ Reproduzir")

    def on_duration(self, duration: int):
        self.slider.setRange(0, max(duration, 0))

    def on_position(self, position: int):
        if not self.dragging:
            self.slider.setValue(position)
        duration = self.player.duration()
        self.time_label.setText(f"{self.pretty(position)} / {self.pretty(duration)}")
        entry = find_entry_at(self.entries, position)
        self.subtitle.setText(entry.text.replace("\n", "<br>") if entry else " ")

    def slider_released(self):
        self.dragging = False
        self.player.setPosition(self.slider.value())

    def seek_relative(self, delta: int):
        self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + delta)))

    def seek_fraction(self, frac: float):
        if self.player.duration() > 0:
            self.player.setPosition(int(self.player.duration() * frac))

    def go_to_time(self):
        parts = self.jump.text().strip().split(":")
        try:
            nums = [int(p) for p in parts]
            if len(nums) == 2:
                sec = nums[0] * 60 + nums[1]
            elif len(nums) == 3:
                sec = nums[0] * 3600 + nums[1] * 60 + nums[2]
            else:
                raise ValueError
            self.player.setPosition(sec * 1000)
        except ValueError:
            QMessageBox.warning(self, "Tempo inválido", "Use MM:SS ou HH:MM:SS.")

    @staticmethod
    def pretty(ms: int) -> str:
        sec = max(0, ms // 1000)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SubSync Studio {APP_VERSION}")
        self.resize(980, 820)
        self.sync_output = ""
        self.translation_output = ""
        self.review_entries: list[SubtitleEntry] = []
        self.review_reference: list[SubtitleEntry] = []
        self.review_source_path = ""
        self.worker = None
        self.player_dialog = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("SubSync Studio")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Sincronização, tradução offline e revisão leve de legendas.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        self.engine_status = QLabel()
        layout.addWidget(self.engine_status)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_sync_tab(), "Sincronizar")
        self.tabs.addTab(self.build_translate_tab(), "Traduzir EN → PT-BR")
        self.tabs.addTab(self.build_review_tab(), "Revisão rápida")
        layout.addWidget(self.tabs, 1)

        activity_header = QHBoxLayout()
        activity_header.addWidget(QLabel("<b>Atividade</b>"))
        activity_header.addStretch(1)
        clear = QPushButton("Limpar")
        clear.clicked.connect(lambda: self.log.clear())
        activity_header.addWidget(clear)
        layout.addLayout(activity_header)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(125)
        layout.addWidget(self.log)

        self.refresh_status()
        self.apply_style()

    def build_sync_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w); layout.setSpacing(14)
        self.sync_video = FilePicker("Vídeo", VIDEO_FILTER, (".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v"))
        self.sync_srt = FilePicker("Legenda", SRT_FILTER, (".srt",))
        layout.addWidget(self.sync_video); layout.addWidget(self.sync_srt)

        box = QGroupBox("Configuração")
        grid = QGridLayout(box)
        self.sync_mode = QComboBox()
        self.sync_mode.addItem("Padrão — recomendado", "standard")
        self.sync_mode.addItem("Várias regiões — mais rápido em vídeos longos", "multi")
        self.sync_mode.addItem("Cortes/cenas diferentes — experimental", "cuts")
        self.sync_safe = QCheckBox("Evitar resultado de baixa confiança")
        self.sync_safe.setChecked(True)
        grid.addWidget(QLabel("Modo de sincronização"), 0, 0)
        grid.addWidget(self.sync_mode, 1, 0)
        grid.addWidget(QLabel("Segurança"), 0, 1)
        grid.addWidget(self.sync_safe, 1, 1)
        grid.setColumnStretch(0, 2); grid.setColumnStretch(1, 1)
        layout.addWidget(box)

        self.sync_btn = QPushButton("Sincronizar legenda")
        self.sync_btn.setObjectName("primary")
        self.sync_btn.clicked.connect(self.start_sync)
        layout.addWidget(self.sync_btn)
        self.sync_progress = QProgressBar(); self.sync_progress.setValue(0)
        layout.addWidget(self.sync_progress)
        self.sync_result = QLabel("Pronto para sincronizar.")
        layout.addWidget(self.sync_result)
        row = QHBoxLayout(); row.addStretch(1)
        self.sync_test = QPushButton("Testar no vídeo"); self.sync_test.setEnabled(False); self.sync_test.clicked.connect(self.test_sync)
        folder = QPushButton("Abrir pasta de saída"); folder.clicked.connect(lambda: self.open_output_folder(self.sync_output))
        row.addWidget(self.sync_test); row.addWidget(folder); layout.addLayout(row)
        layout.addStretch(1)
        return w

    def build_translate_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w); layout.setSpacing(14)
        info = QLabel("Fluxo leve: sincroniza a legenda em inglês (opcional) e traduz localmente com Argos. Não usa IA para o filme inteiro.")
        info.setWordWrap(True); info.setObjectName("muted"); layout.addWidget(info)
        self.tr_video = FilePicker("Vídeo", VIDEO_FILTER, (".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v"), optional=True)
        self.tr_srt = FilePicker("Legenda original em inglês", SRT_FILTER, (".srt",))
        layout.addWidget(self.tr_video); layout.addWidget(self.tr_srt)

        opts = QGroupBox("Tradução")
        form = QGridLayout(opts)
        self.tr_sync = QCheckBox("Sincronizar com o vídeo antes de traduzir")
        self.tr_sync.setChecked(True)
        self.tr_ptbr = QCheckBox("Aplicar ajustes leves de vocabulário para PT-BR")
        self.tr_ptbr.setChecked(True)
        self.tr_mode = QComboBox(); self.tr_mode.addItem("Padrão", "standard"); self.tr_mode.addItem("Várias regiões", "multi"); self.tr_mode.addItem("Cortes/cenas diferentes", "cuts")
        self.tr_safe = QCheckBox("Evitar sincronização de baixa confiança"); self.tr_safe.setChecked(True)
        form.addWidget(self.tr_sync, 0, 0, 1, 2)
        form.addWidget(self.tr_ptbr, 1, 0, 1, 2)
        form.addWidget(QLabel("Modo de sincronização"), 2, 0); form.addWidget(self.tr_mode, 3, 0)
        form.addWidget(QLabel("Segurança"), 2, 1); form.addWidget(self.tr_safe, 3, 1)
        form.setColumnStretch(0, 2); form.setColumnStretch(1, 1)
        layout.addWidget(opts)

        model_row = QHBoxLayout()
        self.argos_status = QLabel()
        model_row.addWidget(self.argos_status, 1)
        self.argos_btn = QPushButton("Instalar modelo EN → PT")
        self.argos_btn.clicked.connect(self.install_argos)
        model_row.addWidget(self.argos_btn)
        layout.addLayout(model_row)

        self.tr_btn = QPushButton("Traduzir + sincronizar")
        self.tr_btn.setObjectName("primary"); self.tr_btn.clicked.connect(self.start_translation)
        layout.addWidget(self.tr_btn)
        self.tr_progress = QProgressBar(); layout.addWidget(self.tr_progress)
        self.tr_result = QLabel("Aguardando arquivos."); layout.addWidget(self.tr_result)
        row = QHBoxLayout(); row.addStretch(1)
        self.tr_test = QPushButton("Testar no vídeo"); self.tr_test.setEnabled(False); self.tr_test.clicked.connect(self.test_translation)
        row.addWidget(self.tr_test); layout.addLayout(row)
        layout.addStretch(1)
        self.update_argos_status()
        return w

    def build_review_tab(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w); layout.setSpacing(12)
        info = QLabel(
            "Esta versão não revisa o filme inteiro com IA. A checagem rápida é instantânea e a IA local só é chamada quando você escolhe um trecho específico."
        )
        info.setWordWrap(True); info.setObjectName("muted"); layout.addWidget(info)
        self.rv_srt = FilePicker("Legenda PT-BR", SRT_FILTER, (".srt",))
        self.rv_en = FilePicker("Legenda original em inglês", SRT_FILTER, (".srt",), optional=True)
        layout.addWidget(self.rv_srt); layout.addWidget(self.rv_en)

        buttons = QHBoxLayout()
        scan = QPushButton("Executar revisão rápida"); scan.setObjectName("primary"); scan.clicked.connect(self.run_quick_review)
        safe = QPushButton("Aplicar correções seguras"); safe.clicked.connect(self.apply_review_safe_fixes)
        save = QPushButton("Salvar versão revisada"); save.clicked.connect(self.save_review)
        buttons.addWidget(scan); buttons.addWidget(safe); buttons.addWidget(save); buttons.addStretch(1)
        layout.addLayout(buttons)

        self.rv_table = QTableWidget(0, 4)
        self.rv_table.setHorizontalHeaderLabels(["Tempo", "Categoria", "Problema", "Texto"])
        self.rv_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rv_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rv_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rv_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.rv_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.rv_table, 1)

        ai_box = QGroupBox("Melhorar somente o trecho selecionado com IA local — opcional")
        ai = QHBoxLayout(ai_box)
        ai.addWidget(QLabel("Modelo Ollama:"))
        self.model_combo = QComboBox(); ai.addWidget(self.model_combo, 1)
        refresh = QPushButton("Atualizar modelos"); refresh.clicked.connect(self.refresh_models); ai.addWidget(refresh)
        self.ai_btn = QPushButton("Revisar trecho selecionado"); self.ai_btn.clicked.connect(self.improve_selected); ai.addWidget(self.ai_btn)
        layout.addWidget(ai_box)
        self.rv_status = QLabel("Nenhuma revisão executada."); layout.addWidget(self.rv_status)
        self.refresh_models()
        return w

    def apply_style(self):
        self.setStyleSheet("""
        QWidget { background: #0f1218; color: #f2f4f8; font-size: 13px; }
        QLabel#title { font-size: 28px; font-weight: 800; }
        QLabel#muted { color: #aab2c0; }
        QGroupBox { border: 1px solid #2b3340; border-radius: 12px; margin-top: 10px; padding: 12px; font-weight: 700; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        QLineEdit, QComboBox, QTextEdit, QTableWidget { background: #0b0e13; border: 1px solid #30394a; border-radius: 8px; padding: 8px; }
        QComboBox { min-height: 24px; }
        QPushButton { background: #202735; border: 1px solid #30394a; border-radius: 9px; padding: 9px 14px; }
        QPushButton:hover { background: #293244; }
        QPushButton#primary { background: #6673ff; color: white; font-weight: 700; border: none; min-height: 24px; }
        QPushButton#primary:hover { background: #7480ff; }
        QPushButton:disabled { color: #747d8e; background: #1b202b; }
        QProgressBar { border: 1px solid #30394a; border-radius: 7px; text-align: center; background: #1a202b; min-height: 15px; }
        QProgressBar::chunk { background: #6673ff; border-radius: 6px; }
        QTabWidget::pane { border: 1px solid #29313e; border-radius: 12px; top: -1px; }
        QTabBar::tab { background: #171c25; padding: 10px 16px; margin-right: 4px; border-radius: 8px 8px 0 0; }
        QTabBar::tab:selected { background: #252c3a; font-weight: 700; }
        QHeaderView::section { background: #171c25; padding: 7px; border: none; font-weight: 700; }
        """)

    def log_line(self, text: str):
        self.log.append(text)

    def refresh_status(self):
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        try:
            ffs_version = version("ffsubsync")
        except PackageNotFoundError:
            ffs_version = None
        if ffmpeg_ok and ffs_version:
            self.engine_status.setText(f"✓ Motor pronto: FFmpeg + FFsubsync {ffs_version}")
            self.engine_status.setStyleSheet("color: #5ee59b;")
        else:
            missing = []
            if not ffmpeg_ok: missing.append("FFmpeg")
            if not ffs_version: missing.append("FFsubsync")
            self.engine_status.setText("⚠ Falta: " + ", ".join(missing))
            self.engine_status.setStyleSheet("color: #ffbf69;")

    def update_argos_status(self):
        try:
            ready = model_installed()
        except Exception:
            ready = False
        self.argos_status.setText("✓ Modelo EN → PT instalado e offline" if ready else "Modelo EN → PT ainda não instalado (download único).")
        self.argos_status.setStyleSheet("color: #5ee59b;" if ready else "color: #ffbf69;")
        self.argos_btn.setText("Modelo instalado" if ready else "Instalar modelo EN → PT")
        self.argos_btn.setEnabled(not ready)

    def install_argos(self):
        self.argos_btn.setEnabled(False)
        self.worker = ModelInstallWorker()
        self.worker.status.connect(lambda s: (self.argos_status.setText(s), self.log_line(s)))
        self.worker.done.connect(lambda: (self.update_argos_status(), self.log_line("✓ Modelo Argos instalado.")))
        self.worker.failed.connect(lambda e: (QMessageBox.critical(self, "Erro", e), self.update_argos_status()))
        self.worker.start()

    def start_sync(self):
        video, srt = self.sync_video.path(), self.sync_srt.path()
        if not Path(video).exists() or not Path(srt).exists():
            QMessageBox.warning(self, "Arquivos", "Selecione um vídeo e uma legenda válidos."); return
        self.sync_btn.setEnabled(False); self.sync_progress.setValue(0); self.sync_result.setText("Sincronizando...")
        self.log_line(f"Sincronizando: {Path(srt).name}")
        self.worker = SyncWorker(video, srt, self.sync_mode.currentData(), self.sync_safe.isChecked())
        self.worker.progress.connect(self.sync_progress.setValue)
        self.worker.done.connect(self.sync_done)
        self.worker.failed.connect(self.worker_failed)
        self.worker.start()

    def sync_done(self, output: str, result: dict, elapsed: float):
        self.sync_output = output; self.sync_btn.setEnabled(True); self.sync_test.setEnabled(True); self.sync_progress.setValue(100)
        offset = result.get("offset_seconds")
        factor = result.get("framerate_scale_factor")
        details = [f"Concluído em {elapsed:.1f}s"]
        if offset is not None: details.append(f"offset {float(offset):+.3f}s")
        if factor is not None: details.append(f"framerate ×{float(factor):.6f}")
        self.sync_result.setText(" • ".join(details))
        self.log_line(f"✓ Legenda salva: {output}")
        QMessageBox.information(self, "Sincronização concluída", f"Legenda salva em:\n{output}")

    def worker_failed(self, message: str):
        self.sync_btn.setEnabled(True); self.tr_btn.setEnabled(True)
        self.sync_result.setText("Falha no processamento."); self.tr_result.setText("Falha no processamento.")
        self.log_line("✗ " + message)
        QMessageBox.critical(self, "Erro", message)

    def start_translation(self):
        srt = self.tr_srt.path(); video = self.tr_video.path()
        if not Path(srt).exists():
            QMessageBox.warning(self, "Legenda", "Selecione uma legenda em inglês válida."); return
        if self.tr_sync.isChecked() and not Path(video).exists():
            QMessageBox.warning(self, "Vídeo", "Selecione o vídeo ou desmarque a sincronização antes da tradução."); return
        if not model_installed():
            QMessageBox.information(self, "Modelo necessário", "Instale primeiro o modelo EN → PT pelo botão desta aba."); return
        self.tr_btn.setEnabled(False); self.tr_progress.setValue(0); self.tr_result.setText("Iniciando...")
        self.worker = TranslateWorker(video, srt, self.tr_sync.isChecked(), self.tr_ptbr.isChecked(), self.tr_mode.currentData(), self.tr_safe.isChecked())
        self.worker.progress.connect(self.tr_progress.setValue)
        self.worker.status.connect(lambda s: (self.tr_result.setText(s), self.log_line(s)))
        self.worker.done.connect(self.translation_done)
        self.worker.failed.connect(self.worker_failed)
        self.worker.start()

    def translation_done(self, output: str, synced_en: str, elapsed: float):
        self.translation_output = output; self.tr_btn.setEnabled(True); self.tr_progress.setValue(100)
        self.tr_test.setEnabled(bool(self.tr_video.path()))
        self.tr_result.setText(f"Tradução concluída em {elapsed:.1f}s — {Path(output).name}")
        self.log_line(f"✓ PT-BR salvo: {output}")
        if synced_en: self.log_line(f"✓ Inglês sincronizado salvo: {synced_en}")
        self.rv_srt.set_path(output)
        if synced_en: self.rv_en.set_path(synced_en)
        QMessageBox.information(self, "Tradução concluída", f"Legenda PT-BR salva em:\n{output}")

    def run_quick_review(self):
        path = self.rv_srt.path()
        if not Path(path).exists():
            QMessageBox.warning(self, "Legenda", "Selecione uma legenda PT-BR válida."); return
        self.review_source_path = path
        self.review_entries = read_srt(path)
        en = self.rv_en.path()
        self.review_reference = read_srt(en) if en and Path(en).exists() else []
        issues = quick_review(self.review_entries)
        self.fill_review_table(issues)
        self.rv_status.setText(f"Revisão rápida concluída: {len(issues)} alerta(s) em {len(self.review_entries)} trechos.")
        self.log_line(f"Revisão rápida: {len(issues)} alerta(s). Nenhuma IA executada no filme inteiro.")

    def fill_review_table(self, issues: list[dict]):
        self.rv_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            vals = [issue["time"], issue["category"], issue["message"], issue["text"].replace("\n", " / ")]
            for col, value in enumerate(vals):
                item = QTableWidgetItem(str(value))
                if col == 0: item.setData(Qt.UserRole, issue["entry_pos"])
                self.rv_table.setItem(row, col, item)
        if issues: self.rv_table.selectRow(0)

    def apply_review_safe_fixes(self):
        if not self.review_entries:
            self.run_quick_review()
            if not self.review_entries: return
        self.review_entries, count = apply_safe_fixes(self.review_entries)
        issues = quick_review(self.review_entries); self.fill_review_table(issues)
        self.rv_status.setText(f"{count} trecho(s) receberam apenas correções seguras de espaços/pontuação.")
        self.log_line(f"Correções seguras aplicadas: {count} trecho(s).")

    def save_review(self):
        if not self.review_entries:
            QMessageBox.information(self, "Revisão", "Execute primeiro a revisão rápida."); return
        source = Path(self.review_source_path)
        out = source.with_name(source.stem + ".revisada.srt")
        n = 2; base = out
        while out.exists():
            out = base.with_name(f"{base.stem}-{n}{base.suffix}"); n += 1
        write_srt(out, self.review_entries)
        self.rv_status.setText(f"Versão revisada salva: {out.name}")
        self.log_line(f"✓ Revisão salva: {out}")
        QMessageBox.information(self, "Salvo", f"Legenda revisada salva em:\n{out}")

    def refresh_models(self):
        models = list_models()
        self.model_combo.clear(); self.model_combo.addItems(models)
        default = choose_default_model(models)
        if default:
            self.model_combo.setCurrentText(default)
            self.ai_btn.setEnabled(True)
        else:
            self.model_combo.addItem("Ollama não detectado / sem modelos")
            self.ai_btn.setEnabled(False)

    def improve_selected(self):
        row = self.rv_table.currentRow()
        if row < 0 or not self.review_entries:
            QMessageBox.information(self, "Trecho", "Selecione uma linha da tabela."); return
        item = self.rv_table.item(row, 0)
        pos = item.data(Qt.UserRole) if item else None
        if pos is None or not (0 <= int(pos) < len(self.review_entries)):
            return
        pos = int(pos); entry = self.review_entries[pos]
        prev = self.review_entries[pos - 1].text if pos > 0 else ""
        nxt = self.review_entries[pos + 1].text if pos + 1 < len(self.review_entries) else ""
        ref = match_reference_entry(entry, self.review_reference) if self.review_reference else None
        english = ref.text if ref else ""
        model = self.model_combo.currentText()
        self.ai_btn.setEnabled(False); self.rv_status.setText("Revisando somente o trecho selecionado com IA local...")
        self.worker = AIWorker(entry.text, prev, nxt, english, model)
        self.worker.done.connect(lambda result, p=pos: self.ai_done(p, result))
        self.worker.failed.connect(lambda e: (self.ai_btn.setEnabled(True), QMessageBox.critical(self, "IA local", e)))
        self.worker.start()

    def ai_done(self, pos: int, result: dict):
        self.ai_btn.setEnabled(True)
        current = self.review_entries[pos].text
        suggestion = result.get("suggestion", current)
        reason = result.get("reason", "")
        if not result.get("changed") or suggestion.strip() == current.strip():
            self.rv_status.setText(f"{result.get('model')}: o trecho selecionado já parece natural.")
            QMessageBox.information(self, "Revisão local", "A IA local não encontrou motivo suficiente para alterar este trecho.")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Sugestão da IA local")
        box.setIcon(QMessageBox.Question)
        box.setText("Aplicar esta sugestão somente ao trecho selecionado?")
        box.setInformativeText(f"Atual:\n{current}\n\nSugestão:\n{suggestion}\n\nMotivo:\n{reason}")
        apply_btn = box.addButton("Aplicar", QMessageBox.AcceptRole)
        box.addButton("Manter atual", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == apply_btn:
            self.review_entries[pos] = replace(self.review_entries[pos], text=suggestion)
            self.fill_review_table(quick_review(self.review_entries))
            self.rv_status.setText("Sugestão aplicada em memória. Clique em Salvar versão revisada para gerar o arquivo.")
            self.log_line(f"IA local ({result.get('model')}): 1 trecho ajustado.")

    def test_sync(self):
        if self.sync_output: self.open_player(self.sync_video.path(), self.sync_output)

    def test_translation(self):
        if self.translation_output: self.open_player(self.tr_video.path(), self.translation_output)

    def open_player(self, video: str, srt: str):
        if not Path(video).exists() or not Path(srt).exists():
            QMessageBox.warning(self, "Player", "Vídeo ou legenda não encontrado."); return
        self.player_dialog = PlayerDialog(video, srt, self)
        self.player_dialog.show()

    def open_output_folder(self, output: str):
        path = Path(output) if output else Path(self.sync_srt.path() or ".")
        folder = path.parent if path.suffix else path
        if folder.exists():
            os.startfile(str(folder)) if sys.platform.startswith("win") else None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("SubSync Studio")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
