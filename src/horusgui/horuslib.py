#!/usr/bin/env python3

import ctypes
from ctypes import *
import logging
import sys
from enum import Enum
import os
import logging


# TODO
# - Doc Strings
# - frame error checking
# - Modem Stats
# - demodulate should return an object with the stats

MODEM_STATS_NR_MAX = 8
MODEM_STATS_NC_MAX = 50
MODEM_STATS_ET_MAX = 8
MODEM_STATS_EYE_IND_MAX = 160
MODEM_STATS_NSPEC = 512
MODEM_STATS_MAX_F_EST = 4


class COMP(Structure):
    _fields_ = [("real", c_float), ("imag", c_float)]


class MODEM_STATS(Structure):  # modem_stats.h
    _fields_ = [
        ("Nc", c_int),
        ("snr_est", c_float),
        (
            "rx_symbols",
            (COMP * MODEM_STATS_NR_MAX) * (MODEM_STATS_NC_MAX + 1),
        ),  # rx_symbols[MODEM_STATS_NR_MAX][MODEM_STATS_NC_MAX+1];
        ("nr", c_int),
        ("sync", c_int),
        ("foff", c_float),
        ("rx_timing", c_float),
        ("clock_offset", c_float),
        ("sync_metric", c_float),
        (
            "rx_eye",
            (c_float * MODEM_STATS_ET_MAX) * MODEM_STATS_EYE_IND_MAX,
        ),  # float  rx_eye[MODEM_STATS_ET_MAX][MODEM_STATS_EYE_IND_MAX];
        ("neyetr", c_int),
        ("neyesamp", c_int),
        ("f_est", c_float * MODEM_STATS_MAX_F_EST),
        ("fft_buf", c_float * 2 * MODEM_STATS_NSPEC),
        ("fft_cfg", POINTER(c_ubyte)),
    ]


class Mode(Enum):
    BINARY = 0
    BINARY_V1 = 0
    RTTY_7N2 = 99
    BINARY_V2_256BIT = 1
    BINARY_V2_128BIT = 2


class Frame:
    def __init__(
        self,
        data: bytes,
        sync: bool,
        crc_pass: bool,
        snr: float,
        extended_stats: MODEM_STATS,
    ):
        self.data = data
        self.sync = sync
        self.snr = snr
        self.crc_pass = crc_pass
        self.extended_stats = extended_stats


