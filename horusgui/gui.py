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

import datetime
import glob
import logging
import pyqtgraph as pg
import numpy as np
from queue import Queue
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from pyqtgraph.dockarea import *
from threading import Thread

from .widgets import *
from .audio import *
from .udpaudio import *
from .fft import *
from .modem import *
from .config import *
from .habitat import *
from .utils import position_info
from .icon import getHorusIcon
from horusdemodlib.demod import HorusLib, Mode
from horusdemodlib.decoder import decode_packet, parse_ukhas_string
from horusdemodlib.payloads import *
from horusdemodlib.horusudp import send_payload_summary
from . import __version__

# Setup Logging
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)

# A few hardcoded defaults
DEFAULT_ESTIMATOR_MIN = 100
DEFAULT_ESTIMATOR_MAX = 4000


# Global widget store
widgets = {}

# Queues for handling updates to image / status indications.
fft_update_queue = Queue(256)
status_update_queue = Queue(256)
log_update_queue = Queue(256)

# List of audio devices and their info
audio_devices = {}

# Processor objects
audio_stream = None
fft_process = None
horus_modem = None
habitat_uploader = None

decoder_init = False

# Global running indicator
running = False

#
#   GUI Creation - The Bad way.
#

# Create a Qt App.
pg.mkQApp()

# GUI LAYOUT - Gtk Style!
win = QtGui.QMainWindow()
area = DockArea()
win.setCentralWidget(area)
win.setWindowTitle(f"Horus Telemetry GUI - v{__version__}")
win.setWindowIcon(getHorusIcon())

# Create multiple dock areas, for displaying our data.
d0 = Dock("Audio", size=(300, 50))
d0_modem = Dock("Modem", size=(300, 80))
d0_habitat = Dock("Habitat", size=(300, 200))
d0_other = Dock("Other", size=(300, 100))
d1 = Dock("Spectrum", size=(800, 350))
d2_stats = Dock("SNR (dB)", size=(50, 300))
d2_snr = Dock("SNR Plot", size=(750, 300))
d3_data = Dock("Data", size=(800, 50))
d3_position = Dock("Position", size=(800, 50))
d4 = Dock("Log", size=(800, 150))
# Arrange docks.
area.addDock(d0)
area.addDock(d1, "right", d0)
area.addDock(d0_modem, "bottom", d0)
area.addDock(d0_habitat, "bottom", d0_modem)
area.addDock(d0_other, "below", d0_habitat)
area.addDock(d2_stats, "bottom", d1)
area.addDock(d3_data, "bottom", d2_stats)
area.addDock(d3_position, "bottom", d3_data)
area.addDock(d4, "bottom", d3_position)
area.addDock(d2_snr, "right", d2_stats)
d0_habitat.raiseDock()


# Controls
w1_audio = pg.LayoutWidget()
# TNC Connection
widgets["audioDeviceLabel"] = QtGui.QLabel("<b>Audio Device:</b>")
widgets["audioDeviceSelector"] = QtGui.QComboBox()

widgets["audioSampleRateLabel"] = QtGui.QLabel("<b>Sample Rate (Hz):</b>")
widgets["audioSampleRateSelector"] = QtGui.QComboBox()

w1_audio.addWidget(widgets["audioDeviceLabel"], 0, 0, 1, 1)
w1_audio.addWidget(widgets["audioDeviceSelector"], 0, 1, 1, 2)
w1_audio.addWidget(widgets["audioSampleRateLabel"], 1, 0, 1, 1)
w1_audio.addWidget(widgets["audioSampleRateSelector"], 1, 1, 1, 2)

d0.addWidget(w1_audio)

w1_modem = pg.LayoutWidget()

# Modem Parameters
widgets["horusModemLabel"] = QtGui.QLabel("<b>Mode:</b>")
widgets["horusModemSelector"] = QtGui.QComboBox()

widgets["horusModemRateLabel"] = QtGui.QLabel("<b>Baudrate:</b>")
widgets["horusModemRateSelector"] = QtGui.QComboBox()

widgets["horusMaskEstimatorLabel"] = QtGui.QLabel("<b>Enable Mask Estim.:</b>")
widgets["horusMaskEstimatorSelector"] = QtGui.QCheckBox()

widgets["horusMaskSpacingLabel"] = QtGui.QLabel("<b>Tone Spacing (Hz):</b>")
widgets["horusMaskSpacingEntry"] = QtGui.QLineEdit("270")
widgets["horusManualEstimatorLabel"] = QtGui.QLabel("<b>Manual Estim. Limits:</b>")
widgets["horusManualEstimatorSelector"] = QtGui.QCheckBox()

