#!/usr/bin/env python
#
#   Horus Telemetry GUI - Configuration
#
#   Mark Jessop <vk5qi@rfhead.net>
#
import json
import logging
import os
from pyqtgraph.Qt import QtCore
from . import __version__
from .modem import populate_modem_settings
from .audio import populate_sample_rates
from horusdemodlib.payloads import download_latest_payload_id_list, download_latest_custom_field_list, read_payload_list, read_custom_field_list
import horusdemodlib.payloads

default_config = {
    "version": __version__,
    "audio_device": "None",
    "audio_sample_rate": "48000",
    "modem": "Horus Binary v1 (Legacy)",
    "baud_rate": -1,
    "habitat_upload_enabled": True,
    "habitat_call": "N0CALL",
    "habitat_lat": 0.0,
    "habitat_lon": 0.0,
    "habitat_alt": 0.0,
    "habitat_antenna": "",
    "habitat_radio": "",
    "horus_udp_enabled": True,
    "horus_udp_port": 55672,
    "ozimux_enabled": False,
    "ozimux_udp_port": 55683,
    "rotator_type": "rotctld",
    "rotator_host": "localhost",
    "rotator_port": 4533,
    "rotator_rangeinhibit": True,
    "logging_enabled": False,
    "log_format": "CSV",
    "log_directory": "",
    "payload_list": json.dumps(horusdemodlib.payloads.HORUS_PAYLOAD_LIST),
    "custom_field_list": json.dumps({})
}

qt_settings = QtCore.QSettings("Project Horus", "Horus-GUI")

def ValueToBool(Value):
    """ Helper function to deal with QSettings inconsistency in handling boolean values """
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
    
    logging.info("Current configuration saved.")


def read_config(widgets):
    """ Read in configuration settings from Qt """
    global qt_settings, default_config

    # This is getting a bit ridiculous, need to re-think this approach.
    OK_VERSIONS = [__version__, '0.3.18', '0.3.17', '0.3.16', '0.3.15', '0.3.14', '0.3.13', '0.3.12', '0.3.11', '0.3.10', '0.3.9', '0.3.8', '0.3.7', '0.3.6', '0.3.5', '0.3.4', '0.3.1', '0.2.1']
    
    # Try and read in the version parameter from QSettings
    if qt_settings.value("version") not in OK_VERSIONS:
        logging.debug("Configuration out of date, clearing and overwriting.")
        write_config()

    for _setting in default_config:
        try:
            _new_setting = qt_settings.value(_setting)
            if _new_setting is not None:
                default_config[_setting] = _new_setting
        except Exception as e:
            logging.debug("Missing config setting: " + _setting)

    if widgets:
        # Habitat Settings
        widgets["sondehubUploadSelector"].setChecked(ValueToBool(default_config["habitat_upload_enabled"]))
        widgets["userCallEntry"].setText(str(default_config["habitat_call"]))
        widgets["userLatEntry"].setText(str(default_config["habitat_lat"]))
        widgets["userLonEntry"].setText(str(default_config["habitat_lon"]))
        widgets["userAltEntry"].setText(str(default_config["habitat_alt"]))
        widgets["userAntennaEntry"].setText(str(default_config["habitat_antenna"]))
        widgets["userRadioEntry"].setText(str(default_config["habitat_radio"]))

        # Horus Settings
        widgets["horusUploadSelector"].setChecked(ValueToBool(default_config["horus_udp_enabled"]))
        widgets["horusUDPEntry"].setText(str(default_config["horus_udp_port"]))
        widgets["ozimuxUploadSelector"].setChecked(ValueToBool(default_config["ozimux_enabled"]))
        widgets["ozimuxUDPEntry"].setText(str(default_config["ozimux_udp_port"]))

        # Try and set the audio device.
        # If the audio device is not in the available list of devices, this will fail silently.
        widgets["audioDeviceSelector"].setCurrentText(default_config["audio_device"])
        # Populate the list of valid sample rates
        populate_sample_rates(widgets)
        # Attempt to set the configured sample rate. This will fail silently if it does not exist.
        widgets["audioSampleRateSelector"].setCurrentText(str(default_config["audio_sample_rate"]))

        # Try and set the modem. If the modem is not valid, this will fail silently.
        widgets["horusModemSelector"].setCurrentText(default_config["modem"])
        # Populate the default settings.
        populate_modem_settings(widgets)

        # Rotator Settings
        widgets["rotatorTypeSelector"].setCurrentText(default_config["rotator_type"])
        widgets["rotatorHostEntry"].setText(str(default_config["rotator_host"]))
        widgets["rotatorPortEntry"].setText(str(default_config["rotator_port"]))
        widgets["rotatorRangeInhibit"].setChecked(ValueToBool(default_config["rotator_rangeinhibit"]))

        # Logging Settings
        widgets["loggingPathEntry"].setText(str(default_config["log_directory"]))
        widgets["loggingFormatSelector"].setCurrentText(default_config["log_format"])
        widgets["enableLoggingSelector"].setChecked(ValueToBool(default_config["logging_enabled"]))

        if default_config['baud_rate'] != -1:
            widgets["horusModemRateSelector"].setCurrentText(str(default_config['baud_rate']))


    if 'payload_list' in default_config:
        _payloads = json.loads(default_config['payload_list'])
        # JSON converts the int dictionary keys into strings... annoying!
        _temp = {}
        for _key in _payloads:
            _temp[int(_key)] = _payloads[_key]
        
        default_config['payload_list'] = _temp





