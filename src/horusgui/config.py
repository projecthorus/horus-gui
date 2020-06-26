#!/usr/bin/env python
#
#   Horus Telemetry GUI - Configuration
#
#   Mark Jessop <vk5qi@rfhead.net>
#

import logging
import os
from ruamel.yaml import YAML
from . import __version__


default_config = {
    'audio_device': 'None',
    'modem': 'Horus Binary v1 (Legacy)',
    'habitat_upload_enabled': True,
    'habitat_call': 'N0CALL',
    'habitat_lat': 0.0,
    'habitat_lon': 0.0,
    'habitat_antenna': "",
    'habitat_radio': "Horus-GUI "+ __version__,
    'horus_udp_enabled': True,
    'horus_udp_port': 55672
}


def init_config(filename="config.yml"):
    """ Initialise the configuration file if it does not exist """
    global default_config
    logging.info(f"Writing configuration file {filename}")

    yaml = YAML()

    try:
        with open(filename, 'w') as _outfile:
            yaml.dump(default_config, _outfile)
    except Exception as e:
        logging.error(f"Could not write configuration file - {str(e)}")



def read_config(widgets, filename="config.yml"):
    """ Read in a configuration yml file, and set up all GUI widgets """
    if not os.path.exists(filename):
        init_config(filename)

    yaml = YAML()

    _config = None

    try:
        with open(filename, 'r') as _infile:
            _config = yaml.load(_infile)
    except Exception as e:
        logging.error(f"Error reading config file - {str(e)}")

    if _config == None:
        return

    if widgets:
        # Habitat Settings
        widgets['habitatUploadSelector'].setChecked(_config['habitat_upload_enabled'])
        widgets['userCallEntry'].setText(str(_config['habitat_call']))
        widgets['userLatEntry'].setText(str(_config['habitat_lat']))
        widgets['userLonEntry'].setText(str(_config['habitat_lon']))
        widgets['userAntennaEntry'].setText(str(_config['habitat_antenna']))
        widgets['userRadioEntry'].setText(str(_config['habitat_radio']))

        # Horus Settings
        widgets['horusUploadSelector'].setChecked(_config['horus_udp_enabled'])
        widgets['horusUDPEntry'].setText(str(_config['horus_udp_port']))

        # Try and set the audio device.
        # If the audio device is not in the available list of devices, this will fail silently.
        widgets['audioDeviceSelector'].setCurrentText(_config['audio_device'])
        # Try and set the modem. If the modem is not valid, this will fail silently.
        widgets['horusModemSelector'].setCurrentText(_config['modem'])
    

    


def save_config(widgets, filename="config.yml"):
    """ Write out settings to a config file """
    global default_config

    if widgets:
        default_config['habitat_upload_enabled'] = widgets['habitatUploadSelector'].isChecked()
        default_config['habitat_call'] = widgets['userCallEntry'].text()
        default_config['habitat_lat'] = float(widgets['userLatEntry'].text())
        default_config['habitat_lon'] = float(widgets['userLonEntry'].text())
        default_config['habitat_antenna'] = widgets['userAntennaEntry'].text()
        default_config['habitat_radio'] = widgets['userRadioEntry'].text()
        default_config['horus_udp_enabled'] = widgets['horusUploadSelector'].isChecked()
        default_config['horus_udp_port'] = int(widgets['horusUDPEntry'].text())
        default_config['audio_device'] = widgets['audioDeviceSelector'].currentText()
        default_config['modem'] = widgets['horusModemSelector'].currentText()

        init_config(filename)





if __name__ == "__main__":
    read_config(None)
