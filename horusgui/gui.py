#!/usr/bin/env python
#
#   Horus Telemetry GUI
#
#   Mark Jessop <vk5qi@rfhead.net>
#


# Python 3 check
import sys

if sys.version_info < (3, 0):
    print("This script requires Python 3!")
    sys.exit(1)

import argparse
import datetime
# import glob
import logging
import platform
import time
import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from pyqtgraph.dockarea import *

from .widgets import *
from .audio import *
from .udpaudio import *
from .fft import *
from .modem import *
from .config import *
from .utils import position_info
from .icon import getHorusIcon
from .rotators import ROTCTLD, PSTRotator
from .telemlogger import TelemetryLogger
from horusdemodlib.demod import HorusLib, Mode
from horusdemodlib.decoder import decode_packet, parse_ukhas_string
from horusdemodlib.payloads import *
from horusdemodlib.horusudp import send_payload_summary, send_ozimux_message
from horusdemodlib.sondehubamateur import *
from . import __version__

# Read command-line arguments
parser = argparse.ArgumentParser(description="Project Horus GUI", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("--payload-id-list", type=str, default=None, help="Use supplied Payload ID List instead of downloading a new one.")
parser.add_argument("--custom-field-list", type=str, default=None, help="Use supplied Custom Field List instead of downloading a new one.")
parser.add_argument("--libfix", action="store_true", default=False, help="Search for libhorus.dll/so in ./ instead of on the path.")
parser.add_argument("--reset", action="store_true", default=False, help="Reset all configuration information on startup.")
parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output (set logging level to DEBUG)")
args = parser.parse_args()

if args.verbose:
    _log_level = logging.DEBUG
else:
    _log_level = logging.INFO

# Setup Logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s", level=_log_level
)

# This font seems to look bigger in Windows... not sure why.
if 'Windows' in platform.system():
    POSITION_LABEL_FONT_SIZE = 14
else:
    POSITION_LABEL_FONT_SIZE = 16

PEN_WIDTH=1