# Start/Stop
widgets["startDecodeButton"] = QtGui.QPushButton("Start")
widgets["startDecodeButton"].setEnabled(False)

w1_modem.addWidget(widgets["horusModemLabel"], 0, 0, 1, 1)
w1_modem.addWidget(widgets["horusModemSelector"], 0, 1, 1, 1)
w1_modem.addWidget(widgets["horusModemRateLabel"], 1, 0, 1, 1)
w1_modem.addWidget(widgets["horusModemRateSelector"], 1, 1, 1, 1)
w1_modem.addWidget(widgets["horusMaskEstimatorLabel"], 2, 0, 1, 1)
w1_modem.addWidget(widgets["horusMaskEstimatorSelector"], 2, 1, 1, 1)
w1_modem.addWidget(widgets["horusMaskSpacingLabel"], 3, 0, 1, 1)
w1_modem.addWidget(widgets["horusMaskSpacingEntry"], 3, 1, 1, 1)
w1_modem.addWidget(widgets["horusManualEstimatorLabel"], 4, 0, 1, 1)
w1_modem.addWidget(widgets["horusManualEstimatorSelector"], 4, 1, 1, 1)
w1_modem.addWidget(widgets["startDecodeButton"], 5, 0, 2, 2)

d0_modem.addWidget(w1_modem)


w1_habitat = pg.LayoutWidget()
# Listener Information
widgets["habitatHeading"] = QtGui.QLabel("<b>Habitat Settings</b>")
widgets["habitatUploadLabel"] = QtGui.QLabel("<b>Enable Habitat Upload:</b>")
widgets["habitatUploadSelector"] = QtGui.QCheckBox()
widgets["habitatUploadSelector"].setChecked(True)
widgets["userCallLabel"] = QtGui.QLabel("<b>Callsign:</b>")
widgets["userCallEntry"] = QtGui.QLineEdit("N0CALL")
widgets["userCallEntry"].setMaxLength(20)
widgets["userLocationLabel"] = QtGui.QLabel("<b>Lat/Lon:</b>")
widgets["userLatEntry"] = QtGui.QLineEdit("0.0")
widgets["userLonEntry"] = QtGui.QLineEdit("0.0")
widgets["userAntennaLabel"] = QtGui.QLabel("<b>Antenna:</b>")
widgets["userAntennaEntry"] = QtGui.QLineEdit("")
widgets["userRadioLabel"] = QtGui.QLabel("<b>Radio:</b>")
widgets["userRadioEntry"] = QtGui.QLineEdit("Horus-GUI " + __version__)
widgets["habitatUploadPosition"] = QtGui.QPushButton("Upload Position")
widgets["saveSettingsButton"] = QtGui.QPushButton("Save Settings")

w1_habitat.addWidget(widgets["habitatUploadLabel"], 0, 0, 1, 1)
w1_habitat.addWidget(widgets["habitatUploadSelector"], 0, 1, 1, 1)
w1_habitat.addWidget(widgets["userCallLabel"], 1, 0, 1, 1)
w1_habitat.addWidget(widgets["userCallEntry"], 1, 1, 1, 2)
w1_habitat.addWidget(widgets["userLocationLabel"], 2, 0, 1, 1)
w1_habitat.addWidget(widgets["userLatEntry"], 2, 1, 1, 1)
w1_habitat.addWidget(widgets["userLonEntry"], 2, 2, 1, 1)
w1_habitat.addWidget(widgets["userAntennaLabel"], 3, 0, 1, 1)
w1_habitat.addWidget(widgets["userAntennaEntry"], 3, 1, 1, 2)
w1_habitat.addWidget(widgets["userRadioLabel"], 4, 0, 1, 1)
w1_habitat.addWidget(widgets["userRadioEntry"], 4, 1, 1, 2)
w1_habitat.addWidget(widgets["habitatUploadPosition"], 5, 0, 1, 3)
w1_habitat.layout.setRowStretch(6, 1)
w1_habitat.addWidget(widgets["saveSettingsButton"], 7, 0, 1, 3)

d0_habitat.addWidget(w1_habitat)

