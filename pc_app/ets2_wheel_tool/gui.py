from __future__ import annotations

from collections import deque
from pathlib import Path
import time

from PySide6.QtCore import QPointF, QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit, QProgressBar, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget

from .config import APP_SETTINGS_PATH, BUNDLED_PROFILE_PATH, DEFAULT_PROFILE_PATH, AppSettings, WheelProfile
from .device import DeviceManager, DeviceState
from .ffb import ForceCommand, ForceFeedbackModel
from .telemetry.funbit_provider import FunbitTelemetryProvider
from .telemetry.mock_provider import MockTelemetryProvider
from .virtual_controller import VirtualControllerBridge
from .windows_startup import is_enabled as startup_is_enabled, set_enabled as startup_set_enabled


class HistoryPlot(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: deque[float] = deque(maxlen=180)
        self._color = QColor(color)
        self.setMinimumHeight(160)

    def push(self, value: float) -> None:
        self._values.append(value)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#0f1720'))
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor('#243447'), 1))
        for frac in (0.25, 0.5, 0.75):
            y = int(self.height() * frac)
            painter.drawLine(0, y, self.width(), y)
        if len(self._values) < 2:
            return
        lo = min(self._values)
        hi = max(self._values)
        span = max(1e-6, hi - lo)
        points = []
        for i, value in enumerate(self._values):
            x = i * (self.width() - 1) / max(1, len(self._values) - 1)
            y = self.height() - ((value - lo) / span) * (self.height() - 12) - 6
            points.append(QPointF(x, y))
        painter.setPen(QPen(self._color, 2.2))
        painter.drawPolyline(QPolygonF(points))


