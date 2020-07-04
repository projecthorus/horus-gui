#!/usr/bin/env python
#
#   Horus Telemetry GUI - Horus UDP
#
#   Mark Jessop <vk5qi@rfhead.net>
#
import crcmod
import datetime
import json
import logging
import socket


def crc16_ccitt(data):
    """
    Calculate the CRC16 CCITT checksum of *data*.
    
    (CRC16 CCITT: start 0xFFFF, poly 0x1021)
    """
    crc16 = crcmod.predefined.mkCrcFun("crc-ccitt-false")
    return hex(crc16(data))[2:].upper().zfill(4)


def decode_ukhas_sentence(sentence):
    """ 
        Attempt to parse a UKHAS-compatible sentence into a dictionary 

        NOTE: This function is limited to the following:
        * Decimal-degree lat/lon fields.
        * CRC16-CCITT Checksums
        * Time in HH:MM:SS
        * Fields in order: $$CALLSIGN,sequence_no,HH:MM:SS,lat,lon,alt,.....*CRC16
    
    """
    # Try and proceed through the following. If anything fails, we have a corrupt sentence.
    try:
        # Strip out any leading/trailing whitespace.
        _sentence = sentence.strip()

        # First, try and find the start of the sentence, which always starts with '$$''
        _sentence = _sentence.split("$$")[-1]
        # Hack to handle odd numbers of $$'s at the start of a sentence
        if _sentence[0] == "$":
            _sentence = _sentence[1:]
        # Now try and split out the telemetry from the CRC16.
        _telem = _sentence.split("*")[0]
        _crc = _sentence.split("*")[1]

        # Now check if the CRC matches.
        _calc_crc = crc16_ccitt(_telem.encode("ascii"))

        if _calc_crc != _crc:
            logging.error("Could not parse ASCII Sentence - CRC Fail.")
            return None

        # We now have a valid sentence! Extract fields..
        _fields = _telem.split(",")

        _callsign = _fields[0]
        _time = _fields[2]
        _latitude = float(_fields[3])
        _longitude = float(_fields[4])
        _altitude = int(_fields[5])
        # The rest we don't care about.

        # Perform some sanity checks on the data.

        # Attempt to parse the time string. This will throw an error if any values are invalid.
        try:
            _time_dt = datetime.datetime.strptime(_time, "%H:%M:%S")
        except:
            logging.error("Could not parse ASCII Sentence - Invalid Time.")
            return None

        # Check if the lat/long is 0.0,0.0 - no point passing this along.
        if _latitude == 0.0 or _longitude == 0.0:
            logging.error("Could not parse ASCII Sentence - Zero Lat/Long.")
            return None

        # Place a limit on the altitude field. We generally store altitude on the payload as a uint16, so it shouldn't fall outside these values.
        if _altitude > 65535 or _altitude < 0:
            logging.error("Could not parse ASCII Sentence - Invalid Altitude.")
            return None

        # Produce a dict output which is compatible with send_payload_summary below
        _telem = {
            "callsign": _callsign,
            "time": _time,
            "latitude": _latitude,
            "longitude": _longitude,
            "altitude": _altitude,
            "speed": -1,
            "heading": -1,
            "temp": -1,
            "sats": -1,
            "batt_voltage": -1,
        }

        return _telem

    except Exception as e:
        logging.error("Could not parse ASCII Sentence - %s" % str(e))
        return None


def send_payload_summary(telemetry, port=55672, comment="Horus Binary"):
    """ Send a payload summary message into the network via UDP broadcast.

    Args:
    telemetry (dict): Telemetry dictionary to send.
    port (int): UDP port to send to.

    """

    try:
        # Do a few checks before sending.
        if telemetry["latitude"] == 0.0 and telemetry["longitude"] == 0.0:
            logging.error("Horus UDP - Zero Latitude/Longitude, not sending.")
            return

        packet = {
            "type": "PAYLOAD_SUMMARY",
            "callsign": telemetry["callsign"],
            "latitude": telemetry["latitude"],
            "longitude": telemetry["longitude"],
            "altitude": telemetry["altitude"],
            "speed": telemetry["speed"],
            "heading": -1,
            "time": telemetry["time"],
            "comment": comment,
            "temp": telemetry["temp"],
            "sats": telemetry["sats"],
            "batt_voltage": telemetry["batt_voltage"],
        }

        # Set up our UDP socket
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.settimeout(1)
        # Set up socket for broadcast, and allow re-use of the address
        _s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        _s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Under OSX we also need to set SO_REUSEPORT to 1
        try:
            _s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except:
            pass

        try:
            _s.sendto(json.dumps(packet).encode("ascii"), ("<broadcast>", port))
        # Catch any socket errors, that may occur when attempting to send to a broadcast address
        # when there is no network connected. In this case, re-try and send to localhost instead.
        except socket.error as e:
            logging.debug(
                "Horus UDP - Send to broadcast address failed, sending to localhost instead."
            )
            _s.sendto(json.dumps(packet).encode("ascii"), ("127.0.0.1", port))

        _s.close()

    except Exception as e:
        logging.error("Horus UDP - Error sending Payload Summary: %s" % str(e))


if __name__ == "__main__":
    # Test script for the above functions

    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO
    )

    sentence = "$$TESTING,1,01:02:03,-34.0,138.0,1000"
    crc = crc16_ccitt(sentence[2:].encode("ascii"))
    sentence = sentence + "*" + crc
    print("Sentence: " + sentence)

    _decoded = decode_ukhas_sentence(sentence)
    print(_decoded)

    send_payload_summary(_decoded)