w1_other = pg.LayoutWidget()
widgets["horusUploadLabel"] = QtGui.QLabel("<b>Enable Horus UDP Output:</b>")
widgets["horusUploadSelector"] = QtGui.QCheckBox()
widgets["horusUploadSelector"].setChecked(True)
widgets["horusUDPLabel"] = QtGui.QLabel("<b>Horus UDP Port:</b>")
widgets["horusUDPEntry"] = QtGui.QLineEdit("55672")
widgets["horusUDPEntry"].setMaxLength(5)

w1_other.addWidget(widgets["horusUploadLabel"], 0, 0, 1, 1)
w1_other.addWidget(widgets["horusUploadSelector"], 0, 1, 1, 1)
w1_other.addWidget(widgets["horusUDPLabel"], 1, 0, 1, 1)
w1_other.addWidget(widgets["horusUDPEntry"], 1, 1, 1, 1)
w1_other.layout.setRowStretch(5, 1)

d0_other.addWidget(w1_other)

# Spectrum Display
widgets["spectrumPlot"] = pg.PlotWidget(title="Spectra")
widgets["spectrumPlot"].setLabel("left", "Power (dB)")
widgets["spectrumPlot"].setLabel("bottom", "Frequency (Hz)")
widgets["spectrumPlotData"] = widgets["spectrumPlot"].plot([0])

# Frequency Estiator Outputs
widgets["estimatorLines"] = [
    pg.InfiniteLine(
        pos=-1000,
        pen=pg.mkPen(color="w", width=2, style=QtCore.Qt.DashLine),
        label="F1",
        labelOpts={'position':0.9}
    ),
    pg.InfiniteLine(
        pos=-1000,
        pen=pg.mkPen(color="w", width=2, style=QtCore.Qt.DashLine),
        label="F2",
        labelOpts={'position':0.9}
    ),
    pg.InfiniteLine(
        pos=-1000,
        pen=pg.mkPen(color="w", width=2, style=QtCore.Qt.DashLine),
        label="F3",
        labelOpts={'position':0.9}
    ),
    pg.InfiniteLine(
        pos=-1000,
        pen=pg.mkPen(color="w", width=2, style=QtCore.Qt.DashLine),
        label="F4",
        labelOpts={'position':0.9}
    ),
]
for _line in widgets["estimatorLines"]:
    widgets["spectrumPlot"].addItem(_line)

widgets["spectrumPlot"].setLabel("left", "Power (dBFs)")
widgets["spectrumPlot"].setLabel("bottom", "Frequency", units="Hz")
widgets["spectrumPlot"].setXRange(100, 4000)
widgets["spectrumPlot"].setYRange(-100, -20)
widgets["spectrumPlot"].setLimits(xMin=100, xMax=4000, yMin=-120, yMax=0)
widgets["spectrumPlot"].showGrid(True, True)

widgets["estimatorRange"] = pg.LinearRegionItem([100,3000])
widgets["estimatorRange"].setBounds([100,4000])

d1.addWidget(widgets["spectrumPlot"])

widgets["spectrumPlotRange"] = [-100, -20]


w3_stats = pg.LayoutWidget()
widgets["snrBar"] = QtWidgets.QProgressBar()
widgets["snrBar"].setOrientation(QtCore.Qt.Vertical)
widgets["snrBar"].setRange(-10, 15)
widgets["snrBar"].setValue(-10)
widgets["snrBar"].setTextVisible(False)
widgets["snrBar"].setAlignment(QtCore.Qt.AlignCenter)
widgets["snrLabel"] = QtGui.QLabel("--.-")
widgets["snrLabel"].setAlignment(QtCore.Qt.AlignCenter);
widgets["snrLabel"].setFont(QtGui.QFont("Courier New", 14))
w3_stats.addWidget(widgets["snrBar"], 0, 1, 1, 1)
w3_stats.addWidget(widgets["snrLabel"], 1, 0, 1, 3)
w3_stats.layout.setColumnStretch(0, 2)
w3_stats.layout.setColumnStretch(2, 2)

d2_stats.addWidget(w3_stats)

# SNR Plot
w3_snr = pg.LayoutWidget()
widgets["snrPlot"] = pg.PlotWidget(title="SNR")
widgets["snrPlot"].setLabel("left", "SNR (dB)")
widgets["snrPlot"].setLabel("bottom", "Time (s)")
widgets["snrPlot"].setXRange(-60, 0)
widgets["snrPlot"].setYRange(-10, 30)
widgets["snrPlot"].setLimits(xMin=-60, xMax=0, yMin=-10, yMax=40)
widgets["snrPlot"].showGrid(True, True)
widgets["snrPlotRange"] = [-10, 30]
widgets["snrPlotTime"] = np.array([])
widgets["snrPlotSNR"] = np.array([])
widgets["snrPlotData"] = widgets["snrPlot"].plot(widgets["snrPlotTime"], widgets["snrPlotSNR"])