class ValueCard(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName('valueCard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        title_label = QLabel(title)
        title_label.setObjectName('cardTitle')
        self.value_label = QLabel('--')
        self.value_label.setObjectName('cardValue')
        self.value_label.setStyleSheet(f'color: {accent};')
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def setText(self, text: str) -> None:
        self.value_label.setText(text)


class WheelView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle_deg = 0.0
        self.setMinimumSize(260, 260)

    def setAngle(self, angle_deg: float) -> None:
        self._angle_deg = angle_deg
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor('#0f1720'))

        size = min(self.width(), self.height()) - 24
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        radius = size / 2.0

        painter.setPen(QPen(QColor('#243447'), 2))
        painter.setBrush(QColor('#111927'))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_deg)

        rim_pen = QPen(QColor('#dbe7f3'), 10)
        rim_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(rim_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(int(-radius + 12), int(-radius + 12), int((radius - 12) * 2), int((radius - 12) * 2), 40 * 16, 280 * 16)

        spoke_pen = QPen(QColor('#f59e0b'), 6)
        spoke_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(spoke_pen)
        painter.drawLine(QPointF(0, -radius + 26), QPointF(0, 0))
        painter.drawLine(QPointF(-radius * 0.55, radius * 0.18), QPointF(0, 0))
        painter.drawLine(QPointF(radius * 0.55, radius * 0.18), QPointF(0, 0))

        painter.setBrush(QColor('#1d4ed8'))
        painter.setPen(QPen(QColor('#8fb3ff'), 2))
        painter.drawEllipse(QPointF(0, 0), radius * 0.18, radius * 0.18)
        painter.restore()

        painter.setPen(QPen(QColor('#8ea2b9'), 1))
        painter.drawText(self.rect().adjusted(0, 0, 0, -8), Qt.AlignBottom | Qt.AlignHCenter, f'{self._angle_deg:.1f} deg')


def make_slider(low: int, high: int, value: int) -> QSlider:
    slider = QSlider(Qt.Horizontal)
    slider.setRange(low, high)
    slider.setValue(value)
    return slider


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('ETS2 DIY FFB Wheel Tool')
        self.resize(1400, 920)
        self._apply_theme()

        self.device = DeviceManager()
        self.device.state_changed.connect(self.on_state_changed)
        self.device.log_message.connect(self.append_log)
        self.ffb_model = ForceFeedbackModel()
        self.settings = AppSettings.load(APP_SETTINGS_PATH) if APP_SETTINGS_PATH.exists() else AppSettings()
        if not DEFAULT_PROFILE_PATH.exists() and BUNDLED_PROFILE_PATH.exists():
            WheelProfile.load(BUNDLED_PROFILE_PATH).save(DEFAULT_PROFILE_PATH)
        self.profile = WheelProfile.load(DEFAULT_PROFILE_PATH) if DEFAULT_PROFILE_PATH.exists() else WheelProfile()
        self.profile_path = Path(self.settings.last_profile_path) if self.settings.last_profile_path else DEFAULT_PROFILE_PATH
        if self.profile_path.exists():
            self.profile = WheelProfile.load(self.profile_path)
        else:
            self.profile_path = DEFAULT_PROFILE_PATH
        self._migrated_profile_data = False
        self.telemetry_provider = FunbitTelemetryProvider()
        self.mock_provider = MockTelemetryProvider()
        self.virtual_controller = VirtualControllerBridge()
        self.last_state = DeviceState()
        self.last_force = 0.0
        self.current_angle = 0.0
        self.current_speed = 0.0
        self._last_count_sample: tuple[int, float] | None = None

        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        cards = QHBoxLayout()
        self.card_connection = ValueCard('Connection', '#22c55e')
        self.card_angle = ValueCard('Wheel Angle', '#f59e0b')
        self.card_speed = ValueCard('Wheel Speed', '#60a5fa')
        self.card_torque = ValueCard('Torque', '#fb7185')
        self.card_pedals = ValueCard('Pedals', '#34d399')
        for card in (self.card_connection, self.card_angle, self.card_speed, self.card_torque, self.card_pedals):
            cards.addWidget(card, 1)
        root.addLayout(cards)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.connection_tab = QWidget()
        self.encoder_tab = QWidget()
        self.motor_tab = QWidget()
        self.pedals_tab = QWidget()
        self.tuning_tab = QWidget()
        self.runtime_tab = QWidget()
        self.diagnostics_tab = QWidget()
        self.tabs.addTab(self.connection_tab, 'Connection')
        self.tabs.addTab(self.encoder_tab, 'Encoder Setup')
        self.tabs.addTab(self.motor_tab, 'Motor Setup')
        self.tabs.addTab(self.pedals_tab, 'Pedal Setup')
        self.tabs.addTab(self.tuning_tab, 'FFB Tuning')
        self.tabs.addTab(self.runtime_tab, 'ETS2 Runtime')
        self.tabs.addTab(self.diagnostics_tab, 'Diagnostics')
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._build_connection_tab()
        self._build_encoder_tab()
        self._build_motor_tab()
        self._build_pedals_tab()
        self._build_tuning_tab()
        self._build_runtime_tab()
        self._build_diagnostics_tab()
        self._load_settings_into_ui()
        if 0 <= self.settings.last_tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(self.settings.last_tab_index)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.poll_device)
        self.status_timer.start(80)
        self.runtime_timer = QTimer(self)
        self.runtime_timer.timeout.connect(self.update_runtime)
        self.runtime_timer.start(20)

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
        QMainWindow, QWidget { background: #0b1220; color: #d7e2f0; font-size: 10.5pt; }
        QTabWidget::pane { border: 1px solid #203041; background: #111927; border-radius: 10px; }
        QTabBar::tab { background: #172130; color: #95a6ba; padding: 10px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
        QTabBar::tab:selected { background: #223249; color: #f2f7fb; }
        QGroupBox { border: 1px solid #243445; border-radius: 12px; margin-top: 12px; padding-top: 12px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #f3f8fc; }
        QPushButton { background: #1d4ed8; color: white; border: none; border-radius: 8px; padding: 8px 12px; }
        QPushButton:hover { background: #2563eb; }
        QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { background: #111927; border: 1px solid #2b3e52; border-radius: 8px; padding: 6px; }
        QSlider::groove:horizontal { background: #2a394b; height: 6px; border-radius: 3px; }
        QSlider::handle:horizontal { background: #f59e0b; width: 16px; margin: -5px 0; border-radius: 8px; }
        QProgressBar { border: 1px solid #2b3e52; border-radius: 7px; background: #101822; text-align: center; }
        QProgressBar::chunk { background: #10b981; border-radius: 6px; }
        QLabel#cardTitle { color: #8ea2b9; font-size: 9pt; font-weight: 600; }
        QLabel#cardValue { font-size: 20pt; font-weight: 700; }
        QFrame#valueCard { background: #101926; border: 1px solid #223446; border-radius: 14px; }
        """)

    def _save_settings(self) -> None:
        self.settings.save(APP_SETTINGS_PATH)

    def _apply_motor_dir(self, value: float) -> float:
        return -value if self.profile.motor.invert_direction else value

    def _encoder_angle(self, count: int) -> float:
        angle = (count * 360.0 / max(1, self.profile.encoder.counts_per_rev)) + self.profile.encoder.center_offset_deg
        return -angle if self.profile.encoder.invert_direction else angle

    def _encoder_speed(self, count: int) -> float:
        now = time.perf_counter()
        if self._last_count_sample is None:
            self._last_count_sample = (count, now)
            return 0.0
        last_count, last_time = self._last_count_sample
        self._last_count_sample = (count, now)
        speed = ((count - last_count) * 360.0 / max(1, self.profile.encoder.counts_per_rev)) / max(1e-3, now - last_time)
        return -speed if self.profile.encoder.invert_direction else speed

    def _sync_settings_from_ui(self) -> None:
        self.settings.last_profile_path = str(self.profile_path)
        self.settings.last_tab_index = self.tabs.currentIndex()
        self._sync_profile_from_ui()
        self._save_settings()

    def _sync_profile_from_ui(self) -> None:
        selected_path = self.port_combo.currentData()
        self.profile.last_port = str(selected_path or "")
        self.profile.start_with_windows = self.start_with_windows_checkbox.isChecked()
        self.profile.test_mode = self.test_mode_checkbox.isChecked()
        self.profile.runtime_enabled = self.runtime_enable_checkbox.isChecked()
        self.profile.virtual_controller_enabled = self.virtual_controller_checkbox.isChecked()
        self.profile.virtual_steering_range_deg = self.virtual_steer_range_spin.value()
        self.profile.encoder.counts_per_rev = self.encoder_cpr_spin.value()
        self.profile.encoder.wheel_range_deg = self.encoder_range_spin.value()
        self.profile.encoder.center_offset_deg = self.encoder_offset_spin.value()
        self.profile.encoder.invert_direction = self.encoder_invert_checkbox.isChecked()
        self.profile.motor.invert_direction = self.motor_invert_checkbox.isChecked()
        self.profile.motor.startup_enable = self.motor_enable_checkbox.isChecked()
        self.profile.brake.min_raw = self.brake_min_spin.value()
        self.profile.brake.max_raw = self.brake_max_spin.value()
        self.profile.brake.invert = self.brake_invert_checkbox.isChecked()
        self.profile.accel.min_raw = self.accel_min_spin.value()
        self.profile.accel.max_raw = self.accel_max_spin.value()
        self.profile.accel.invert = self.accel_invert_checkbox.isChecked()
        for name, slider in self.profile_sliders.items():
            setattr(self.profile, name, slider.value() / 100.0)

    def _save_active_profile(self) -> None:
        self._sync_profile_from_ui()
        self.profile.save(self.profile_path)

    def _apply_profile_to_ui(self) -> None:
        self.test_mode_checkbox.setChecked(self.profile.test_mode)
        self.runtime_enable_checkbox.setChecked(self.profile.runtime_enabled)
        self.virtual_controller_checkbox.setChecked(self.profile.virtual_controller_enabled)
        self.start_with_windows_checkbox.setChecked(self.profile.start_with_windows)
        self.virtual_steer_range_spin.setValue(self.profile.virtual_steering_range_deg)
        self.encoder_cpr_spin.setValue(self.profile.encoder.counts_per_rev)
        self.encoder_range_spin.setValue(self.profile.encoder.wheel_range_deg)
        self.encoder_offset_spin.setValue(self.profile.encoder.center_offset_deg)
        self.encoder_invert_checkbox.setChecked(self.profile.encoder.invert_direction)
        self.motor_invert_checkbox.setChecked(self.profile.motor.invert_direction)
        self.motor_enable_checkbox.setChecked(self.profile.motor.startup_enable)
        self.brake_min_spin.setValue(self.profile.brake.min_raw)
        self.brake_max_spin.setValue(self.profile.brake.max_raw)
        self.brake_invert_checkbox.setChecked(self.profile.brake.invert)
        self.accel_min_spin.setValue(self.profile.accel.min_raw)
        self.accel_max_spin.setValue(self.profile.accel.max_raw)
        self.accel_invert_checkbox.setChecked(self.profile.accel.invert)
        for name, slider in self.profile_sliders.items():
            with QSignalBlocker(slider):
                slider.setValue(int(getattr(self.profile, name) * 100))
        if self.profile.last_port:
            for index in range(self.port_combo.count()):
                if self.port_combo.itemData(index) == self.profile.last_port:
                    self.port_combo.setCurrentIndex(index)
                    break

    def _migrate_legacy_settings_into_profile(self) -> None:
        legacy_found = any(
            [
                getattr(self.settings, "last_port", ""),
                hasattr(self.settings, "start_with_windows"),
                hasattr(self.settings, "test_mode"),
                hasattr(self.settings, "runtime_enabled"),
                hasattr(self.settings, "encoder"),
                hasattr(self.settings, "motor"),
                hasattr(self.settings, "brake"),
                hasattr(self.settings, "accel"),
            ]
        )
        if not legacy_found:
            return
        if getattr(self.settings, "last_port", "") and not self.profile.last_port:
            self.profile.last_port = self.settings.last_port
        if hasattr(self.settings, "start_with_windows"):
            self.profile.start_with_windows = self.settings.start_with_windows
        if hasattr(self.settings, "test_mode"):
            self.profile.test_mode = self.settings.test_mode
        if hasattr(self.settings, "runtime_enabled"):
            self.profile.runtime_enabled = self.settings.runtime_enabled
        if hasattr(self.settings, "encoder"):
            self.profile.encoder = self.settings.encoder
        if hasattr(self.settings, "motor"):
            self.profile.motor = self.settings.motor
        if hasattr(self.settings, "brake"):
            self.profile.brake = self.settings.brake
        if hasattr(self.settings, "accel"):
            self.profile.accel = self.settings.accel
        self._migrated_profile_data = True

    def _on_tab_changed(self, index: int) -> None:
        self.settings.last_tab_index = index
        self._save_settings()

    def _on_start_with_windows_toggled(self, checked: bool) -> None:
        try:
            startup_set_enabled(checked)
            self.profile.start_with_windows = checked
            self._save_active_profile()
            self._save_settings()
        except OSError as exc:
            QMessageBox.warning(self, 'Startup Setting Failed', f'Could not update Windows startup setting.\n\n{exc}')
            with QSignalBlocker(self.start_with_windows_checkbox):
                self.start_with_windows_checkbox.setChecked(startup_is_enabled())

    def _build_connection_tab(self) -> None:
        layout = QVBoxLayout(self.connection_tab)
        top = QHBoxLayout()
        self.port_combo = QComboBox()
        self.refresh_ports()
        refresh_btn = QPushButton('Refresh Devices')
        refresh_btn.clicked.connect(self.refresh_ports)
        connect_btn = QPushButton('Connect')
        connect_btn.clicked.connect(self.connect_selected)
        disconnect_btn = QPushButton('Disconnect')
        disconnect_btn.clicked.connect(self.device.disconnect)
        top.addWidget(QLabel('USB HID Device'))
        top.addWidget(self.port_combo, 1)
        top.addWidget(refresh_btn)
        top.addWidget(connect_btn)
        top.addWidget(disconnect_btn)
        layout.addLayout(top)
        grid = QGridLayout()
        dev = QGroupBox('Device')
        form = QFormLayout(dev)
        self.connection_state_label = QLabel('Disconnected')
        self.version_label = QLabel('-')
        self.fault_label = QLabel('0x00000000')
        form.addRow('State', self.connection_state_label)
        form.addRow('Firmware', self.version_label)
        form.addRow('Fault Flags', self.fault_label)
        opts = QGroupBox('Startup')
        opts_form = QFormLayout(opts)
        self.test_mode_checkbox = QCheckBox('Virtual test mode')
        self.runtime_enable_checkbox = QCheckBox('Stream FFB to STM32')
        self.virtual_controller_checkbox = QCheckBox('Expose virtual Xbox controller')
        self.start_with_windows_checkbox = QCheckBox('Start app with Windows')
        self.test_mode_checkbox.toggled.connect(self._sync_settings_from_ui)
        self.runtime_enable_checkbox.toggled.connect(self._sync_settings_from_ui)
        self.virtual_controller_checkbox.toggled.connect(self._on_virtual_controller_toggled)
        self.start_with_windows_checkbox.toggled.connect(self._on_start_with_windows_toggled)
        opts_form.addRow(self.test_mode_checkbox)
        opts_form.addRow(self.runtime_enable_checkbox)
        opts_form.addRow(self.virtual_controller_checkbox)
        opts_form.addRow(self.start_with_windows_checkbox)
        actions = QGroupBox('Quick Actions')
        actions_layout = QVBoxLayout(actions)
        zero_btn = QPushButton('Set Current Position As Center')
        zero_btn.clicked.connect(self.zero_encoder_with_offset)
        clear_btn = QPushButton('Clear Faults')
        clear_btn.clicked.connect(self.device.clear_faults)
        estop_btn = QPushButton('Emergency Stop')
        estop_btn.clicked.connect(lambda: self.device.set_estop(True))
        actions_layout.addWidget(zero_btn)
        actions_layout.addWidget(clear_btn)
        actions_layout.addWidget(estop_btn)
        actions_layout.addStretch(1)
        grid.addWidget(dev, 0, 0)
        grid.addWidget(opts, 0, 1)
        grid.addWidget(actions, 0, 2)
        layout.addLayout(grid)
        layout.addStretch(1)

    def _build_encoder_tab(self) -> None:
        layout = QVBoxLayout(self.encoder_tab)
        top = QHBoxLayout()
        live = QGroupBox('Live Encoder')
        live_form = QFormLayout(live)
        self.encoder_count_label = QLabel('0')
        self.encoder_angle_label = QLabel('0.0 deg')
        self.encoder_speed_label = QLabel('0.0 deg/s')
        self.encoder_dir_label = QLabel('Stopped')
        self.encoder_range_label = QLabel('0.0 %')
        live_form.addRow('Count', self.encoder_count_label)
        live_form.addRow('Angle', self.encoder_angle_label)
        live_form.addRow('Speed', self.encoder_speed_label)
        live_form.addRow('Direction', self.encoder_dir_label)
        live_form.addRow('Range Use', self.encoder_range_label)
        cal = QGroupBox('Calibration')
        cal_form = QFormLayout(cal)
        self.encoder_cpr_spin = QSpinBox(); self.encoder_cpr_spin.setRange(1, 100000); self.encoder_cpr_spin.setSingleStep(100)
        self.encoder_range_spin = QDoubleSpinBox(); self.encoder_range_spin.setRange(90.0, 2160.0); self.encoder_range_spin.setSuffix(' deg')
        self.virtual_steer_range_spin = QDoubleSpinBox(); self.virtual_steer_range_spin.setRange(90.0, 2160.0); self.virtual_steer_range_spin.setSuffix(' deg')
        self.encoder_offset_spin = QDoubleSpinBox(); self.encoder_offset_spin.setRange(-1080.0, 1080.0); self.encoder_offset_spin.setSuffix(' deg')
        self.encoder_invert_checkbox = QCheckBox('Invert encoder direction')
        for widget in (self.encoder_cpr_spin, self.encoder_range_spin, self.virtual_steer_range_spin, self.encoder_offset_spin):
            widget.valueChanged.connect(self._sync_settings_from_ui)
        self.encoder_invert_checkbox.toggled.connect(self._sync_settings_from_ui)
        capture_btn = QPushButton('Capture Current Center')
        capture_btn.clicked.connect(self.capture_current_encoder_center)
        cal_form.addRow('CPR', self.encoder_cpr_spin)
        cal_form.addRow('Wheel Range', self.encoder_range_spin)
        cal_form.addRow('Game Steering Range', self.virtual_steer_range_spin)
        cal_form.addRow('Center Offset', self.encoder_offset_spin)
        cal_form.addRow(self.encoder_invert_checkbox)
        cal_form.addRow(capture_btn)
        top.addWidget(live, 1)
        top.addWidget(cal, 1)
        wheel_box = QGroupBox('Visual Wheel')
        wheel_layout = QVBoxLayout(wheel_box)
        self.wheel_view = WheelView()
        wheel_layout.addWidget(self.wheel_view, 1)
        top.addWidget(wheel_box, 1)
        layout.addLayout(top)
        self.encoder_plot = HistoryPlot('#f59e0b')
        layout.addWidget(self.encoder_plot)

    def _build_motor_tab(self) -> None:
        layout = QVBoxLayout(self.motor_tab)
        cfg = QGroupBox('Direction And Manual Test')
        form = QFormLayout(cfg)
        self.motor_enable_checkbox = QCheckBox('Enable motor output')
        self.motor_enable_checkbox.toggled.connect(self.device.set_motor_enabled)
        self.motor_enable_checkbox.toggled.connect(self._sync_settings_from_ui)
        self.motor_invert_checkbox = QCheckBox('Invert motor direction')
        self.motor_invert_checkbox.toggled.connect(self._sync_settings_from_ui)
        self.manual_torque_slider = make_slider(-45, 45, 0)
        self.manual_torque_slider.valueChanged.connect(lambda v: self.device.set_constant_torque(self._apply_motor_dir(v / 100.0)))
        self.manual_pwm_slider = make_slider(-120, 120, 0)
        self.manual_pwm_slider.valueChanged.connect(lambda v: self.device.set_pwm_raw(int(self._apply_motor_dir(float(v)))))
        buttons = QHBoxLayout()
        vib_btn = QPushButton('Vibration Test'); vib_btn.clicked.connect(lambda: self.device.set_vibration(0.18, 32.0))
        spring_btn = QPushButton('Spring Test'); spring_btn.clicked.connect(lambda: self.device.set_spring(0.22, self.profile.encoder.center_offset_deg))
        damper_btn = QPushButton('Damper Test'); damper_btn.clicked.connect(lambda: self.device.set_damper(0.18))
        bump_btn = QPushButton('Bump Pulse'); bump_btn.clicked.connect(lambda: self.device.trigger_impulse(self._apply_motor_dir(0.2), 75))
        buttons.addWidget(vib_btn); buttons.addWidget(spring_btn); buttons.addWidget(damper_btn); buttons.addWidget(bump_btn)
        form.addRow(self.motor_enable_checkbox)
        form.addRow(self.motor_invert_checkbox)
        form.addRow('Manual Torque', self.manual_torque_slider)
        form.addRow('Raw PWM', self.manual_pwm_slider)
        form.addRow(buttons)
        layout.addWidget(cfg)
        layout.addStretch(1)

    def _build_pedals_tab(self) -> None:
        layout = QVBoxLayout(self.pedals_tab)
        live = QGroupBox('Live Pedals')
        grid = QGridLayout(live)
        self.brake_bar = QProgressBar(); self.brake_bar.setRange(0, 1000)
        self.accel_bar = QProgressBar(); self.accel_bar.setRange(0, 1000)
        self.brake_raw_label = QLabel('0'); self.accel_raw_label = QLabel('0')
        grid.addWidget(QLabel('Brake'), 0, 0); grid.addWidget(self.brake_bar, 0, 1); grid.addWidget(self.brake_raw_label, 0, 2)
        grid.addWidget(QLabel('Accelerator'), 1, 0); grid.addWidget(self.accel_bar, 1, 1); grid.addWidget(self.accel_raw_label, 1, 2)
        layout.addWidget(live)
        row = QHBoxLayout()
        row.addWidget(self._make_pedal_box('Brake', True))
        row.addWidget(self._make_pedal_box('Accelerator', False))
        layout.addLayout(row)
        actions = QHBoxLayout()
        min_btn = QPushButton('Capture Current As Min'); min_btn.clicked.connect(self.capture_current_min_values)
        max_btn = QPushButton('Capture Current As Max'); max_btn.clicked.connect(self.capture_current_max_values)
        apply_btn = QPushButton('Apply And Save Calibration'); apply_btn.clicked.connect(self.apply_pedal_calibration)
        actions.addWidget(min_btn); actions.addWidget(max_btn); actions.addWidget(apply_btn)
        layout.addLayout(actions)
        self.pedal_plot = HistoryPlot('#22c55e')
        layout.addWidget(self.pedal_plot)

    def _make_pedal_box(self, title: str, is_brake: bool) -> QGroupBox:
        box = QGroupBox(f'{title} Calibration')
        form = QFormLayout(box)
        min_spin = QSpinBox(); min_spin.setRange(0, 4095)
        max_spin = QSpinBox(); max_spin.setRange(0, 4095)
        invert_checkbox = QCheckBox('Invert')
        min_spin.valueChanged.connect(self._sync_settings_from_ui)
        max_spin.valueChanged.connect(self._sync_settings_from_ui)
        invert_checkbox.toggled.connect(self._sync_settings_from_ui)
        form.addRow('Min Raw', min_spin)
        form.addRow('Max Raw', max_spin)
        form.addRow(invert_checkbox)
        if is_brake:
            self.brake_min_spin = min_spin; self.brake_max_spin = max_spin; self.brake_invert_checkbox = invert_checkbox
        else:
            self.accel_min_spin = min_spin; self.accel_max_spin = max_spin; self.accel_invert_checkbox = invert_checkbox
        return box

    def _build_tuning_tab(self) -> None:
        layout = QVBoxLayout(self.tuning_tab)
        group = QGroupBox('FFB Tuning')
        form = QFormLayout(group)
        self.profile_sliders: dict[str, QSlider] = {}
        fields = [('master_gain', 'Master Gain', 0, 100), ('spring_gain', 'Center Spring', 0, 100), ('damper_gain', 'Damper', 0, 100), ('friction_gain', 'Friction', 0, 100), ('vibration_gain', 'Road Vibration', 0, 100), ('bump_gain', 'Bumps', 0, 100), ('collision_gain', 'Collision Kick', 0, 100), ('speed_sensitivity', 'Speed Sensitivity', 0, 100), ('torque_limit', 'Torque Limit', 5, 45)]
        for name, label, low, high in fields:
            slider = make_slider(low, high, int(getattr(self.profile, name) * 100))
            slider.valueChanged.connect(self.on_profile_changed)
            self.profile_sliders[name] = slider
            form.addRow(label, slider)
        row = QHBoxLayout()
        new_btn = QPushButton('New Profile'); new_btn.clicked.connect(self.new_profile)
        save_btn = QPushButton('Save Profile'); save_btn.clicked.connect(self.save_profile)
        save_as_btn = QPushButton('Save Profile As'); save_as_btn.clicked.connect(self.save_profile_as)
        load_btn = QPushButton('Load Profile'); load_btn.clicked.connect(self.load_profile)
        row.addWidget(new_btn); row.addWidget(save_btn); row.addWidget(save_as_btn); row.addWidget(load_btn)
        layout.addWidget(group)
        layout.addLayout(row)
        layout.addStretch(1)

    def _build_runtime_tab(self) -> None:
        layout = QVBoxLayout(self.runtime_tab)
        info = QGroupBox('Live Telemetry')
        form = QFormLayout(info)
        self.controller_status_label = QLabel('Virtual Xbox controller disabled')
        self.telemetry_status_label = QLabel('Virtual test mode enabled')
        self.telemetry_source_label = QLabel('virtual-test')
        self.telemetry_speed_label = QLabel('0.0 m/s')
        self.telemetry_rpm_label = QLabel('0 rpm')
        self.telemetry_brake_label = QLabel('0.00')
        self.telemetry_accel_label = QLabel('0.00')
        self.telemetry_force_label = QLabel('0.000')
        self.controller_steer_label = QLabel('0.00')
        self.controller_status_label.setWordWrap(True)
        self.controller_status_label.setStyleSheet('color: #60a5fa;')
        form.addRow('Controller', self.controller_status_label)
        self.telemetry_status_label.setWordWrap(True)
        self.telemetry_status_label.setStyleSheet('color: #facc15;')
        form.addRow('Status', self.telemetry_status_label)
        form.addRow('Source', self.telemetry_source_label)
        form.addRow('Truck Speed', self.telemetry_speed_label)
        form.addRow('Engine RPM', self.telemetry_rpm_label)
        form.addRow('Brake', self.telemetry_brake_label)
        form.addRow('Throttle', self.telemetry_accel_label)
        form.addRow('Steer Axis', self.controller_steer_label)
        form.addRow('Output Torque', self.telemetry_force_label)
        layout.addWidget(info)
        bridge_box = QGroupBox('Real ETS2 Setup')
        bridge_layout = QVBoxLayout(bridge_box)
        bridge_hint = QLabel(
            'For live Euro Truck Simulator 2 use, turn off Virtual test mode and run an ETS2 telemetry bridge '
            'that exposes HTTP on 127.0.0.1:25555 before launching or driving the game.'
        )
        bridge_hint.setWordWrap(True)
        bridge_layout.addWidget(bridge_hint)
        layout.addWidget(bridge_box)
        self.runtime_plot = HistoryPlot('#60a5fa')
        layout.addWidget(self.runtime_plot)

    def _build_diagnostics_tab(self) -> None:
        layout = QVBoxLayout(self.diagnostics_tab)
        box = QGroupBox('Transport')
        form = QFormLayout(box)
        self.latency_label = QLabel('0.0 ms')
        self.rx_label = QLabel('0')
        self.tx_label = QLabel('0')
        self.command_age_label = QLabel('0 ms')
        form.addRow('Latency', self.latency_label)
        form.addRow('RX Packets', self.rx_label)
        form.addRow('TX Packets', self.tx_label)
        form.addRow('Command Age', self.command_age_label)
        layout.addWidget(box)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def _load_settings_into_ui(self) -> None:
        self._migrate_legacy_settings_into_profile()
        self._apply_profile_to_ui()
        self.virtual_controller.set_enabled(self.profile.virtual_controller_enabled)
        if self._migrated_profile_data:
            self._save_active_profile()
            self._save_settings()

    def refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        for device in self.device.devices():
            self.port_combo.addItem(device.label, device.path)
        target = self.profile.last_port or current
        if target:
            for index in range(self.port_combo.count()):
                if self.port_combo.itemData(index) == target:
                    self.port_combo.setCurrentIndex(index)
                    break

    def connect_selected(self) -> None:
        path = self.port_combo.currentData()
        if not path:
            QMessageBox.warning(self, 'No Device', 'Select a USB HID device first.')
            return
        self.device.connect_path(str(path))
        self._sync_settings_from_ui()
        self.apply_saved_calibrations_to_device()

    def apply_saved_calibrations_to_device(self) -> None:
        if not self.device.transport.connected:
            return
        self.device.set_pedal_cal(0, self.profile.brake.min_raw, self.profile.brake.max_raw, self.profile.brake.invert)
        self.device.set_pedal_cal(1, self.profile.accel.min_raw, self.profile.accel.max_raw, self.profile.accel.invert)
        self.device.set_motor_enabled(self.motor_enable_checkbox.isChecked())

    def zero_encoder_with_offset(self) -> None:
        self.device.zero_encoder()
        self.encoder_offset_spin.setValue(0.0)
        self._sync_settings_from_ui()

    def capture_current_encoder_center(self) -> None:
        self.encoder_offset_spin.setValue(self.profile.encoder.center_offset_deg - self._encoder_angle(self.last_state.encoder_count))
        self._sync_settings_from_ui()

    def capture_current_min_values(self) -> None:
        self.brake_min_spin.setValue(self.last_state.brake_raw)
        self.accel_min_spin.setValue(self.last_state.accel_raw)
        self._sync_settings_from_ui()

    def capture_current_max_values(self) -> None:
        self.brake_max_spin.setValue(self.last_state.brake_raw)
        self.accel_max_spin.setValue(self.last_state.accel_raw)
        self._sync_settings_from_ui()

    def apply_pedal_calibration(self) -> None:
        self._sync_settings_from_ui()
        self.apply_saved_calibrations_to_device()

    def poll_device(self) -> None:
        if self.device.transport.connected:
            self.device.request_status()

    def update_runtime(self) -> None:
        telemetry = self.mock_provider.read() if self.test_mode_checkbox.isChecked() else self.telemetry_provider.read()
        self.telemetry_source_label.setText(telemetry.source)
        self.telemetry_speed_label.setText(f'{telemetry.speed_mps:.1f} m/s')
        self.telemetry_rpm_label.setText(f'{telemetry.engine_rpm:.0f} rpm')
        self.telemetry_brake_label.setText(f'{telemetry.brake:.2f}')
        self.telemetry_accel_label.setText(f'{telemetry.throttle:.2f}')
        if self.test_mode_checkbox.isChecked():
            self.telemetry_status_label.setText('Virtual test mode is active. Forces are generated without the ETS2 game.')
            self.telemetry_status_label.setStyleSheet('color: #facc15;')
        elif telemetry.connected:
            self.telemetry_status_label.setText('Live ETS2 telemetry detected. Runtime FFB is following the game.')
            self.telemetry_status_label.setStyleSheet('color: #4ade80;')
        else:
            self.telemetry_status_label.setText(
                'Waiting for live ETS2 telemetry on 127.0.0.1:25555. FFB output is held at zero until the bridge is available.'
            )
            self.telemetry_status_label.setStyleSheet('color: #f87171;')
        controller_status = self.virtual_controller.status()
        self.controller_status_label.setText(controller_status.message)
        self.controller_status_label.setStyleSheet('color: #4ade80;' if controller_status.active else 'color: #60a5fa;')
        if self.runtime_enable_checkbox.isChecked() and self.device.transport.connected:
            command = self.ffb_model.compute(telemetry, self.current_angle, self.current_speed, self.profile, test_mode=self.test_mode_checkbox.isChecked())
            command = ForceCommand(constant=self._apply_motor_dir(command.constant), spring_gain=command.spring_gain, spring_center_deg=self.profile.encoder.center_offset_deg, damper_gain=command.damper_gain, friction_gain=command.friction_gain, vibration_gain=command.vibration_gain, vibration_freq_hz=command.vibration_freq_hz, impulse_torque=self._apply_motor_dir(command.impulse_torque), impulse_duration_ms=command.impulse_duration_ms, debug_total=self._apply_motor_dir(command.debug_total))
            self.last_force = command.debug_total
            self.telemetry_force_label.setText(f'{command.debug_total:.3f}')
            self.runtime_plot.push(command.debug_total)
            self.device.apply_force_command(command)
        else:
            self.last_force = 0.0
            self.telemetry_force_label.setText('0.000')
        steer = self.current_angle / max(1.0, self.profile.virtual_steering_range_deg * 0.5)
        self.controller_steer_label.setText(f'{max(-1.0, min(1.0, steer)):.2f}')
        self.virtual_controller.update_inputs(steer, self.last_state.brake_norm, self.last_state.accel_norm)

    def on_state_changed(self, state: DeviceState) -> None:
        self.last_state = state
        self.current_angle = self._encoder_angle(state.encoder_count)
        self.current_speed = self._encoder_speed(state.encoder_count)
        direction = 'Right' if self.current_speed > 0.5 else 'Left' if self.current_speed < -0.5 else 'Stopped'
        range_pct = 100.0 * min(1.0, abs(self.current_angle) / max(1.0, self.profile.encoder.wheel_range_deg * 0.5))
        self.connection_state_label.setText('Connected' if state.connected else 'Disconnected')
        self.version_label.setText(state.version or '-')
        self.fault_label.setText(f'0x{state.fault_flags:08X}')
        self.encoder_count_label.setText(str(state.encoder_count))
        self.encoder_angle_label.setText(f'{self.current_angle:.2f} deg')
        self.encoder_speed_label.setText(f'{self.current_speed:.2f} deg/s')
        self.encoder_dir_label.setText(direction)
        self.encoder_range_label.setText(f'{range_pct:.1f} %')
        self.brake_bar.setValue(int(state.brake_norm * 1000))
        self.accel_bar.setValue(int(state.accel_norm * 1000))
        self.brake_raw_label.setText(str(state.brake_raw))
        self.accel_raw_label.setText(str(state.accel_raw))
        self.latency_label.setText(f'{state.latency_ms:.1f} ms')
        self.rx_label.setText(str(state.rx_packets))
        self.tx_label.setText(str(state.tx_packets))
        self.command_age_label.setText(f'{state.command_age_ms} ms')
        self.card_connection.setText('Connected' if state.connected else 'Offline')
        self.card_angle.setText(f'{self.current_angle:.1f} deg')
        self.card_speed.setText(f'{self.current_speed:.1f} deg/s')
        self.card_torque.setText(f'{self.last_force:.3f}')
        self.card_pedals.setText(f'B {state.brake_norm:.2f} / A {state.accel_norm:.2f}')
        self.wheel_view.setAngle(self.current_angle)
        self.encoder_plot.push(self.current_angle)
        self.pedal_plot.push(state.accel_norm - state.brake_norm)

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def on_profile_changed(self) -> None:
        self._save_active_profile()

    def save_profile(self) -> None:
        self._save_active_profile()
        self._sync_settings_from_ui()
        QMessageBox.information(self, 'Profile Saved', f'Saved profile:\n{self.profile_path}')

    def save_profile_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Save Profile As', str(self.profile_path), 'JSON Files (*.json)')
        if path:
            self.profile_path = Path(path)
            self._save_active_profile()
            self._sync_settings_from_ui()

    def new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, 'New Profile', 'Profile file name:')
        if not ok or not name.strip():
            return
        filename = name.strip()
        if not filename.lower().endswith('.json'):
            filename += '.json'
        self.profile = WheelProfile()
        self.profile_path = self.profile_path.parent / filename
        self._apply_profile_to_ui()
        self._save_active_profile()
        self._sync_settings_from_ui()

    def load_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Load Profile', str(self.profile_path), 'JSON Files (*.json)')
        if not path:
            return
        self.profile_path = Path(path)
        self.profile = WheelProfile.load(self.profile_path)
        self._apply_profile_to_ui()
        self._save_active_profile()
        self._sync_settings_from_ui()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._sync_settings_from_ui()
        self.virtual_controller.close()
        super().closeEvent(event)

    def _on_virtual_controller_toggled(self, checked: bool) -> None:
        self.virtual_controller.set_enabled(checked)
        if not checked:
            self.virtual_controller.reset_inputs()
        self._sync_settings_from_ui()


def run() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