def save_config(widgets):
    """ Write out settings to a config file """
    global default_config

    if widgets:
        default_config["habitat_upload_enabled"] = widgets[
            "sondehubUploadSelector"
        ].isChecked()
        default_config["version"] = __version__
        default_config["habitat_call"] = widgets["userCallEntry"].text()
        default_config["habitat_lat"] = float(widgets["userLatEntry"].text())
        default_config["habitat_lon"] = float(widgets["userLonEntry"].text())
        default_config["habitat_alt"] = float(widgets["userAltEntry"].text())
        default_config["habitat_antenna"] = widgets["userAntennaEntry"].text()
        default_config["habitat_radio"] = widgets["userRadioEntry"].text()
        default_config["horus_udp_enabled"] = widgets["horusUploadSelector"].isChecked()
        default_config["horus_udp_port"] = int(widgets["horusUDPEntry"].text())
        default_config["ozimux_enabled"] = widgets["ozimuxUploadSelector"].isChecked()
        default_config["ozimux_udp_port"] = int(widgets["ozimuxUDPEntry"].text())
        default_config["audio_device"] = widgets["audioDeviceSelector"].currentText()
        default_config["audio_sample_rate"] = widgets["audioSampleRateSelector"].currentText()
        default_config["modem"] = widgets["horusModemSelector"].currentText()
        default_config["baud_rate"] = int(widgets["horusModemRateSelector"].currentText())
        default_config["rotator_type"] = widgets["rotatorTypeSelector"].currentText()
        default_config["rotator_host"] = widgets["rotatorHostEntry"].text()
        default_config["rotator_port"] = int(widgets["rotatorPortEntry"].text())
        default_config["rotator_rangeinhibit"] = widgets["rotatorRangeInhibit"].isChecked()
        default_config["logging_enabled"] = widgets["enableLoggingSelector"].isChecked()
        default_config["log_directory"] = widgets["loggingPathEntry"].text()
        default_config["log_format"] = widgets["loggingFormatSelector"].currentText()

        default_config["payload_list"] = json.dumps(horusdemodlib.payloads.HORUS_PAYLOAD_LIST)
        default_config["custom_field_list"] = json.dumps(horusdemodlib.payloads.HORUS_CUSTOM_FIELDS)

        # Write out to config file
        write_config()


def init_payloads(payload_id_list=None, custom_field_list=None):
    """ Attempt to download the latest payload / config data, and update local configs """
    global default_config

    # Attempt to grab the payload list.
    if payload_id_list is None:
        _payload_list = download_latest_payload_id_list(timeout=3)
    else:
        logging.info(f"Using supplied Payload ID list file: {payload_id_list}")
        _payload_list = read_payload_list(payload_id_list)

    if _payload_list:
        # Sanity check the result
        if 0 in _payload_list:
            horusdemodlib.payloads.HORUS_PAYLOAD_LIST = _payload_list
            logging.info(f"Updated Payload List Successfuly!")
        else:
            logging.critical("Could not read payload list!")
    else:
        if 'payload_list' in default_config:
            # Maybe we have a stored config we can use.
            try:
                _payload_list = default_config['payload_list']
                if 0 in _payload_list:
                    horusdemodlib.payloads.HORUS_PAYLOAD_LIST = _payload_list
                    logging.warning(f"Loaded Payload List from local cache, may be out of date!")
                else:
                    logging.critical("Could not read stored payload list!")
            except Exception as e:
                logging.critical(f"Could not read stored payload list - {str(e)}")
        else:
            logging.critical("Payload list not available in local storage!")

    logging.info(f"Payload List contains {len(list(horusdemodlib.payloads.HORUS_PAYLOAD_LIST.keys()))} entries.")

    if custom_field_list is None:
        _custom_fields = download_latest_custom_field_list(timeout=3)
    else:
        logging.info(f"Using supplied Custom Field List file: {custom_field_list}")
        _custom_fields = read_custom_field_list(custom_field_list)

    if _custom_fields:
        # Sanity Check
        if '4FSKTEST-V2' in _custom_fields:
            horusdemodlib.payloads.HORUS_CUSTOM_FIELDS = _custom_fields
            logging.info(f"Updated Custom Field List Successfuly!")
        else:
            logging.critical("Could not read custom field list!")
    else:
        if 'custom_field_list' in default_config:
            # Maybe we have a stored config we can use.
            try:
                _custom_fields = json.loads(default_config['custom_field_list'])
                if '4FSKTEST-V2' in _custom_fields:
                    horusdemodlib.payloads.HORUS_CUSTOM_FIELDS = _custom_fields
                    logging.warning("Loaded Custom Fields List from local cache, may be out of date!")
                else:
                    logging.critical("Could not read stored custom fields list!")
            except Exception as e:
                logging.critical(f"Could not read stored custom fields list - {str(e)}")
        else:
            logging.critical("Custom Field list not available in local storage!")
    
    logging.info(f"Custom Field list contains {len(list(horusdemodlib.payloads.HORUS_CUSTOM_FIELDS.keys()))} entries.")




if __name__ == "__main__":
    import sys
    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.DEBUG
    )

    if len(sys.argv) >= 2:
        write_config()

    read_config(None)