# TODO: Look into eye diagram more
# widgets["eyeDiagramPlot"] = pg.PlotWidget(title="Eye Diagram")
# widgets["eyeDiagramData"] = widgets["eyeDiagramPlot"].plot([0])

w3_snr.addWidget(widgets["snrPlot"], 0, 1, 2, 1)

#w3.addWidget(widgets["eyeDiagramPlot"], 0, 1)

d2_snr.addWidget(w3_snr)

# Telemetry Data
w4_data = pg.LayoutWidget()
widgets["latestRawSentenceLabel"] = QtGui.QLabel("<b>Latest Packet (Raw):</b>")
widgets["latestRawSentenceData"] = QtGui.QLineEdit("NO DATA")
widgets["latestRawSentenceData"].setReadOnly(True)
#widgets["latestRawSentenceData"].setFont(QtGui.QFont("Courier New", 18, QtGui.QFont.Bold))
#widgets["latestRawSentenceData"].setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
widgets["latestDecodedSentenceLabel"] = QtGui.QLabel("<b>Latest Packet (Decoded):</b>")
widgets["latestDecodedSentenceData"] = QtGui.QLineEdit("NO DATA")
widgets["latestDecodedSentenceData"].setReadOnly(True)
#widgets["latestDecodedSentenceData"].setFont(QtGui.QFont("Courier New", 18, QtGui.QFont.Bold))
#widgets["latestDecodedSentenceData"].setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
w4_data.addWidget(widgets["latestRawSentenceLabel"], 0, 0, 1, 1)
w4_data.addWidget(widgets["latestRawSentenceData"], 0, 1, 1, 6)
w4_data.addWidget(widgets["latestDecodedSentenceLabel"], 1, 0, 1, 1)
w4_data.addWidget(widgets["latestDecodedSentenceData"], 1, 1, 1, 6)
d3_data.addWidget(w4_data)

