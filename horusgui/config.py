#!/usr/bin/env python
#
#   Horus Telemetry GUI - Configuration
#
#   Mark Jessop <vk5qi@rfhead.net>
#

import logging
import os
from pyqtgraph.Qt import QtCore
from ruamel.yaml import YAML
from . import __version__
from .modem import populate_modem_settings


default_config = {
    "version": __version__,
    "audio_device": "None",
    "modem": "Horus Binary v1 (Legacy)",
    "baud_rate": -1,
    "habitat_upload_enabled": True,
    "habitat_call": "N0CALL",
    "habitat_lat": 0.0,
    "habitat_lon": 0.0,
    "habitat_antenna": "",
    "habitat_radio": "Horus-GUI " + __version__,
    "horus_udp_enabled": True,
    "horus_udp_port": 55672,
}

qt_settings = QtCore.QSettings("Project Horus", "Horus-GUI")

def ValueToBool(Value):
    if isinstance(Value, bool):
        RetVal = Value
    else:
        RetVal = None
        if isinstance(Value, str):
            if Value.lower() == 'true':
                RetVal = True
            elif Value.lower() == 'false':
                RetVal = False
        else:
            RetVal = bool(Value)
    
    return RetVal


def write_config():
    """ Write global settings into QSettings """
    global default_config, qt_settings

    # Write all settings
    for _setting in default_config:
        qt_settings.setValue(_setting, default_config[_setting])
    
    logging.debug("Wrote configuration state into QSettings")


def read_config(widgets):
    """ Read in configuration settings from Qt """
    global qt_settings, default_config

    # Try and read in the version parameter from QSettings
    if qt_settings.value("version") != __version__:
        logging.debug("Configuration out of date, clearing and overwriting.")
        write_config()

    for _setting in default_config:
        default_config[_setting] = qt_settings.value(_setting)

    if widgets:
        # Habitat Settings
        widgets["habitatUploadSelector"].setChecked(ValueToBool(default_config["habitat_upload_enabled"]))
        widgets["userCallEntry"].setText(str(default_config["habitat_call"]))
        widgets["userLatEntry"].setText(str(default_config["habitat_lat"]))
        widgets["userLonEntry"].setText(str(default_config["habitat_lon"]))
        widgets["userAntennaEntry"].setText(str(default_config["habitat_antenna"]))
        widgets["userRadioEntry"].setText(str(default_config["habitat_radio"]))

        # Horus Settings
        widgets["horusUploadSelector"].setChecked(ValueToBool(default_config["horus_udp_enabled"]))
        widgets["horusUDPEntry"].setText(str(default_config["horus_udp_port"]))

        # Try and set the audio device.
        # If the audio device is not in the available list of devices, this will fail silently.
        widgets["audioDeviceSelector"].setCurrentText(default_config["audio_device"])
        # Try and set the modem. If the modem is not valid, this will fail silently.
        widgets["horusModemSelector"].setCurrentText(default_config["modem"])
        # Populate the default settings.
        populate_modem_settings(widgets)

        if default_config['baud_rate'] != -1:
            widgets["horusModemRateSelector"].setCurrentText(str(default_config['baud_rate']))



def save_config(widgets):
    """ Write out settings to a config file """
    global default_config

    if widgets:
        default_config["habitat_upload_enabled"] = widgets[
            "habitatUploadSelector"
        ].isChecked()
        default_config["habitat_call"] = widgets["userCallEntry"].text()
        default_config["habitat_lat"] = float(widgets["userLatEntry"].text())
        default_config["habitat_lon"] = float(widgets["userLonEntry"].text())
        default_config["habitat_antenna"] = widgets["userAntennaEntry"].text()
        default_config["habitat_radio"] = widgets["userRadioEntry"].text()
        default_config["horus_udp_enabled"] = widgets["horusUploadSelector"].isChecked()
        default_config["horus_udp_port"] = int(widgets["horusUDPEntry"].text())
        default_config["audio_device"] = widgets["audioDeviceSelector"].currentText()
        default_config["modem"] = widgets["horusModemSelector"].currentText()
        default_config["baud_rate"] = int(widgets["horusModemRateSelector"].currentText())

        # Write out to config file
        write_config()


if __name__ == "__main__":
    import sys
    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.DEBUG
    )

    if len(sys.argv) >= 2:
        write_config()

    read_config(None)