class HorusLib:
    def __init__(
        self,
        libpath=f"",
        mode=Mode.BINARY,
        rate=-1,
        tone_spacing=-1,
        stereo_iq=False,
        verbose=False,
    ):
        """
        Parameters
        ----------
        libpath : str
            Path to libhorus
        mode : Mode
            horuslib.Mode.BINARY, horuslib.Mode.BINARY_V2_256BIT, horuslib.Mode.BINARY_V2_128BIT, horuslib.Mode.RTTY_7N2
        rate : int
            Changes the modem rate for supported modems. -1 for default
        tone_spacing : int
            Spacing between tones (hz) -1 for default
        stereo_iq : bool
            use stereo (IQ) input (quadrature)
        verbose : bool
            Enabled horus_set_verbose
        """

        if sys.platform == "darwin":
            libpath = os.path.join(libpath, "libhorus.dylib")
        elif sys.platform == "win32":
            libpath = os.path.join(libpath, "libhorus.dll")
        else:
            libpath = os.path.join(libpath, "libhorus.so")

        self.c_lib = ctypes.cdll.LoadLibrary(
            libpath
        )  # future improvement would be to try a few places / names

        # horus_open_advanced
        self.c_lib.horus_open_advanced.restype = POINTER(c_ubyte)

        # horus_nin
        self.c_lib.horus_nin.restype = c_uint32

        # horus_get_Fs
        self.c_lib.horus_get_Fs.restype = c_int

        # horus_set_freq_est_limits - (struct horus *hstates, float fsk_lower, float fsk_upper)
        self.c_lib.horus_set_freq_est_limits.argtype = [
            POINTER(c_ubyte),
            c_float,
            c_float,
        ]

        # horus_get_max_demod_in
        self.c_lib.horus_get_max_demod_in.restype = c_int

        # horus_get_max_ascii_out_len
        self.c_lib.horus_get_max_ascii_out_len.restype = c_int

        # horus_crc_ok
        self.c_lib.horus_crc_ok.restype = c_int

        # horus_get_modem_extended_stats - (struct horus *hstates, struct MODEM_STATS *stats)
        self.c_lib.horus_get_modem_extended_stats.argtype = [
            POINTER(MODEM_STATS),
            POINTER(c_ubyte),
        ]

        # horus_get_mFSK
        self.c_lib.horus_get_mFSK.restype = c_int

        # horus_rx
        self.c_lib.horus_rx.restype = c_int

        # struct horus *hstates, char ascii_out[], short demod_in[], int quadrature

        if type(mode) != type(Mode(0)):
            raise ValueError("Must be of type horuslib.Mode")
        else:
            self.mode = mode

        self.stereo_iq = stereo_iq

        # intial nin
        self.nin = 0

        # try to open the modem and set the verbosity
        self.hstates = self.c_lib.horus_open_advanced(
            self.mode.value, rate, tone_spacing
        )
        self.c_lib.horus_set_verbose(self.hstates, int(verbose))

        # check that the modem was actually opened and we don't just have a null pointer
        if bool(self.hstates):
            logging.debug("Opened Horus API")
        else:
            logging.error("Couldn't open Horus API for some reason")
            raise EnvironmentError("Couldn't open Horus API")

        # build some class types to fit the data for demodulation using ctypes
        max_demod_in = int(self.c_lib.horus_get_max_demod_in(self.hstates))
        max_ascii_out = int(self.c_lib.horus_get_max_ascii_out_len(self.hstates))
        self.DemodIn = c_short * (max_demod_in * (1 + int(self.stereo_iq)))
        self.DataOut = c_char * max_ascii_out
        self.c_lib.horus_rx.argtype = [
            POINTER(c_ubyte),
            c_char * max_ascii_out,
            c_short * max_demod_in,
            c_int,
        ]

        self.mfsk = int(self.c_lib.horus_get_mFSK(self.hstates))

    # in case someone wanted to use `with` style. I'm not sure if closing the modem does a lot.
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        self.c_lib.horus_close(self.hstates)
        logging.debug("Shutdown horus modem")

    def update_nin(self):
        new_nin = int(self.c_lib.horus_nin(self.hstates))
        if self.nin != new_nin:
            logging.debug(f"Updated nin {new_nin}")
        self.nin = new_nin

    def demodulate(self, demod_in: bytes):
        # from_buffer_copy requires exact size so we pad it out.
        buffer = bytearray(
            len(self.DemodIn()) * sizeof(c_short)
        )  # create empty byte array
        buffer[: len(demod_in)] = demod_in  # copy across what we have

        modulation = self.DemodIn  # get an empty modulation array
        modulation = modulation.from_buffer_copy(
            buffer
        )  # copy buffer across and get a pointer to it.

        data_out = self.DataOut()  # initilize a pointer to where bytes will be outputed

        self.c_lib.horus_rx(self.hstates, data_out, modulation, int(self.stereo_iq))

        stats = MODEM_STATS()
        self.c_lib.horus_get_modem_extended_stats(self.hstates, byref(stats))

        crc = bool(self.c_lib.horus_crc_ok(self.hstates))

        data_out = bytes(data_out)
        self.update_nin()

        # strip the null terminator out
        data_out = data_out[:-1]

        if data_out == bytes(len(data_out)):
            data_out = (
                b""  # check if bytes is just null and return an empty bytes instead
            )
        elif self.mode != Mode.RTTY:
            try:
                data_out = bytes.fromhex(data_out.decode("ascii"))
            except ValueError:
                logging.debug(data_out)
                logging.error("💥Couldn't decode the hex from the modem")
                return bytes()
        else:
            data_out = bytes(data_out.decode("ascii"))

        frame = Frame(
            data=data_out,
            snr=float(stats.snr_est),
            sync=bool(stats.sync),
            crc_pass=crc,
            extended_stats=stats,
        )
        return frame


if __name__ == "__main__":
    import sys

    filename = sys.argv[1]

    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO
    )
    with HorusLib(libpath=".", mode=Mode.BINARY, verbose=True) as horus:
        with open(filename, "rb") as f:
            while True:
                data = f.read(horus.nin * 2)
                if horus.nin != 0 and data == b"":  # detect end of file
                    break
                output = horus.demodulate(data)
                if output.crc_pass and output.data:
                    print(f"{output.data.hex()} SNR: {output.snr}")
                    for x in range(horus.mfsk):
                        print(f"F{str(x)}: {float(output.extended_stats.f_est[x])}")