w4_position = pg.LayoutWidget()
POSITION_LABEL_FONT_SIZE = 16
widgets["latestPacketCallsignLabel"] = QtGui.QLabel("<b>Callsign</b>")
widgets["latestPacketCallsignValue"] = QtGui.QLabel("---")
widgets["latestPacketCallsignValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketTimeLabel"] = QtGui.QLabel("<b>Time</b>")
widgets["latestPacketTimeValue"] = QtGui.QLabel("---")
widgets["latestPacketTimeValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketLatitudeLabel"] = QtGui.QLabel("<b>Latitude</b>")
widgets["latestPacketLatitudeValue"] = QtGui.QLabel("---")
widgets["latestPacketLatitudeValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketLongitudeLabel"] = QtGui.QLabel("<b>Longitude</b>")
widgets["latestPacketLongitudeValue"] = QtGui.QLabel("---")
widgets["latestPacketLongitudeValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketAltitudeLabel"] = QtGui.QLabel("<b>Altitude</b>")
widgets["latestPacketAltitudeValue"] = QtGui.QLabel("---")
widgets["latestPacketAltitudeValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketBearingLabel"] = QtGui.QLabel("<b>Bearing</b>")
widgets["latestPacketBearingValue"] = QtGui.QLabel("---")
widgets["latestPacketBearingValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketElevationLabel"] = QtGui.QLabel("<b>Elevation</b>")
widgets["latestPacketElevationValue"] = QtGui.QLabel("---")
widgets["latestPacketElevationValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))
widgets["latestPacketRangeLabel"] = QtGui.QLabel("<b>Range (km)</b>")
widgets["latestPacketRangeValue"] = QtGui.QLabel("---")
widgets["latestPacketRangeValue"].setFont(QtGui.QFont("Courier New", POSITION_LABEL_FONT_SIZE, QtGui.QFont.Bold))

w4_position.addWidget(widgets["latestPacketCallsignLabel"], 0, 0, 1, 2)
w4_position.addWidget(widgets["latestPacketCallsignValue"], 1, 0, 1, 2)
w4_position.addWidget(widgets["latestPacketTimeLabel"], 0, 2, 1, 1)
w4_position.addWidget(widgets["latestPacketTimeValue"], 1, 2, 1, 1)
w4_position.addWidget(widgets["latestPacketLatitudeLabel"], 0, 3, 1, 1)
w4_position.addWidget(widgets["latestPacketLatitudeValue"], 1, 3, 1, 1)
w4_position.addWidget(widgets["latestPacketLongitudeLabel"], 0, 4, 1, 1)
w4_position.addWidget(widgets["latestPacketLongitudeValue"], 1, 4, 1, 1)
w4_position.addWidget(widgets["latestPacketAltitudeLabel"], 0, 5, 1, 1)
w4_position.addWidget(widgets["latestPacketAltitudeValue"], 1, 5, 1, 1)
w4_position.addWidget(widgets["latestPacketBearingLabel"], 0, 7, 1, 1)
w4_position.addWidget(widgets["latestPacketBearingValue"], 1, 7, 1, 1)
w4_position.addWidget(widgets["latestPacketElevationLabel"], 0, 8, 1, 1)
w4_position.addWidget(widgets["latestPacketElevationValue"], 1, 8, 1, 1)
w4_position.addWidget(widgets["latestPacketRangeLabel"], 0, 9, 1, 1)
w4_position.addWidget(widgets["latestPacketRangeValue"], 1, 9, 1, 1)
w4_position.layout.setRowStretch(1, 6)
d3_position.addWidget(w4_position)

w5 = pg.LayoutWidget()
widgets["console"] = QtWidgets.QPlainTextEdit()
widgets["console"].setReadOnly(True)
w5.addWidget(widgets["console"])
d4.addWidget(w5)

# Resize window to final resolution, and display.
logging.info("Starting GUI.")
win.resize(1500, 800)
win.show()

# Audio Initialization
audio_devices = init_audio(widgets)


def update_audio_sample_rates():
    """ Update the sample-rate dropdown when a different audio device is selected.  """
    global widgets
    # Pass widgets straight on to function from .audio
    populate_sample_rates(widgets)


widgets["audioDeviceSelector"].currentIndexChanged.connect(update_audio_sample_rates)

# Initialize modem list.
init_horus_modem(widgets)


def update_modem_settings():
    """ Update the modem setting widgets when a different modem is selected """
    global widgets
    populate_modem_settings(widgets)


widgets["horusModemSelector"].currentIndexChanged.connect(update_modem_settings)


# Read in configuration file settings
read_config(widgets)

# Start Habitat Uploader
habitat_uploader = HabitatUploader(
    user_callsign=widgets["userCallEntry"].text(),
    listener_lat=widgets["userLatEntry"].text(),
    listener_lon=widgets["userLonEntry"].text(),
    listener_radio="Horus-GUI v" + __version__ + " " + widgets["userRadioEntry"].text(),
    listener_antenna=widgets["userAntennaEntry"].text(),
)


# Handlers for various checkboxes and push-buttons

def habitat_position_reupload():
    """ Trigger a re-upload of user position information """
    global widgets, habitat_uploader

    habitat_uploader.user_callsign = widgets["userCallEntry"].text()
    habitat_uploader.listener_lat = widgets["userLatEntry"].text()
    habitat_uploader.listener_lon = widgets["userLonEntry"].text()
    habitat_uploader.listener_radio = "Horus-GUI v" + __version__ + " " + widgets["userRadioEntry"].text()
    habitat_uploader.listener_antenna = widgets["userAntennaEntry"].text()
    habitat_uploader.trigger_position_upload()

widgets["habitatUploadPosition"].clicked.connect(habitat_position_reupload)


def habitat_inhibit():
    """ Update the Habitat inhibit flag """
    global widgets, habitat_uploader
    habitat_uploader.inhibit = not widgets["habitatUploadSelector"].isChecked()
    logging.debug(f"Updated Habitat Inhibit state: {habitat_uploader.inhibit}")

widgets["habitatUploadSelector"].clicked.connect(habitat_inhibit)


def update_manual_estimator():
    """ Push a change to the manually defined estimator limits into the modem """
    global widgets, horus_modem

    _limits = widgets["estimatorRange"].getRegion()

    _lower = _limits[0]
    _upper = _limits[1]

    if horus_modem != None:
        horus_modem.set_estimator_limits(_lower, _upper)

widgets["estimatorRange"].sigRegionChangeFinished.connect(update_manual_estimator)


def set_manual_estimator():
    """ Show or hide the manual estimator limit region """
    global widgets
    if widgets["horusManualEstimatorSelector"].isChecked():
        widgets["spectrumPlot"].addItem(widgets["estimatorRange"])
        update_manual_estimator()
    else:
        try:
            widgets["spectrumPlot"].removeItem(widgets["estimatorRange"])
            # Reset modem estimator limits to their defaults.
            if horus_modem != None:
                horus_modem.set_estimator_limits(DEFAULT_ESTIMATOR_MIN, DEFAULT_ESTIMATOR_MAX)
        except:
            pass

widgets["horusManualEstimatorSelector"].clicked.connect(set_manual_estimator)


def save_settings():
    """ Manually save current settings """
    global widgets
    save_config(widgets)

widgets["saveSettingsButton"].clicked.connect(save_settings)


# Handlers for data arriving via queues.

def handle_fft_update(data):
    """ Handle a new FFT update """
    global widgets

    _scale = data["scale"]
    _data = data["fft"]

    widgets["spectrumPlotData"].setData(_scale, _data)

    # Really basic IIR to smoothly adjust scale
    _old_max = widgets["spectrumPlotRange"][1]
    _tc = 0.1
    _new_max = float((_old_max * (1 - _tc)) + (np.max(_data) * _tc))

    # Store new max
    widgets["spectrumPlotRange"][1] = max(widgets["spectrumPlotRange"][0], _new_max)

    widgets["spectrumPlot"].setYRange(
        widgets["spectrumPlotRange"][0], widgets["spectrumPlotRange"][1] + 20
    )

def handle_status_update(status):
    """ Handle a new status frame """
    global widgets, habitat

    # Update Frequency estimator markers
    for _i in range(len(status.extended_stats.f_est)):
        _fest_pos = float(status.extended_stats.f_est[_i])
        if _fest_pos != 0.0:
            widgets["estimatorLines"][_i].setPos(_fest_pos)

    # Update SNR Plot
    _time = time.time()
    # Roll Time/SNR
    widgets["snrPlotTime"] = np.append(widgets["snrPlotTime"], _time)
    widgets["snrPlotSNR"] = np.append(widgets["snrPlotSNR"], float(status.snr))
    if len(widgets["snrPlotTime"]) > 200:
        widgets["snrPlotTime"] = widgets["snrPlotTime"][1:]
        widgets["snrPlotSNR"] = widgets["snrPlotSNR"][1:]

    # Plot new SNR data
    widgets["snrPlotData"].setData((widgets["snrPlotTime"]-_time),  widgets["snrPlotSNR"])
    _old_max = widgets["snrPlotRange"][1]
    _tc = 0.1
    _new_max = float((_old_max * (1 - _tc)) + (np.max(widgets["snrPlotSNR"]) * _tc))
    widgets["snrPlotRange"][1] = _new_max
    widgets["snrPlot"].setYRange(
        widgets["snrPlotRange"][0], _new_max+10 
    )

    # Update SNR bar and label
    widgets["snrLabel"].setText(f"{float(status.snr):2.1f}")
    widgets["snrBar"].setValue(int(status.snr))





def add_fft_update(data):
    """ Try and insert a new set of FFT data into the update queue """
    global fft_update_queue
    try:
        fft_update_queue.put_nowait(data)
    except:
        logging.error("FFT Update Queue Full!")


def add_stats_update(frame):
    """ Try and insert modem statistics into the processing queue """
    global status_update_queue
    try:
        status_update_queue.put_nowait(frame)
    except:
        logging.error("Status Update Queue Full!")
    



def handle_new_packet(frame):
    """ Handle receipt of a newly decoded packet """

    if len(frame.data) > 0:
        if type(frame.data) == bytes:
            # Packets from the binary decoders are provided as raw bytes.
            # Conver them to a hexadecimal representation for display in the 'raw' area.
            _packet = frame.data.hex().upper()
        else:
            # RTTY packets are provided as a string, and can be displayed directly
            _packet = frame.data
        
        # Update the raw display.
        widgets["latestRawSentenceData"].setText(f"{_packet}")


        _decoded = None

        if type(frame.data) == str:
            # RTTY packet handling.
            # Attempt to extract fields from it:
            try:
                _decoded = parse_ukhas_string(frame.data)
                # If we get here, the string is valid!
                widgets["latestDecodedSentenceData"].setText(f"{_packet}")

                # Upload the string to Habitat
                _decoded_str = "$$" + frame.data.split('$')[-1] + '\n'
                habitat_uploader.add(_decoded_str)

            except Exception as e:
                widgets["latestDecodedSentenceData"].setText("DECODE FAILED")
                logging.error(f"Decode Failed: {str(e)}")
        
        else:
            # Handle binary packets
            try:
                _decoded = decode_packet(frame.data)
                widgets["latestDecodedSentenceData"].setText(_decoded['ukhas_str'])
                habitat_uploader.add(_decoded['ukhas_str']+'\n')
            except Exception as e:
                widgets["latestDecodedSentenceData"].setText("DECODE FAILED")
                logging.error(f"Decode Failed: {str(e)}")
        
        # If we have extracted data, update the decoded data display
        if _decoded:
            widgets["latestPacketCallsignValue"].setText(_decoded['callsign'])
            widgets["latestPacketTimeValue"].setText(_decoded['time'])
            widgets["latestPacketLatitudeValue"].setText(f"{_decoded['latitude']:.5f}")
            widgets["latestPacketLongitudeValue"].setText(f"{_decoded['longitude']:.5f}")
            widgets["latestPacketAltitudeValue"].setText(f"{_decoded['altitude']}")

            # Attempt to update the range/elevation/bearing fields.
            try:
                _station_lat = float(widgets["userLatEntry"].text())
                _station_lon = float(widgets["userLonEntry"].text())
                _station_alt = 0.0

                if (_station_lat != 0.0) or (_station_lon != 0.0):
                    _position_info = position_info(
                        (_station_lat, _station_lon, _station_alt),
                        (_decoded['latitude'], _decoded['longitude'], _decoded['altitude'])
                    )

                    widgets['latestPacketBearingValue'].setText(f"{_position_info['bearing']:.1f}")
                    widgets['latestPacketElevationValue'].setText(f"{_position_info['elevation']:.1f}")
                    widgets['latestPacketRangeValue'].setText(f"{_position_info['straight_distance']/1000.0:.1f}")
            except Exception as e:
                logging.error(f"Could not calculate relative position to payload - {str(e)}")
            
            # Send data out via Horus UDP
            if widgets["horusUploadSelector"].isChecked():
                _udp_port = int(widgets["horusUDPEntry"].text())
                # Add in SNR data
                _snr = float(widgets["snrLabel"].text())
                _decoded['snr'] = _snr

                send_payload_summary(_decoded, port=_udp_port)




def start_decoding():
    """
    Read settings from the GUI
    Set up all elements of the decode chain
    Start decoding!
    (Or, stop decoding)
    """
    global widgets, audio_stream, fft_process, horus_modem, habitat_uploader, audio_devices, running, fft_update_queue, status_update_queue

    if not running:
        # Grab settings off widgets
        _dev_name = widgets["audioDeviceSelector"].currentText()
        if _dev_name != 'GQRX UDP':
            _sample_rate = int(widgets["audioSampleRateSelector"].currentText())
            _dev_index = audio_devices[_dev_name]["index"]
        else:
            # Override sample rate for GQRX UDP input.
            _sample_rate = 48000

        # Grab Horus Settings
        _modem_name = widgets["horusModemSelector"].currentText()
        _modem_id = HORUS_MODEM_LIST[_modem_name]['id']
        _modem_rate = int(widgets["horusModemRateSelector"].currentText())
        _modem_mask_enabled = widgets["horusMaskEstimatorSelector"].isChecked()
        if _modem_mask_enabled:
            _modem_tone_spacing = int(widgets["horusMaskSpacingEntry"].text())
        else:
            _modem_tone_spacing = -1

        # Reset Frequency Estimator indicators
        for _line in widgets["estimatorLines"]:
            _line.setPos(-1000)

        # Reset data fields
        widgets["latestRawSentenceData"].setText("NO DATA")
        widgets["latestDecodedSentenceData"].setText("NO DATA")
        widgets["latestPacketCallsignValue"].setText("---")
        widgets["latestPacketTimeValue"].setText("---")
        widgets["latestPacketLatitudeValue"].setText("---")
        widgets["latestPacketLongitudeValue"].setText("---")
        widgets["latestPacketAltitudeValue"].setText("---")
        widgets["latestPacketElevationValue"].setText("---")
        widgets["latestPacketBearingValue"].setText("---")
        widgets["latestPacketRangeValue"].setText("---")

        # Ensure the Habitat upload is set correctly.
        habitat_uploader.inhibit = not widgets["habitatUploadSelector"].isChecked()

        # Init FFT Processor
        NFFT = 2 ** 13
        STRIDE = 2 ** 13
        fft_process = FFTProcess(
            nfft=NFFT, 
            stride=STRIDE,
            update_decimation=1,
            fs=_sample_rate, 
            callback=add_fft_update
        )

        # Setup Modem
        horus_modem = HorusLib(
            mode=_modem_id,
            rate=_modem_rate,
            tone_spacing=_modem_tone_spacing,
            callback=handle_new_packet,
            sample_rate=_sample_rate
        )

        # Set manual estimator limits, if enabled
        if widgets["horusManualEstimatorSelector"].isChecked():
            update_manual_estimator()
        else:
            horus_modem.set_estimator_limits(DEFAULT_ESTIMATOR_MIN, DEFAULT_ESTIMATOR_MAX)

        # Setup Audio (or UDP input)
        if _dev_name == 'GQRX UDP':
            audio_stream = UDPStream(
                udp_port=7355,
                fs=_sample_rate,
                block_size=fft_process.stride,
                fft_input=fft_process.add_samples,
                modem=horus_modem,
                stats_callback=add_stats_update
            )
        else:
            audio_stream = AudioStream(
                _dev_index,
                fs=_sample_rate,
                block_size=fft_process.stride,
                fft_input=fft_process.add_samples,
                modem=horus_modem,
                stats_callback=add_stats_update
            )

        widgets["startDecodeButton"].setText("Stop")
        running = True
        logging.info("Started Audio Processing.")

    else:
        try:
            audio_stream.stop()
        except Exception as e:
            logging.exception("Could not stop audio stream.", exc_info=e)

        try:
            fft_process.stop()
        except Exception as e:
            logging.exception("Could not stop fft processing.", exc_info=e)

        try:
            horus_modem.close()
        except Exception as e:
            logging.exception("Could not close horus modem.", exc_info=e)

        horus_modem = None

        fft_update_queue = Queue(256)
        status_update_queue = Queue(256)

        widgets["startDecodeButton"].setText("Start")
        running = False

        logging.info("Stopped Audio Processing.")


widgets["startDecodeButton"].clicked.connect(start_decoding)


def handle_log_update(log_update):
    global widgets

    widgets["console"].appendPlainText(log_update)
    # Make sure the scroll bar is right at the bottom.
    _sb = widgets["console"].verticalScrollBar()
    _sb.setValue(_sb.maximum())


# GUI Update Loop
def processQueues():
    """ Read in data from the queues, this decouples the GUI and async inputs somewhat. """
    global fft_update_queue, status_update_queue, decoder_init, widgets

    while fft_update_queue.qsize() > 0:
        _data = fft_update_queue.get()

        handle_fft_update(_data)

    while status_update_queue.qsize() > 0:
        _status = status_update_queue.get()

        handle_status_update(_status)

    while log_update_queue.qsize() > 0:
        _log = log_update_queue.get()
        
        handle_log_update(_log)

    # Try and force a re-draw.
    QtGui.QApplication.processEvents()

    if not decoder_init:
        # Initialise decoders, and other libraries here.
        init_payloads()
        decoder_init = True
        # Once initialised, enable the start button
        widgets["startDecodeButton"].setEnabled(True)

gui_update_timer = QtCore.QTimer()
gui_update_timer.timeout.connect(processQueues)
gui_update_timer.start(100)


class ConsoleHandler(logging.Handler):
    """ Logging handler to write to the GUI console """

    def __init__(self, log_queue):
        logging.Handler.__init__(self)
        self.log_queue = log_queue

    def emit(self, record):
        _time = datetime.datetime.now()
        _text = f"{_time.strftime('%H:%M:%S')} [{record.levelname}]  {record.msg}"

        try:
            self.log_queue.put_nowait(_text)
        except:
            print("Queue full!")



# Add console handler to top level logger.
console_handler = ConsoleHandler(log_update_queue)
logging.getLogger().addHandler(console_handler)


logging.info("Started GUI.")


# Main
def main():
    # Start the Qt Loop
    if (sys.flags.interactive != 1) or not hasattr(QtCore, "PYQT_VERSION"):
        QtGui.QApplication.instance().exec_()
        save_config(widgets)

    try:
        audio_stream.stop()
    except Exception as e:
        pass

    try:
        fft_process.stop()
    except Exception as e:
        pass

    try:
        habitat_uploader.close()
    except:
        pass


if __name__ == "__main__":
    main()