# Establish signals and worker for multi-threaded use
class WorkerSignals(QObject):
    # finished = pyqtSignal()
    error = pyqtSignal(tuple)
    # result = pyqtSignal(object)
    info = pyqtSignal(object)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        self.kwargs['info_callback'] = self.signals.info

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        # else:
        #     self.signals.result.emit(result)
        # finally:
        #     self.signals.finished.emit()

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1500, 800)

        self.threadpool = QThreadPool()
        self.stop_signal = False

        # A few hardcoded defaults
        self.DEFAULT_ESTIMATOR_MIN = 100
        self.DEFAULT_ESTIMATOR_MAX = 4000

        # Global widget store
        self.widgets = {}

        # List of audio devices and their info
        self.audio_devices = {}

        # Processor objects
        self.audio_stream = None
        self.fft_process = None
        self.horus_modem = None
        self.sondehub_uploader = None
        self.telemetry_logger = None

        self.last_packet_time = None

        # Rotator object
        self.rotator = None
        self.rotator_current_az = 0.0
        self.rotator_current_el = 0.0

        # Global running indicator
        self.running = False

        # Decoded packet signal
        self.new_packet_signal = WorkerSignals()
        self.new_packet_signal.info.connect(self.handle_new_packet)

        self.initialize()

    def initialize(self):
        # GUI LAYOUT - Gtk Style!
        self.setWindowTitle(f"Horus Telemetry GUI - v{__version__}")
        self.setWindowIcon(getHorusIcon())

        # Left Column VBox
        left_column = QVBoxLayout()

        # Controls
        w1_audio_groupbox = QGroupBox('Audio')
        w1_audio_groupbox.setObjectName("b1")
        w1_audio_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w1_audio = QGridLayout(w1_audio_groupbox)

        # Audio Parameters
        self.widgets["audioDeviceLabel"] = QLabel("<b>Audio Device:</b>")
        self.widgets["audioDeviceSelector"] = QComboBox()
        # self.widgets["audioDeviceSelector"].setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        # self.widgets["audioDeviceSelector"].setFixedWidth(275) # Dirty, but it needed to be done
        self.widgets["audioDeviceSelector"].currentIndexChanged.connect(self.update_audio_sample_rates)

        self.widgets["audioSampleRateLabel"] = QLabel("<b>Sample Rate (Hz):</b>")
        self.widgets["audioSampleRateSelector"] = QComboBox()

        self.widgets["audioDbfsLabel"] = QLabel("<b>Input Level (dBFS):</b>")
        self.widgets["audioDbfsValue"] = QLabel("--")
        self.widgets["audioDbfsValue_float"] = 0.0

        w1_audio.addWidget(self.widgets["audioDeviceLabel"], 0, 0, 1, 3)
        w1_audio.addWidget(self.widgets["audioDeviceSelector"], 1, 0, 1, 3)
        w1_audio.addWidget(self.widgets["audioSampleRateLabel"], 2, 0, 1, 1)
        w1_audio.addWidget(self.widgets["audioSampleRateSelector"], 2, 1, 1, 2)
        w1_audio.addWidget(self.widgets["audioDbfsLabel"], 3, 0, 1, 1)
        w1_audio.addWidget(self.widgets["audioDbfsValue"], 3, 1, 1, 2)
        w1_audio_groupbox.setLayout(w1_audio)

        # Modem Parameters
        w1_modem_groupbox = QGroupBox('Modem')
        w1_modem_groupbox.setObjectName("b1")
        w1_modem_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w1_modem = QGridLayout(w1_modem_groupbox)

        self.widgets["horusModemLabel"] = QLabel("<b>Mode:</b>")
        self.widgets["horusModemSelector"] = QComboBox()
        self.widgets["horusModemSelector"].currentIndexChanged.connect(self.update_modem_settings)

        self.widgets["horusModemRateLabel"] = QLabel("<b>Baudrate:</b>")
        self.widgets["horusModemRateSelector"] = QComboBox()

        self.widgets["horusMaskEstimatorLabel"] = QLabel("<b>Enable Mask Estim.:</b>")
        self.widgets["horusMaskEstimatorSelector"] = QCheckBox()
        self.widgets["horusMaskEstimatorSelector"].setToolTip(
            "Enable the mask frequency estimator, which makes uses of the \n"\
            "tone spacing value entered below as extra input to the frequency\n"\
            "estimator. This can help decode performance in very weak signal conditions."
        )

        self.widgets["horusMaskSpacingLabel"] = QLabel("<b>Tone Spacing (Hz):</b>")
        self.widgets["horusMaskSpacingEntry"] = QLineEdit("270")
        self.widgets["horusMaskSpacingEntry"].setToolTip(
            "If the tone spacing of the transmitter is known, it can be entered here,\n"\
            "and used with the mask estimator option above. The default tone spacing for\n"\
            "a RS41-based transmitter is 270 Hz."
        )
        self.widgets["horusManualEstimatorLabel"] = QLabel("<b>Manual Estim. Limits:</b>")
        self.widgets["horusManualEstimatorSelector"] = QCheckBox()
        self.widgets["horusManualEstimatorSelector"].setToolTip(
            "Enables manual selection of the frequency estimator limits. This will enable\n"\
            "a slidable area on the spectrum display, which can be used to select the frequency\n"\
            "range of interest, and help stop in-band CW interference from biasing the frequency\n"\
            "estimator. You can either click-and-drag the entire area, or click-and-drag the edges\n"\
            "to change the estimator frequency range."
        )
        self.widgets["horusManualEstimatorSelector"].clicked.connect(self.set_manual_estimator)

        # Start/Stop
        self.widgets["startDecodeButton"] = QPushButton("Start")
        self.widgets["startDecodeButton"].setEnabled(False)
        self.widgets["startDecodeButton"].clicked.connect(self.start_decoding)

        w1_modem.addWidget(self.widgets["horusModemLabel"], 0, 0, 1, 1)
        w1_modem.addWidget(self.widgets["horusModemSelector"], 0, 1, 1, 1)
        w1_modem.addWidget(self.widgets["horusModemRateLabel"], 1, 0, 1, 1)
        w1_modem.addWidget(self.widgets["horusModemRateSelector"], 1, 1, 1, 1)
        w1_modem.addWidget(self.widgets["horusMaskEstimatorLabel"], 2, 0, 1, 1)
        w1_modem.addWidget(self.widgets["horusMaskEstimatorSelector"], 2, 1, 1, 1)
        w1_modem.addWidget(self.widgets["horusMaskSpacingLabel"], 3, 0, 1, 1)
        w1_modem.addWidget(self.widgets["horusMaskSpacingEntry"], 3, 1, 1, 1)
        w1_modem.addWidget(self.widgets["horusManualEstimatorLabel"], 4, 0, 1, 1)
        w1_modem.addWidget(self.widgets["horusManualEstimatorSelector"], 4, 1, 1, 1)
        w1_modem.addWidget(self.widgets["startDecodeButton"], 5, 0, 2, 2)
        w1_modem_groupbox.setLayout(w1_modem)


        w1_habitat_widget = QWidget()
        w1_habitat = QGridLayout(w1_habitat_widget)
        # Listener Information
        self.widgets["habitatHeading"] = QLabel("<b>SondeHub Settings</b>")
        self.widgets["sondehubUploadLabel"] = QLabel("<b>Enable SondeHub Upload:</b>")
        self.widgets["sondehubUploadSelector"] = QCheckBox()
        self.widgets["sondehubUploadSelector"].setChecked(True)
        self.widgets["sondehubUploadSelector"].clicked.connect(self.habitat_inhibit)
        self.widgets["userCallLabel"] = QLabel("<b>Callsign:</b>")
        self.widgets["userCallEntry"] = QLineEdit("N0CALL")
        self.widgets["userCallEntry"].setMaxLength(20)
        self.widgets["userCallEntry"].setToolTip(
            "Your station callsign, which doesn't necessarily need to be an\n"\
            "amateur radio callsign, just something unique!"
        )
        self.widgets["userCallEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["userLocationLabel"] = QLabel("<b>Latitude / Longitude:</b>")
        self.widgets["userLatEntry"] = QLineEdit("0.0")
        self.widgets["userLatEntry"].setToolTip("Station Latitude in Decimal Degrees, e.g. -34.123456")
        self.widgets["userLatEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["userLonEntry"] = QLineEdit("0.0")
        self.widgets["userLonEntry"].setToolTip("Station Longitude in Decimal Degrees, e.g. 138.123456")
        self.widgets["userLonEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["userAltitudeLabel"] = QLabel("<b>Altitude:</b>")
        self.widgets["userAltEntry"] = QLineEdit("0.0")
        self.widgets["userAltEntry"].setToolTip("Station Altitude in Metres Above Sea Level.")
        self.widgets["userAltEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["userAntennaLabel"] = QLabel("<b>Antenna:</b>")
        self.widgets["userAntennaEntry"] = QLineEdit("")
        self.widgets["userAntennaEntry"].setToolTip("A text description of your station's antenna.")
        self.widgets["userAntennaEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["userRadioLabel"] = QLabel("<b>Radio:</b>")
        self.widgets["userRadioEntry"] = QLineEdit("Horus-GUI " + __version__)
        self.widgets["userRadioEntry"].setToolTip(
            "A text description of your station's radio setup.\n"\
            "This field will be automatically prefixed with Horus-GUI\n"\
            "and the Horus-GUI software version."
        )
        self.widgets["userRadioEntry"].textEdited.connect(self.update_uploader_details)
        self.widgets["habitatUploadPosition"] = QPushButton("Re-upload Station Info")
        self.widgets["habitatUploadPosition"].setToolTip(
            "Manually re-upload your station information to SondeHub-Amateur.\n"\
        )
        # Connect the 'Re-upload Position' button to the above function.
        self.widgets["habitatUploadPosition"].clicked.connect(self.habitat_position_reupload)
        self.widgets["dialFreqLabel"] = QLabel("<b>Radio Dial Freq (MHz):</b>")
        self.widgets["dialFreqEntry"] = QLineEdit("")
        self.widgets["dialFreqEntry"].setToolTip(
            "Optional entry of your radio's dial frequency in MHz (e.g. 437.600).\n"\
            "Used to provide frequency information on SondeHub-Amateur."\
        )
        self.widgets["sondehubPositionNotesLabel"] = QLabel("")

        self.widgets["saveSettingsButton"] = QPushButton("Save Settings")
        self.widgets["saveSettingsButton"].clicked.connect(self.save_settings)

        w1_habitat.addWidget(self.widgets["sondehubUploadLabel"], 0, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["sondehubUploadSelector"], 0, 1, 1, 1)
        w1_habitat.addWidget(self.widgets["userCallLabel"], 1, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["userCallEntry"], 1, 1, 1, 2)
        w1_habitat.addWidget(self.widgets["userLocationLabel"], 2, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["userLatEntry"], 2, 1, 1, 1)
        w1_habitat.addWidget(self.widgets["userLonEntry"], 2, 2, 1, 1)
        w1_habitat.addWidget(self.widgets["userAltitudeLabel"], 3, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["userAltEntry"], 3, 1, 1, 2)
        w1_habitat.addWidget(self.widgets["userAntennaLabel"], 4, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["userAntennaEntry"], 4, 1, 1, 2)
        w1_habitat.addWidget(self.widgets["userRadioLabel"], 5, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["userRadioEntry"], 5, 1, 1, 2)
        w1_habitat.addWidget(self.widgets["dialFreqLabel"], 6, 0, 1, 1)
        w1_habitat.addWidget(self.widgets["dialFreqEntry"], 6, 1, 1, 2)
        w1_habitat.addWidget(self.widgets["habitatUploadPosition"], 7, 0, 1, 3)
        w1_habitat.addWidget(self.widgets["sondehubPositionNotesLabel"], 8, 0, 1, 3)
        w1_habitat.setRowStretch(9, 1) 
        w1_habitat.addWidget(self.widgets["saveSettingsButton"], 10, 0, 1, 3)
        w1_habitat_widget.setLayout(w1_habitat)

        w1_other_widget = QWidget()
        w1_other = QGridLayout(w1_other_widget)
        self.widgets["horusHeaderLabel"] = QLabel("<b><u>Telemetry Forwarding</u></b>")
        self.widgets["horusUploadLabel"] = QLabel("<b>Enable Horus UDP Output:</b>")
        self.widgets["horusUploadSelector"] = QCheckBox()
        self.widgets["horusUploadSelector"].setChecked(True)
        self.widgets["horusUploadSelector"].setToolTip(
            "Enable output of 'Horus UDP' JSON messages. These are emitted as a JSON object\n"\
            "and contain the fields: callsign, time, latitude, longitude, altitude, snr"\
        )
        self.widgets["horusUDPLabel"] = QLabel("<b>Horus UDP Port:</b>")
        self.widgets["horusUDPEntry"] = QLineEdit("55672")
        self.widgets["horusUDPEntry"].setMaxLength(5)
        self.widgets["horusUDPEntry"].setToolTip(
            "UDP Port to output 'Horus UDP' JSON messages to."
        )
        self.widgets["ozimuxUploadLabel"] = QLabel("<b>Enable OziMux UDP Output:</b>")
        self.widgets["ozimuxUploadSelector"] = QCheckBox()
        self.widgets["ozimuxUploadSelector"].setChecked(False)
        self.widgets["ozimuxUploadSelector"].setToolTip(
            "Output OziMux UDP messages. These are of the form:\n"\
            "'TELEMETRY,HH:MM:SS,lat,lon,alt\\n'"
        )
        self.widgets["ozimuxUDPLabel"] = QLabel("<b>Ozimux UDP Port:</b>")
        self.widgets["ozimuxUDPEntry"] = QLineEdit("55683")
        self.widgets["ozimuxUDPEntry"].setMaxLength(5)
        self.widgets["ozimuxUDPEntry"].setToolTip(
            "UDP Port to output 'OziMux' UDP messages to."
        )
        self.widgets["loggingHeaderLabel"] = QLabel("<b><u>Logging</u></b>")
        self.widgets["enableLoggingLabel"] = QLabel("<b>Enable Logging:</b>")
        self.widgets["enableLoggingSelector"] = QCheckBox()
        self.widgets["enableLoggingSelector"].setChecked(False)
        self.widgets["enableLoggingSelector"].setToolTip(
            "Enable logging of received telemetry to disk (JSON)"
        )
        self.widgets["enableLoggingSelector"].clicked.connect(self.set_logging_state)
        self.widgets["loggingFormatLabel"] = QLabel("<b>Log Format:</b>")
        self.widgets["loggingFormatSelector"] = QComboBox()
        self.widgets["loggingFormatSelector"].addItem("CSV")
        self.widgets["loggingFormatSelector"].addItem("JSON")
        self.widgets["loggingFormatSelector"].currentIndexChanged.connect(self.set_logging_format)
        self.widgets["loggingPathLabel"] = QLabel("<b>Log Directory:</b>")
        self.widgets["loggingPathEntry"] = QLineEdit("")
        self.widgets["loggingPathEntry"].setToolTip(
            "Logging Directory"
        )
        self.widgets["selectLogDirButton"] = QPushButton("Select Directory")
        self.widgets["selectLogDirButton"].clicked.connect(self.select_log_directory)

        self.widgets["otherHeaderLabel"] = QLabel("<b><u>Other Settings</u></b>")
        self.widgets["inhibitCRCLabel"] = QLabel("<b>Hide Failed CRC Errors:</b>")
        self.widgets["inhibitCRCSelector"] = QCheckBox()
        self.widgets["inhibitCRCSelector"].setChecked(True)
        self.widgets["inhibitCRCSelector"].setToolTip(
            "Hide CRC Failed error messages."
        )
        self.widgets["fftSmoothingLabel"] = QLabel("<b>Enable FFT smoothing:</b>")
        self.widgets["fftSmoothingSelector"] = QCheckBox()
        self.widgets["fftSmoothingSelector"].setChecked(False)
        self.widgets["fftSmoothingSelector"].setToolTip(
            "Enable IIR filter on FFT with tc=0.25."
        )

        w1_other.addWidget(self.widgets["horusHeaderLabel"], 0, 0, 1, 2)
        w1_other.addWidget(self.widgets["horusUploadLabel"], 1, 0, 1, 1)
        w1_other.addWidget(self.widgets["horusUploadSelector"], 1, 1, 1, 1)
        w1_other.addWidget(self.widgets["horusUDPLabel"], 2, 0, 1, 1)
        w1_other.addWidget(self.widgets["horusUDPEntry"], 2, 1, 1, 1)
        w1_other.addWidget(self.widgets["ozimuxUploadLabel"], 3, 0, 1, 1)
        w1_other.addWidget(self.widgets["ozimuxUploadSelector"], 3, 1, 1, 1)
        w1_other.addWidget(self.widgets["ozimuxUDPLabel"], 4, 0, 1, 1)
        w1_other.addWidget(self.widgets["ozimuxUDPEntry"], 4, 1, 1, 1)
        w1_other.addWidget(self.widgets["loggingHeaderLabel"], 5, 0, 1, 2)
        w1_other.addWidget(self.widgets["enableLoggingLabel"], 6, 0, 1, 1)
        w1_other.addWidget(self.widgets["enableLoggingSelector"], 6, 1, 1, 1)
        w1_other.addWidget(self.widgets["loggingFormatLabel"], 7, 0, 1, 1)
        w1_other.addWidget(self.widgets["loggingFormatSelector"], 7, 1, 1, 1)
        w1_other.addWidget(self.widgets["loggingPathLabel"], 8, 0, 1, 1)
        w1_other.addWidget(self.widgets["loggingPathEntry"], 8, 1, 1, 1)
        w1_other.addWidget(self.widgets["selectLogDirButton"], 9, 0, 1, 2)
        w1_other.addWidget(self.widgets["otherHeaderLabel"], 10, 0, 1, 2)
        w1_other.addWidget(self.widgets["inhibitCRCLabel"], 11, 0, 1, 1)
        w1_other.addWidget(self.widgets["inhibitCRCSelector"], 11, 1, 1, 1)
        w1_other.addWidget(self.widgets["fftSmoothingLabel"], 12, 0, 1, 1)
        w1_other.addWidget(self.widgets["fftSmoothingSelector"], 12, 1, 1, 1)
        w1_other.setRowStretch(13, 1)
        w1_other_widget.setLayout(w1_other)


        w1_rotator_widget = QWidget()
        w1_rotator = QGridLayout(w1_rotator_widget)
        self.widgets["rotatorHeaderLabel"] = QLabel("<b><u>Rotator Control</u></b>")

        self.widgets["rotatorTypeLabel"] = QLabel("<b>Rotator Type:</b>")
        self.widgets["rotatorTypeSelector"] = QComboBox()
        self.widgets["rotatorTypeSelector"].addItem("rotctld")
        self.widgets["rotatorTypeSelector"].addItem("PSTRotator")

        self.widgets["rotatorHostLabel"] = QLabel("<b>Rotator Hostname:</b>")
        self.widgets["rotatorHostEntry"] = QLineEdit("localhost")
        self.widgets["rotatorHostEntry"].setToolTip(
            "Hostname of the rotctld or PSTRotator Server.\n"\
        )

        self.widgets["rotatorPortLabel"] = QLabel("<b>Rotator TCP/UDP Port:</b>")
        self.widgets["rotatorPortEntry"] = QLineEdit("4533")
        self.widgets["rotatorPortEntry"].setMaxLength(5)
        self.widgets["rotatorPortEntry"].setToolTip(
            "TCP (rotctld) or UDP (PSTRotator) port to connect to.\n"\
            "Default for rotctld: 4533\n"\
            "Default for PSTRotator: 12000"
        )
        self.widgets["rotatorRangeInhibitLabel"] = QLabel("<b>Inhibit Local Movement:</b>")
        self.widgets["rotatorRangeInhibit"] = QCheckBox()
        self.widgets["rotatorRangeInhibit"].setChecked(True)
        self.widgets["rotatorRangeInhibit"].setToolTip(
            "Inhibit Horus GUI from sending rotator position updates\n"\
            "if range is less than 250 meters. This is useful if testing\n"\
            "transmitter in close vicinity of receiver."
        )
        self.widgets["rotatorThresholdLabel"] = QLabel("<b>Rotator Movement Threshold:</b>")
        self.widgets["rotatorThresholdEntry"] = QLineEdit("2.5")
        self.widgets["rotatorThresholdEntry"].setToolTip(
            "Only move if the angle between the payload position and \n"\
            "the current rotator position is more than this, in degrees."
        )

        self.widgets["rotatorConnectButton"] = QPushButton("Start")
        self.widgets["rotatorConnectButton"].clicked.connect(self.startstop_rotator)

        self.widgets["rotatorCurrentStatusLabel"] = QLabel("<b>Status:</b>")
        self.widgets["rotatorCurrentStatusValue"] = QLabel("Not Started.")

        self.widgets["rotatorCurrentPositionLabel"] = QLabel("<b>Commanded Az/El:</b>")
        self.widgets["rotatorCurrentPositionValue"] = QLabel("---˚, --˚")



        w1_rotator.addWidget(self.widgets["rotatorHeaderLabel"], 0, 0, 1, 2)
        w1_rotator.addWidget(self.widgets["rotatorTypeLabel"], 1, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorTypeSelector"], 1, 1, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorHostLabel"], 2, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorHostEntry"], 2, 1, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorPortLabel"], 3, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorPortEntry"], 3, 1, 1, 1)
        #w1_rotator.addWidget(self.widgets["rotatorThresholdLabel"], 4, 0, 1, 1)
        #w1_rotator.addWidget(self.widgets["rotatorThresholdEntry"], 4, 1, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorRangeInhibitLabel"], 5, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorRangeInhibit"], 5, 1, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorConnectButton"], 6, 0, 1, 2)
        w1_rotator.addWidget(self.widgets["rotatorCurrentStatusLabel"], 7, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorCurrentStatusValue"], 7, 1, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorCurrentPositionLabel"], 8, 0, 1, 1)
        w1_rotator.addWidget(self.widgets["rotatorCurrentPositionValue"], 8, 1, 1, 1)
        w1_rotator.setRowStretch(9, 1)

        w1_rotator_widget.setLayout(w1_rotator)

        w1_tab_widget = QTabWidget()
        w1_tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        w1_tab_widget.tabBar().setExpanding(True)
        w1_tab_widget.addTab(w1_habitat_widget, "SondeHub")
        w1_tab_widget.addTab(w1_other_widget, "Other")
        w1_tab_widget.addTab(w1_rotator_widget, "Rotator")
        w1_tab_widget.setStyleSheet("QTabBar {font: bold 14px;}")

        # Add widgets to left column
        left_column.addWidget(w1_audio_groupbox) #, 0, 0, 1, 1)
        left_column.addWidget(w1_modem_groupbox) #, 1, 0, 1, 1)
        left_column.addWidget(w1_tab_widget) #, 2, 0, 1, 1)

        # Right Column QGrid (Grid for merged cells)
        right_column = QGridLayout()

        # Spectrum Display
        self.widgets["spectrumPlot"] = pg.PlotWidget(title="Spectra")
        self.widgets["spectrumPlot"].setLabel("left", "Power (dB)")
        self.widgets["spectrumPlot"].setLabel("bottom", "Frequency (Hz)")
        self.widgets["spectrumPlotData"] = self.widgets["spectrumPlot"].plot([0], pen=pg.mkPen(width=PEN_WIDTH))

        # Frequency Estiator Outputs
        self.widgets["estimatorLines"] = [
            pg.InfiniteLine(
                pos=-1000,
                pen=pg.mkPen(color="grey", width=(PEN_WIDTH + 1), style=QtCore.Qt.PenStyle.DashLine),
                label="F1",
                labelOpts={'position':0.9}
            ),
            pg.InfiniteLine(
                pos=-1000,
                pen=pg.mkPen(color="grey", width=(PEN_WIDTH + 1), style=QtCore.Qt.PenStyle.DashLine),
                label="F2",
                labelOpts={'position':0.9}
            ),
            pg.InfiniteLine(
                pos=-1000,
                pen=pg.mkPen(color="grey", width=(PEN_WIDTH + 1), style=QtCore.Qt.PenStyle.DashLine),
                label="F3",
                labelOpts={'position':0.9}
            ),
            pg.InfiniteLine(
                pos=-1000,
                pen=pg.mkPen(color="grey", width=(PEN_WIDTH + 1), style=QtCore.Qt.PenStyle.DashLine),
                label="F4",
                labelOpts={'position':0.9}
            ),
        ]
        for _line in self.widgets["estimatorLines"]:
            self.widgets["spectrumPlot"].addItem(_line)

        self.widgets["spectrumPlot"].setLabel("left", "Power (dBFs)")
        self.widgets["spectrumPlot"].setLabel("bottom", "Frequency", units="Hz")
        self.widgets["spectrumPlot"].setXRange(100, 4000)
        self.widgets["spectrumPlot"].setYRange(-100, -20)
        self.widgets["spectrumPlot"].setLimits(xMin=100, xMax=4000, yMin=-120, yMax=0)
        self.widgets["spectrumPlot"].showGrid(True, True)

        self.widgets["estimatorRange"] = pg.LinearRegionItem([100,3000])
        self.widgets["estimatorRange"].setBounds([100,4000])
        self.widgets["estimatorRange"].sigRegionChangeFinished.connect(self.update_manual_estimator)

        w2_spectrum_groupbox = QGroupBox("Spectrum")
        w2_spectrum_groupbox.setObjectName("b1")
        w2_spectrum_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        spectrum = QGridLayout(w2_spectrum_groupbox)
        spectrum.addWidget(self.widgets["spectrumPlot"])

        self.widgets["spectrumPlotRange"] = [-100, -20]

        w3_stats_groupbox = QGroupBox("SNR (dB)")
        w3_stats_groupbox.setObjectName("b1")
        w3_stats_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w3_stats = QGridLayout(w3_stats_groupbox)
        self.widgets["snrBar"] = QProgressBar()
        self.widgets["snrBar"].setOrientation(QtCore.Qt.Orientation.Vertical)
        self.widgets["snrBar"].setRange(-10, 15)
        self.widgets["snrBar"].setValue(-10)
        self.widgets["snrBar"].setTextVisible(False)
        self.widgets["snrBar"].setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.widgets["snrLabel"] = QLabel("--.-")
        self.widgets["snrLabel"].setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);
        self.widgets["snrLabel"].setFont(QFont("Courier New", 14))
        w3_stats.addWidget(self.widgets["snrBar"], 0, 1, 1, 1)
        w3_stats.addWidget(self.widgets["snrLabel"], 1, 0, 1, 3)
        w3_stats.setColumnStretch(0, 2)
        w3_stats.setColumnStretch(2, 2)

        w3_stats_groupbox.setLayout(w3_stats)


        # SNR Plot
        w3_snr_groupbox = QGroupBox("SNR Plot")
        w3_snr_groupbox.setObjectName("b1")
        w3_snr_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w3_snr = QGridLayout(w3_snr_groupbox)
        self.widgets["snrPlot"] = pg.PlotWidget(title="SNR")
        self.widgets["snrPlot"].setLabel("left", "SNR (dB)")
        self.widgets["snrPlot"].setLabel("bottom", "Time (s)")
        self.widgets["snrPlot"].setXRange(-60, 0)
        self.widgets["snrPlot"].setYRange(-10, 30)
        self.widgets["snrPlot"].setLimits(xMin=-60, xMax=0, yMin=-10, yMax=40)
        self.widgets["snrPlot"].showGrid(True, True)
        self.widgets["snrPlotRange"] = [-10, 30]
        self.widgets["snrPlotTime"] = np.array([])
        self.widgets["snrPlotSNR"] = np.array([])
        self.widgets["snrPlotData"] = self.widgets["snrPlot"].plot(self.widgets["snrPlotTime"], self.widgets["snrPlotSNR"], pen=pg.mkPen(width=PEN_WIDTH))
        w3_snr.addWidget(self.widgets["snrPlot"])

        w3_snr_groupbox.setLayout(w3_snr)

        # TODO: Look into eye diagram more
        # self.widgets["eyeDiagramPlot"] = pg.PlotWidget(title="Eye Diagram")
        # self.widgets["eyeDiagramData"] = self.widgets["eyeDiagramPlot"].plot([0])

        #w3_snr.addWidget(self.widgets["snrPlot"], 0, 1, 2, 1)

        #w3.addWidget(self.widgets["eyeDiagramPlot"], 0, 1)

        # Telemetry Data
        w4_data_groupbox = QGroupBox("Data")
        w4_data_groupbox.setObjectName("b1")
        w4_data_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w4_data = QGridLayout(w4_data_groupbox)
        self.widgets["latestRawSentenceLabel"] = QLabel("<b>Latest Packet (Raw):</b>")
        self.widgets["latestRawSentenceData"] = QLineEdit("NO DATA")
        self.widgets["latestRawSentenceData"].setReadOnly(True)
        self.widgets["latestDecodedSentenceLabel"] = QLabel("<b>Latest Packet (Decoded):</b>")
        self.widgets["latestDecodedSentenceData"] = QLineEdit("NO DATA")
        self.widgets["latestDecodedSentenceData"].setReadOnly(True)
        self.widgets["latestDecodedAgeLabel"] = QLabel("<b>Last Packet Age:</b>")
        self.widgets["latestDecodedAgeData"] = QLabel("No packet yet!")
        w4_data.addWidget(self.widgets["latestRawSentenceLabel"], 0, 0, 1, 1)
        w4_data.addWidget(self.widgets["latestRawSentenceData"], 0, 1, 1, 6)
        w4_data.addWidget(self.widgets["latestDecodedSentenceLabel"], 1, 0, 1, 1)
        w4_data.addWidget(self.widgets["latestDecodedSentenceData"], 1, 1, 1, 6)
        w4_data.addWidget(self.widgets["latestDecodedAgeLabel"], 2, 0, 1, 1)
        w4_data.addWidget(self.widgets["latestDecodedAgeData"], 2, 1, 1, 2)

        w4_data_groupbox.setLayout(w4_data)

        w4_position_groupbox = QGroupBox("Position")
        w4_position_groupbox.setObjectName("b1")
        w4_position_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w4_position = QGridLayout(w4_position_groupbox)

        self.widgets["latestPacketCallsignLabel"] = QLabel("<b>Callsign</b>")
        self.widgets["latestPacketCallsignValue"] = QLabel("---")
        self.widgets["latestPacketCallsignValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketTimeLabel"] = QLabel("<b>Time</b>")
        self.widgets["latestPacketTimeValue"] = QLabel("---")
        self.widgets["latestPacketTimeValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketLatitudeLabel"] = QLabel("<b>Latitude</b>")
        self.widgets["latestPacketLatitudeValue"] = QLabel("---")
        self.widgets["latestPacketLatitudeValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketLongitudeLabel"] = QLabel("<b>Longitude</b>")
        self.widgets["latestPacketLongitudeValue"] = QLabel("---")
        self.widgets["latestPacketLongitudeValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketAltitudeLabel"] = QLabel("<b>Altitude</b>")
        self.widgets["latestPacketAltitudeValue"] = QLabel("---")
        self.widgets["latestPacketAltitudeValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketBearingLabel"] = QLabel("<b>Bearing</b>")
        self.widgets["latestPacketBearingValue"] = QLabel("---")
        self.widgets["latestPacketBearingValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketElevationLabel"] = QLabel("<b>Elevation</b>")
        self.widgets["latestPacketElevationValue"] = QLabel("---")
        self.widgets["latestPacketElevationValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestPacketRangeLabel"] = QLabel("<b>Range (km)</b>")
        self.widgets["latestPacketRangeValue"] = QLabel("---")
        self.widgets["latestPacketRangeValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))

        w4_position.addWidget(self.widgets["latestPacketCallsignLabel"], 0, 0, 1, 2)
        w4_position.addWidget(self.widgets["latestPacketCallsignValue"], 1, 0, 1, 2)
        w4_position.addWidget(self.widgets["latestPacketTimeLabel"], 0, 2, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketTimeValue"], 1, 2, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketLatitudeLabel"], 0, 3, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketLatitudeValue"], 1, 3, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketLongitudeLabel"], 0, 4, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketLongitudeValue"], 1, 4, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketAltitudeLabel"], 0, 5, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketAltitudeValue"], 1, 5, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketBearingLabel"], 0, 7, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketBearingValue"], 1, 7, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketElevationLabel"], 0, 8, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketElevationValue"], 1, 8, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketRangeLabel"], 0, 9, 1, 1)
        w4_position.addWidget(self.widgets["latestPacketRangeValue"], 1, 9, 1, 1)
        #w4_position.setRowStretch(1, 6)

        w4_position_groupbox.setLayout(w4_position)

        w5_telemetry_groupbox = QGroupBox("Telemetry")
        w5_telemetry_groupbox.setObjectName("b1")
        w5_telemetry_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        self.w5_telemetry = QGridLayout(w5_telemetry_groupbox)
        w5_telemetry_groupbox.setLayout(self.w5_telemetry)

        # These are placeholders and will be updated when telemetry is received. 
        self.widgets["latestTelemBattVoltageLabel"] = QLabel("<b>Batt Voltage</b>")
        self.widgets["latestTelemBattVoltageValue"] = QLabel("---")
        self.widgets["latestTelemBattVoltageValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestTelemSatellitesLabel"] = QLabel("<b>Satellites</b>")
        self.widgets["latestTelemSatellitesValue"] = QLabel("---")
        self.widgets["latestTelemSatellitesValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestTelemTemperatureLabel"] = QLabel("<b>Temperature</b>")
        self.widgets["latestTelemTemperatureValue"] = QLabel("---")
        self.widgets["latestTelemTemperatureValue"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemBattVoltageLabel"], 0, 0, 1, 1)
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemBattVoltageValue"], 1, 0, 1, 1)
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemSatellitesLabel"], 0, 1, 1, 1)
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemSatellitesValue"], 1, 1, 1, 1)
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemTemperatureLabel"], 0, 2, 1, 1)
        self.w5_telemetry.addWidget(self.widgets[f"latestTelemTemperatureValue"], 1, 2, 1, 1)

        self.widgets["latestTelem0Label"] = QLabel("<b>Ascent Rate</b>")
        self.widgets["latestTelem0Value"] = QLabel("---")
        self.widgets["latestTelem0Value"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestTelem1Label"] = QLabel("<b>External Temperature</b>")
        self.widgets["latestTelem1Value"] = QLabel("---")
        self.widgets["latestTelem1Value"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestTelem2Label"] = QLabel("<b>External Humidity</b>")
        self.widgets["latestTelem2Value"] = QLabel("---")
        self.widgets["latestTelem2Value"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        self.widgets["latestTelem3Label"] = QLabel("<b>External Pressure</b>")
        self.widgets["latestTelem3Value"] = QLabel("---")
        self.widgets["latestTelem3Value"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))
        for i in range(4,9):
            self.widgets[f"latestTelem{i}Label"] = QLabel("")
            self.widgets[f"latestTelem{i}Value"] = QLabel("")
            self.widgets[f"latestTelem{i}Label"].hide()
            self.widgets[f"latestTelem{i}Value"].hide()
            self.widgets[f"latestTelem{i}Value"].setFont(QFont("Courier New", POSITION_LABEL_FONT_SIZE, QFont.Weight.Bold))

        for i in range(0,9):
            self.w5_telemetry.addWidget(self.widgets[f"latestTelem{i}Label"], 0, i+3, 1, 1)
            self.w5_telemetry.addWidget(self.widgets[f"latestTelem{i}Value"], 1, i+3, 1, 1)

        for i in range(0,7):
            self.w5_telemetry.setColumnStretch(i, 10)
        
        for i in range(7, 12):
            self.w5_telemetry.setColumnStretch(i, 1)

        #self.w5_telemetry.setRowStretch(1, 6)

        w6_groupbox = QGroupBox("Log")
        w6_groupbox.setObjectName("b1")
        w6_groupbox.setStyleSheet('QWidget#b1 { font-size: 15px; font-weight: bold}')
        w6 = QGridLayout(w6_groupbox)
        self.widgets["console"] = QPlainTextEdit()
        self.widgets["console"].setReadOnly(True)
        self.widgets["console"].setMaximumBlockCount(1000)
        w6.addWidget(self.widgets["console"])
        w6.setRowStretch(0, 1)
        
        w6_groupbox.setLayout(w6)

        right_column.addWidget(w2_spectrum_groupbox, 0, 0, 1, 1)
        right_column.addWidget(w3_snr_groupbox, 0, 1, 1, 1)
        right_column.addWidget(w3_stats_groupbox, 0, 2, 1, 1)
        right_column.addWidget(w4_data_groupbox, 1, 0, 1, 3)
        right_column.addWidget(w4_position_groupbox, 2, 0, 1, 3)
        right_column.addWidget(w5_telemetry_groupbox, 3, 0, 1, 3)
        right_column.addWidget(w6_groupbox, 4, 0, 1, 3)

        right_column.setColumnStretch(0, 10)
        right_column.setColumnStretch(1, 6)
        right_column.setColumnStretch(2, 1)

        left_column_widget = QWidget()
        left_column_widget.setLayout(left_column)

        right_column_widget = QWidget()
        right_column_widget.setLayout(right_column)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_column_widget)
        splitter.addWidget(right_column_widget)

        self.mainWidget = QWidget()
        self.setCentralWidget(self.mainWidget)
        self.mainLayout = QHBoxLayout()
        self.mainWidget.setLayout(self.mainLayout)

        self.mainLayout.addWidget(splitter)

        # self.mainLayout = QGridLayout()
        # self.mainWidget.setLayout(self.mainLayout)?

        # # Grid: (Row, Column, RowSpan, ColumnSpan)
        # self.mainLayout.addLayout(left_column, 0, 0, 1, 1)
        # self.mainLayout.addLayout(right_column, 0, 1, 1, 1)

        # self.mainLayout.setColumnStretch(0, 1)
        # self.mainLayout.setColumnStretch(1, 10)

        # Resize window to final resolution, and display.
        logging.info("Starting GUI.")
        self.resize(1500, self.minimumSize().height())

        self.post_initialize()


    def post_initialize(self):
        # Audio Initialization
        self.audio_devices = init_audio(self.widgets)

        # Initialize modem list.
        init_horus_modem(self.widgets)

        # Clear the configuration if we have been asked to, otherwise read it in from Qt stores
        if args.reset:
            logging.info("Clearing configuration.")
            write_config()
        else:
            read_config(self.widgets)


        try:
            if float(self.widgets["userLatEntry"].text()) == 0.0 and float(self.widgets["userLonEntry"].text()) == 0.0:
                _sondehub_user_pos = None
            else:
                _sondehub_user_pos = [float(self.widgets["userLatEntry"].text()), float(self.widgets["userLonEntry"].text()), 0.0]
        except:
            _sondehub_user_pos = None

        self.sondehub_uploader = SondehubAmateurUploader(
            upload_rate = 2,
            user_callsign = self.widgets["userCallEntry"].text(),
            user_position = _sondehub_user_pos,
            user_radio = "Horus-GUI v" + __version__ + " " + self.widgets["userRadioEntry"].text(),
            user_antenna = self.widgets["userAntennaEntry"].text(),
            software_name = "Horus-GUI",
            software_version = __version__,
        )

        self.telemetry_logger = TelemetryLogger(
            log_directory = self.widgets["loggingPathEntry"].text(),
            log_format = self.widgets["loggingFormatSelector"].currentText(),
            enabled = self.widgets["enableLoggingSelector"].isChecked()
        )

        # Init payload IDs and such in singleShot timer
        self.payload_init_timer = QTimer()
        self.payload_init_timer.singleShot(100, self.payload_init)

        # Add console handler to top level logger.
        console_handler = ConsoleHandler(self.handle_log_update)
        logging.getLogger().addHandler(console_handler)

        logging.info("Started GUI.")


    def cleanup(self):
        self.running = False

        try:
            if self.horus_modem:
                self.horus_modem.close()
                self.horus_modem = None
        except Exception as e:
            pass

        try:
            self.audio_stream.stop()
        except Exception as e:
            pass

        try:
            self.fft_process.stop()
        except Exception as e:
            pass

        try:
            self.sondehub_uploader.close()
        except:
            pass

        if self.rotator:
            try:
                self.rotator.close()
            except:
                pass

        try:
            self.telemetry_logger.close()
        except:
            pass


    def update_audio_sample_rates(self):
        """ Update the sample-rate dropdown when a different audio device is selected.  """
        # Pass widgets straight on to function from .audio
        populate_sample_rates(self.widgets)


    def update_modem_settings(self):
        """ Update the modem setting widgets when a different modem is selected """
        populate_modem_settings(self.widgets)


    def select_log_directory(self):
        folder = str(QFileDialog.getExistingDirectory(None, "Select Directory"))

        if folder is None:
            logging.info("No log directory selected.")
            return False
        else:
            if folder == "":
                logging.info("No log directory selected.")
                return False
            else:
                self.widgets["loggingPathEntry"].setText(folder)
                self.widgets["enableLoggingSelector"].setChecked(False)
                if self.telemetry_logger:
                    self.widgets["enableLoggingSelector"].setChecked(True)
                    self.telemetry_logger.update_log_directory(self.widgets["loggingPathEntry"].text())
                    self.telemetry_logger.enabled = True
                
                return True


    def set_logging_state(self):
        logging_enabled = self.widgets["enableLoggingSelector"].isChecked()

        if logging_enabled:
            if self.widgets["loggingPathEntry"].text() == "":
                # No logging directory set, prompt user to select one.
                _success = self.select_log_directory()
                if not _success:
                    # User didn't select a directory, set checkbox to false again.
                    logging.error("No log directory selected, logging disabled.")
                    self.widgets["enableLoggingSelector"].setChecked(False)
                    # Disable logging.
                    if self.telemetry_logger:
                        self.telemetry_logger.enabled = False

                    return

            # Enable logging
            if self.telemetry_logger:
                self.telemetry_logger.enabled = True
                self.telemetry_logger.update_log_directory(self.widgets["loggingPathEntry"].text())

        else:
            # Disable logging
            if self.telemetry_logger:
                self.telemetry_logger.enabled = False


    def set_logging_format(self):
        if self.telemetry_logger:
            self.telemetry_logger.log_format = self.widgets["loggingFormatSelector"].currentText()


    # Handlers for various checkboxes and push-buttons
    def habitat_position_reupload(self, dummy_arg, upload=True):
        """ 
        Trigger a re-upload of user position information 
        Note that this requires a dummy argument, as the Qt 
        'connect' callback supplies an argument which we don't want.
        """
        self.sondehub_uploader.user_callsign = self.widgets["userCallEntry"].text()
        self.sondehub_uploader.user_radio = "Horus-GUI v" + __version__ + " " + self.widgets["userRadioEntry"].text()
        self.sondehub_uploader.user_antenna = self.widgets["userAntennaEntry"].text()
        try:
            if float(self.widgets["userLatEntry"].text()) == 0.0 and float(self.widgets["userLonEntry"].text()) == 0.0:
                self.sondehub_uploader.user_position = None
            else:
                self.sondehub_uploader.user_position = [
                    float(self.widgets["userLatEntry"].text()), 
                    float(self.widgets["userLonEntry"].text()), 
                    float(self.widgets["userAltEntry"].text())]
        except Exception as e:
            logging.error(f"Error parsing station location - {str(e)}")
            self.sondehub_uploader.user_position = None

        if upload:
            self.sondehub_uploader.last_user_position_upload = 0
            self.widgets["sondehubPositionNotesLabel"].setText("")
            logging.info("Triggered user position re-upload.")


    # Update uploader info as soon as it's edited, to ensure we upload with the latest user callsign
    def update_uploader_details(self):
        """
        Wrapper function for position re-upload, called when the user callsign entry is changed.
        """
        #habitat_position_reupload("unused arg",upload=False)
        self.widgets["sondehubPositionNotesLabel"].setText("<center><b>Station Info out of date - click Re-Upload!</b></center>")


    def habitat_inhibit(self):
        """ Update the Habitat inhibit flag """
        self.sondehub_uploader.inhibit = not self.widgets["sondehubUploadSelector"].isChecked()
        logging.debug(f"Updated Sondebub Inhibit state: {self.sondehub_uploader.inhibit}")


    def update_manual_estimator(self):
        """ Push a change to the manually defined estimator limits into the modem """
        _limits = self.widgets["estimatorRange"].getRegion()

        _lower = _limits[0]
        _upper = _limits[1]

        if self.horus_modem != None:
            self.horus_modem.set_estimator_limits(_lower, _upper)


    def set_manual_estimator(self):
        """ Show or hide the manual estimator limit region """
        if self.widgets["horusManualEstimatorSelector"].isChecked():
            self.widgets["spectrumPlot"].addItem(self.widgets["estimatorRange"])
            self.update_manual_estimator()
        else:
            try:
                self.widgets["spectrumPlot"].removeItem(self.widgets["estimatorRange"])
                # Reset modem estimator limits to their defaults.
                if self.horus_modem != None:
                    self.horus_modem.set_estimator_limits(self.DEFAULT_ESTIMATOR_MIN, self.DEFAULT_ESTIMATOR_MAX)
            except:
                pass


    def save_settings(self):
        """ Manually save current settings """
        save_config(self.widgets)


    # Handlers for data arriving via callbacks
    def handle_fft_update(self, data):
        """ Handle a new FFT update """

        _scale = data["scale"]
        _data = data["fft"]
        _dbfs = data["dbfs"]

        if self.widgets["fftSmoothingSelector"].isChecked():
            _tc = 0.25
            _plot_data = (self.widgets["spectrumPlotData"].getData()[1] * (1 - _tc) + (_data * _tc))
            self.widgets["spectrumPlotData"].setData(_scale, _plot_data)
        else:
            self.widgets["spectrumPlotData"].setData(_scale, _data)

        # Really basic IIR to smoothly adjust scale
        _old_max = self.widgets["spectrumPlotRange"][1]
        _tc = 0.1
        _new_max = float((_old_max * (1 - _tc)) + (np.max(_data) * _tc))

        # Store new max
        self.widgets["spectrumPlotRange"][1] = max(self.widgets["spectrumPlotRange"][0], _new_max)

        self.widgets["spectrumPlot"].setYRange(
            self.widgets["spectrumPlotRange"][0], self.widgets["spectrumPlotRange"][1] + 20
        )

        # Ignore NaN values.
        if np.isnan(_dbfs) or np.isinf(_dbfs):
            return


        # Use same IIR to smooth out dBFS readings a little.
        _new_dbfs = float((self.widgets["audioDbfsValue_float"] * (1 - _tc)) + (_dbfs * _tc))

        # Set dBFS value
        if (_new_dbfs>-5.0):
            _dbfs_ok = "TOO HIGH"
        elif (_new_dbfs < -90.0):
            _dbfs_ok = "NO AUDIO?"
        elif (_new_dbfs < -50.0):
            _dbfs_ok = "LOW"
        else:
            _dbfs_ok = "GOOD"

        self.widgets["audioDbfsValue"].setText(f"{_new_dbfs:.0f}\t{_dbfs_ok}")
        self.widgets["audioDbfsValue_float"] = _new_dbfs


    def handle_status_update(self, status):
        """ Handle a new status frame """

        # Update Frequency estimator markers
        _fest_average = 0.0
        _fest_count = 0
        for _i in range(len(status.extended_stats.f_est)):
            _fest_pos = float(status.extended_stats.f_est[_i])
            if _fest_pos != 0.0:
                _fest_average += _fest_pos
                _fest_count += 1
                self.widgets["estimatorLines"][_i].setPos(_fest_pos)

        _fest_average = _fest_average/_fest_count
        self.widgets["fest_float"] = _fest_average

        # Update SNR Plot
        _time = time.time()
        # Roll Time/SNR
        self.widgets["snrPlotTime"] = np.append(self.widgets["snrPlotTime"], _time)
        self.widgets["snrPlotSNR"] = np.append(self.widgets["snrPlotSNR"], float(status.snr))
        if len(self.widgets["snrPlotTime"]) > 200:
            self.widgets["snrPlotTime"] = self.widgets["snrPlotTime"][1:]
            self.widgets["snrPlotSNR"] = self.widgets["snrPlotSNR"][1:]

        # Plot new SNR data
        self.widgets["snrPlotData"].setData((self.widgets["snrPlotTime"]-_time),  self.widgets["snrPlotSNR"])
        _old_max = self.widgets["snrPlotRange"][1]
        _tc = 0.1
        _new_max = float((_old_max * (1 - _tc)) + (np.max(self.widgets["snrPlotSNR"]) * _tc))
        self.widgets["snrPlotRange"][1] = _new_max
        self.widgets["snrPlot"].setYRange(
            self.widgets["snrPlotRange"][0], _new_max+10 
        )

        # Update SNR bar and label
        self.widgets["snrLabel"].setText(f"{float(status.snr):2.1f}")
        self.widgets["snrBar"].setValue(int(status.snr))


    def get_latest_snr(self):
        _current_modem = self.widgets["horusModemSelector"].currentText()

        _snr_update_rate = 2 # Hz

        if "RTTY" in _current_modem:
            # RTTY needs a much longer lookback period to find the peak SNR
            # This is because of a very long buffer used in the RTTY demod
            _snr_lookback = _snr_update_rate * 15
        else:
            # For Horus Binary we can use a smaller lookback time
            _snr_lookback = _snr_update_rate * 4
        
        if len(self.widgets["snrPlotSNR"])>_snr_lookback:
            return np.max(self.widgets["snrPlotSNR"][-1*_snr_lookback:])
        else:
            return np.max(self.widgets["snrPlotSNR"])

    def handle_new_packet_emit(self, frame):
        self.new_packet_signal.info.emit(frame)

    def handle_new_packet(self, frame):
        """ Handle receipt of a newly decoded packet """

        if len(frame.data) > 0:
            if type(frame.data) == bytes:
                # Packets from the binary decoders are provided as raw bytes.
                # Conver them to a hexadecimal representation for display in the 'raw' area.
                _packet = frame.data.hex().upper()
            else:
                # RTTY packets are provided as a string, and can be displayed directly
                _packet = frame.data
            
            _decoded = None

            # Grab SNR.
            _snr = self.get_latest_snr()
            #logging.info(f"Packet SNR: {_snr:.2f}")

            # Grab other metadata out of the GUI
            _radio_dial = None

            if self.widgets["dialFreqEntry"].text() != "":
                try:
                    _radio_dial = float(self.widgets["dialFreqEntry"].text())*1e6
                    if self.widgets["fest_float"]:
                        # Add on the centre frequency estimation onto the dial frequency.
                        _radio_dial += self.widgets["fest_float"]

                except:
                    logging.warning("Could not parse radio dial frequency. This must be in MMM.KKK format e.g. 437.600")
                    _radio_dial = None
            

            _baud_rate = int(self.widgets["horusModemRateSelector"].currentText())
            _modulation_detail = HORUS_MODEM_LIST[self.widgets["horusModemSelector"].currentText()]['modulation_detail']

            if type(frame.data) == str:
                # RTTY packet handling.
                # Attempt to extract fields from it:
                try:
                    _decoded = parse_ukhas_string(frame.data)
                    _decoded['snr'] = _snr
                    _decoded['baud_rate'] = _baud_rate
                    if _modulation_detail:
                        _decoded['modulation_detail'] = _modulation_detail
                    if _radio_dial:
                        _decoded['f_centre'] = _radio_dial
                    # If we get here, the string is valid!
                    self.widgets["latestRawSentenceData"].setText(f"{_packet}  ({_snr:.1f} dB SNR)")
                    self.widgets["latestDecodedSentenceData"].setText(f"{_packet}")
                    self.last_packet_time = time.time()

                    # Upload the string to Sondehub Amateur
                    if self.widgets["userCallEntry"].text() == "N0CALL":
                        logging.warning("Uploader callsign is set as N0CALL. Please change this, otherwise telemetry data may be discarded!")
                    
                    self.sondehub_uploader.add(_decoded)

                except Exception as e:
                    if "CRC Failure" in str(e) and self.widgets["inhibitCRCSelector"].isChecked():
                        pass
                    else:
                        self.widgets["latestRawSentenceData"].setText(f"{_packet} ({_snr:.1f} dB SNR)")
                        self.widgets["latestDecodedSentenceData"].setText("DECODE FAILED")
                        logging.error(f"Decode Failed: {str(e)}")
            
            else:
                # Handle binary packets
                try:
                    _decoded = decode_packet(frame.data)
                    _decoded['snr'] = _snr
                    _decoded['baud_rate'] = _baud_rate
                    if _modulation_detail:
                        _decoded['modulation_detail'] = _modulation_detail
                    if _radio_dial:
                        _decoded['f_centre'] = _radio_dial

                    self.widgets["latestRawSentenceData"].setText(f"{_packet} ({_snr:.1f} dB SNR)")
                    self.widgets["latestDecodedSentenceData"].setText(_decoded['ukhas_str'])
                    self.last_packet_time = time.time()
                    # Upload the string to Sondehub Amateur
                    if self.widgets["userCallEntry"].text() == "N0CALL":
                        logging.warning("Uploader callsign is set as N0CALL. Please change this, otherwise telemetry data may be discarded!")

                    self.sondehub_uploader.add(_decoded)
                except Exception as e:
                    if "CRC Failure" in str(e) and self.widgets["inhibitCRCSelector"].isChecked():
                        pass
                    else:
                        self.widgets["latestRawSentenceData"].setText(f"{_packet} ({_snr:.1f} dB SNR)")
                        self.widgets["latestDecodedSentenceData"].setText("DECODE FAILED")
                        logging.error(f"Decode Failed: {str(e)}")
            
            # If we have extracted data, update the decoded data display
            if _decoded:
                self.widgets["latestPacketCallsignValue"].setText(_decoded['callsign'])
                self.widgets["latestPacketTimeValue"].setText(_decoded['time'])
                self.widgets["latestPacketLatitudeValue"].setText(f"{_decoded['latitude']:.5f}")
                self.widgets["latestPacketLongitudeValue"].setText(f"{_decoded['longitude']:.5f}")
                self.widgets["latestPacketAltitudeValue"].setText(f"{_decoded['altitude']}")

                # Update telemetry fields
                if 'battery_voltage' in _decoded:
                    self.widgets["latestTelemBattVoltageValue"].setText(f"{_decoded['battery_voltage']:.2f}")
                else:
                    self.widgets["latestTelemBattVoltageValue"].setText("---")

                if 'satellites' in _decoded:
                    self.widgets["latestTelemSatellitesValue"].setText(f"{_decoded['satellites']}")
                else:
                    self.widgets["latestTelemSatellitesValue"].setText("---")

                if 'temperature' in _decoded:
                    self.widgets["latestTelemTemperatureValue"].setText(f"{_decoded['temperature']:.1f}")
                else:
                    self.widgets["latestTelemTemperatureValue"].setText("---")

                # Handle custom data from Horus V2 packets
                if 'custom_field_names' in _decoded and len(_decoded['custom_field_names']) > 0:
                    column = 0
                    for field in _decoded['custom_field_names']:
                        field_nice = field.replace('_', ' ').title()
                        self.widgets[f"latestTelem{column}Label"].setText(f"<b>{field_nice}</b>")
                        self.widgets[f"latestTelem{column}Value"].setText(f"{_decoded[field]}")
                        self.widgets[f"latestTelem{column}Label"].show()
                        self.widgets[f"latestTelem{column}Value"].show()

                        self.w5_telemetry.setColumnStretch((column + 3), 10)

                        column += 1

                    # Hide remaining columns
                    if column < 8:
                        for i in range(column, 9):
                            self.widgets[f"latestTelem{i}Label"].hide()
                            self.widgets[f"latestTelem{i}Value"].hide()
                            self.w5_telemetry.setColumnStretch((i + 3), 1)
                
                # Else hide unused (Horus V1) columns
                else:
                    for i in range(0, 9):
                        self.widgets[f"latestTelem{i}Label"].hide()
                        self.widgets[f"latestTelem{i}Value"].hide()
                        self.w5_telemetry.setColumnStretch((i + 3), 1)

                # Attempt to update the range/elevation/bearing fields.
                try:
                    _station_lat = float(self.widgets["userLatEntry"].text())
                    _station_lon = float(self.widgets["userLonEntry"].text())
                    _station_alt = float(self.widgets["userAltEntry"].text())

                    if (_station_lat != 0.0) or (_station_lon != 0.0):
                        _position_info = position_info(
                            (_station_lat, _station_lon, _station_alt),
                            (_decoded['latitude'], _decoded['longitude'], _decoded['altitude'])
                        )

                        self.widgets['latestPacketBearingValue'].setText(f"{_position_info['bearing']:.1f}")
                        self.widgets['latestPacketElevationValue'].setText(f"{_position_info['elevation']:.1f}")
                        self.widgets['latestPacketRangeValue'].setText(f"{_position_info['straight_distance']/1000.0:.1f}")

                        _range_inhibit = False
                        if self.widgets["rotatorRangeInhibit"].isChecked() and (_position_info['straight_distance'] < 250):
                            logging.debug("Rotator - Not moving due to Range Inhibit (less than 250m)")
                            _range_inhibit = True

                        if self.rotator and not ( _decoded['latitude'] == 0.0 and _decoded['longitude'] == 0.0 ) and not _range_inhibit:
                            try:
                                self.rotator.set_azel(_position_info['bearing'], _position_info['elevation'], check_response=False)
                                self.widgets["rotatorCurrentPositionValue"].setText(f"{_position_info['bearing']:3.1f}˚,  {_position_info['elevation']:2.1f}˚")
                            except Exception as e:
                                logging.error("Rotator - Error setting Position: " + str(e))
                        
                except Exception as e:
                    logging.error(f"Could not calculate relative position to payload - {str(e)}")
                
                # Send data out via Horus UDP
                if self.widgets["horusUploadSelector"].isChecked():
                    _udp_port = int(self.widgets["horusUDPEntry"].text())
                    # Add in SNR data
                    try:
                        _snr = float(self.widgets["snrLabel"].text())
                    except ValueError as e:
                        logging.error(e)
                        _snr = 0
                    _decoded['snr'] = _snr

                    send_payload_summary(_decoded, port=_udp_port)
                
                # Send data out via OziMux messaging
                if self.widgets["ozimuxUploadSelector"].isChecked():
                    _udp_port = int(self.widgets["ozimuxUDPEntry"].text())
                    send_ozimux_message(_decoded, port=_udp_port)

                # Log telemetry
                if self.telemetry_logger:
                    self.telemetry_logger.add(_decoded)

        # Try and force a refresh of the displays.
        QApplication.processEvents()



    def start_decoding(self):
        """
        Read settings from the GUI
        Set up all elements of the decode chain
        Start decoding!
        (Or, stop decoding)
        """
        global args

        if not self.running:
            # Reset last packet time

            if self.widgets["userCallEntry"].text() == "N0CALL":
                # We don't allow the decoder to start if the callsign is still at the default.
                _error_msgbox = QMessageBox()
                _error_msgbox.setWindowTitle("Uploader Callsign Invalid")
                _error_msgbox.setText("Please change your SondeHub uploader callsign before starting!")
                _error_msgbox.exec()

                return
            
            self.last_packet_time = None
            self.widgets['latestDecodedAgeData'].setText("No packet yet!")
            # Grab settings off widgets
            _dev_name = self.widgets["audioDeviceSelector"].currentText()
            if _dev_name != 'UDP Audio (127.0.0.1:7355)':
                _sample_rate = int(self.widgets["audioSampleRateSelector"].currentText())
                _dev_index = self.audio_devices[_dev_name]["index"]
            else:
                # Override sample rate for GQRX UDP input.
                _sample_rate = 48000

            # Grab Horus Settings
            _modem_name = self.widgets["horusModemSelector"].currentText()
            _modem_id = HORUS_MODEM_LIST[_modem_name]['id']
            _modem_rate = int(self.widgets["horusModemRateSelector"].currentText())
            _modem_mask_enabled = self.widgets["horusMaskEstimatorSelector"].isChecked()
            if _modem_mask_enabled:
                _modem_tone_spacing = int(self.widgets["horusMaskSpacingEntry"].text())
            else:
                _modem_tone_spacing = -1

            # Reset Frequency Estimator indicators
            for _line in self.widgets["estimatorLines"]:
                _line.setPos(-1000)

            # Reset data fields
            self.widgets["latestRawSentenceData"].setText("NO DATA")
            self.widgets["latestDecodedSentenceData"].setText("NO DATA")
            self.widgets["latestPacketCallsignValue"].setText("---")
            self.widgets["latestPacketTimeValue"].setText("---")
            self.widgets["latestPacketLatitudeValue"].setText("---")
            self.widgets["latestPacketLongitudeValue"].setText("---")
            self.widgets["latestPacketAltitudeValue"].setText("---")
            self.widgets["latestPacketElevationValue"].setText("---")
            self.widgets["latestPacketBearingValue"].setText("---")
            self.widgets["latestPacketRangeValue"].setText("---")

            self.widgets["latestTelemBattVoltageValue"].setText("---")
            self.widgets["latestTelemSatellitesValue"].setText("---")
            self.widgets["latestTelemTemperatureValue"].setText("---")
            
            for column in range(0,9):
                self.widgets[f"latestTelem{column}Value"].setText(f"---")

            # Ensure the SondeHub upload is set correctly.
            self.sondehub_uploader.inhibit = not self.widgets["sondehubUploadSelector"].isChecked()

            # Init FFT Processor
            NFFT = 2 ** 13
            STRIDE = 2 ** 13
            self.fft_process = FFTProcess(
                nfft=NFFT, 
                stride=STRIDE,
                update_decimation=1,
                fs=_sample_rate, 
            )

            # Create FFT Processor worker thread
            worker = Worker(self.fft_process.processing_thread)
            # worker.signals.result.connect(self.null_thread_complete)
            # worker.signals.finished.connect(self.null_thread_complete)
            worker.signals.info.connect(self.handle_fft_update)

            self.threadpool.start(worker)

            # Setup Modem
            _libpath = ""
            if args.libfix:
                _libpath = "./"
                
            self.horus_modem = HorusLib(
                libpath=_libpath,
                mode=_modem_id,
                rate=_modem_rate,
                tone_spacing=_modem_tone_spacing,
                callback=self.handle_new_packet_emit,
                sample_rate=_sample_rate
            )

            # Set manual estimator limits, if enabled
            if self.widgets["horusManualEstimatorSelector"].isChecked():
                self.update_manual_estimator()
            else:
                self.horus_modem.set_estimator_limits(self.DEFAULT_ESTIMATOR_MIN, self.DEFAULT_ESTIMATOR_MAX)

            # Setup Audio (or UDP input)
            if _dev_name == 'UDP Audio (127.0.0.1:7355)':
                self.audio_stream = UDPStream(
                    udp_port=7355,
                    fs=_sample_rate,
                    block_size=self.fft_process.stride,
                    fft_input=self.fft_process.add_samples,
                    modem=self.horus_modem,
                )
                
                # Create UDP stream worker thread
                worker = Worker(self.audio_stream.udp_listen_thread)
                worker.signals.info.connect(self.handle_status_update)
                self.threadpool.start(worker)
            

            else:
                self.audio_stream = AudioStream(
                    _dev_index,
                    fs=_sample_rate,
                    block_size=self.fft_process.stride,
                    fft_input=self.fft_process.add_samples,
                    modem=self.horus_modem,
                )

                # Create AudioStream worker thred
                worker = Worker(self.audio_stream.start_stream)
                worker.signals.info.connect(self.handle_status_update)
                self.threadpool.start(worker)

            self.widgets["startDecodeButton"].setText("Stop")
            self.running = True
            logging.info("Started Audio Processing.")

            # Start thread to update the last packet age
            worker = Worker(self.decoded_age_thread)
            # worker.signals.result.connect(self.null_thread_complete)
            # worker.signals.finished.connect(self.null_thread_complete)
            worker.signals.info.connect(self.handle_decoded_age_update)

            self.threadpool.start(worker)

            # Grey out some selectors, so the user cannot adjust them while we are decoding.
            self.widgets["audioDeviceSelector"].setEnabled(False)
            self.widgets["audioSampleRateSelector"].setEnabled(False)
            self.widgets["horusModemSelector"].setEnabled(False)
            self.widgets["horusModemRateSelector"].setEnabled(False)
            self.widgets["horusMaskEstimatorSelector"].setEnabled(False) # This should really be editable while running.
            self.widgets["horusMaskSpacingEntry"].setEnabled(False) # This should really be editable while running

        else:
            try:
                self.audio_stream.stop()
            except Exception as e:
                logging.exception("Could not stop audio stream.", exc_info=e)

            try:
                self.fft_process.stop()
            except Exception as e:
                logging.exception("Could not stop fft processing.", exc_info=e)

            try:
                self.horus_modem.close()
            except Exception as e:
                logging.exception("Could not close horus modem.", exc_info=e)

            self.horus_modem = None

            self.widgets["startDecodeButton"].setText("Start")
            self.running = False

            logging.info("Stopped Audio Processing.")
            
            # Re-Activate selectors.
            self.widgets["audioDeviceSelector"].setEnabled(True)
            self.widgets["audioSampleRateSelector"].setEnabled(True)
            self.widgets["horusModemSelector"].setEnabled(True)
            self.widgets["horusModemRateSelector"].setEnabled(True)
            self.widgets["horusMaskEstimatorSelector"].setEnabled(True)
            self.widgets["horusMaskSpacingEntry"].setEnabled(True)

    def handle_log_update(self, log_update):
        self.widgets["console"].appendPlainText(log_update)
        # Make sure the scroll bar is right at the bottom.
        _sb = self.widgets["console"].verticalScrollBar()
        _sb.setValue(_sb.maximum())


    # Payload init
    def payload_init(self):
        global args 

        # Initialise decoders, and other libraries here.
        init_payloads(payload_id_list = args.payload_id_list, custom_field_list = args.custom_field_list)
        # Once initialised, enable the start button
        self.widgets["startDecodeButton"].setEnabled(True)

    # Thread to update last packet age
    def decoded_age_thread(self, info_callback):
        while self.running:
            if self.last_packet_time != None:
                _time_delta = int(time.time() - self.last_packet_time)
                _time_delta_seconds = int(_time_delta%60)
                _time_delta_minutes = int((_time_delta/60) % 60)
                _time_delta_hours = int((_time_delta/3600))
                info_callback.emit(f"{_time_delta_hours:02d}:{_time_delta_minutes:02d}:{_time_delta_seconds:02d}")

            time.sleep(0.5)

    def handle_decoded_age_update(self, text):
        self.widgets['latestDecodedAgeData'].setText(text)

    # Rotator Control
    def startstop_rotator(self):
        if self.rotator is None:
            # Start a rotator connection.

            try:
                _host = self.widgets["rotatorHostEntry"].text()
                _port = int(self.widgets["rotatorPortEntry"].text())
                _threshold = float(self.widgets["rotatorThresholdEntry"].text())
            except:
                self.widgets["rotatorCurrentStatusValue"].setText("Bad Host/Port")
                return

            if self.widgets["rotatorTypeSelector"].currentText() == "rotctld":
                try:
                    self.rotator = ROTCTLD(hostname=_host, port=_port, threshold=_threshold)
                    self.rotator.connect()
                except Exception as e:
                    logging.error("Rotctld Connect Error: " + str(e))
                    self.rotator = None
                    return
            elif self.widgets["rotatorTypeSelector"].currentText() == "PSTRotator":
                self.rotator = PSTRotator(hostname=_host, port=_port, threshold=_threshold)
                
                # Create worker thread for commanding rotator
                worker = Worker(self.rotator.azel_rx_loop)
                #worker.signals.info.connect(self.info_callback)
                self.threadpool.start(worker)

                # Create worker thread for receiving info from rotator
                worker = Worker(self.rotator.azel_poll_loop)
                #worker.signals.info.connect(self.info_callback)
                self.threadpool.start(worker)
            else:
                return


            self.widgets["rotatorCurrentStatusValue"].setText("Connected")
            self.widgets["rotatorConnectButton"].setText("Stop")
        else:
            # Stop the rotator
            self.rotator.close()
            self.rotator = None
            self.widgets["rotatorConnectButton"].setText("Start")
            self.widgets["rotatorCurrentStatusValue"].setText("Not Connected")
            self.widgets["rotatorCurrentPositionValue"].setText(f"---˚, --˚")



    # def poll_rotator():
    #     global rotator, widgets, rotator_current_az, rotator_current_el

    #     if rotator:
    #         _az, _el = rotator.get_azel()

    #         if _az != None:
    #             rotator_current_az = _az

    #         if _el != None:
    #             rotator_current_el = _el

    #         self.widgets["rotatorCurrentPositionValue"].setText(f"{rotator_current_az:3.1f}˚, {rotator_current_el:2.1f}˚")

    # rotator_poll_timer = QtCore.QTimer()
    # rotator_poll_timer.timeout.connect(poll_rotator)
    # rotator_poll_timer.start(2000)

    # Dummy function to call from worker threads
    def null_thread_complete(self):
        logging.debug("Thread exit!!!")
        return

class ConsoleHandler(logging.Handler):
    """ Logging handler to write to the GUI console """

    def __init__(self, callback):
        logging.Handler.__init__(self)
        self.signaller = WorkerSignals()
        self.signaller.info.connect(callback)

    def emit(self, record):
        _time = datetime.datetime.now()
        _text = f"{_time.strftime('%H:%M:%S')} [{record.levelname}]  {record.msg}"
        
        # TODO -- create gentle dismount when exiting
        try:
            self.signaller.info.emit(_text)
        except:
            pass

# Main
def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    app.aboutToQuit.connect(window.cleanup)
    window.show()
    sys.exit(app.exec())

    # Start the Qt Loop
    if (sys.flags.interactive != 1) or not hasattr(QtCore, "PYQT_VERSION"):
        QApplication.instance().exec()
        save_config(widgets)

if __name__ == "__main__":
    main()