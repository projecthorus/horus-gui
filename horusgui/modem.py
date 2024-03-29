# Modem Interfacing
import logging
from horusdemodlib.demod import Mode


# Modem paramers and defaults
HORUS_MODEM_LIST = {
    "Horus Binary v1/v2": {
        "id": Mode.BINARY_V1,
        "baud_rates": [50, 100, 300], # Note: 25 Baud removed until issues in underlying modem are fixed.
        "default_baud_rate": 100,
        "default_tone_spacing": 270,
        "use_mask_estimator": True,
        "modulation_detail": None
    },
    "RTTY (7N1)": {
        "id": Mode.RTTY_7N1,
        "baud_rates": [50, 75, 100, 200, 300, 600, 1000],
        "default_baud_rate": 100,
        "default_tone_spacing": 425,
        "use_mask_estimator": False,
        "modulation_detail": "7N1"
    },
    "RTTY (7N2)": {
        "id": Mode.RTTY_7N2,
        "baud_rates": [50, 75, 100, 200, 300, 600, 1000],
        "default_baud_rate": 100,
        "default_tone_spacing": 425,
        "use_mask_estimator": False,
        "modulation_detail": "7N2"
    },
    "RTTY (8N2)": {
        "id": Mode.RTTY_8N2,
        "baud_rates": [50, 75, 100, 200, 300, 600, 1000],
        "default_baud_rate": 100,
        "default_tone_spacing": 425,
        "use_mask_estimator": False,
        "modulation_detail": "8N1"
    },
}

DEFAULT_MODEM = "Horus Binary v1/v2"

horusModem = None


def init_horus_modem(widgets):
    """ Initialise the modem drop-down lists """

    # Clear modem list.
    widgets["horusModemSelector"].clear()

    # Add items from modem list
    for _modem in HORUS_MODEM_LIST:
        widgets["horusModemSelector"].addItem(_modem)

    # Select default modem
    widgets["horusModemSelector"].setCurrentText(DEFAULT_MODEM)

    populate_modem_settings(widgets)


def populate_modem_settings(widgets):
    """ Populate the modem settings for the current selected modem """

    _current_modem = widgets["horusModemSelector"].currentText()

    # Clear baud rate dropdown.
    widgets["horusModemRateSelector"].clear()

    # Populate
    for _rate in HORUS_MODEM_LIST[_current_modem]["baud_rates"]:
        widgets["horusModemRateSelector"].addItem(str(_rate))

    # Select default rate.
    widgets["horusModemRateSelector"].setCurrentText(
        str(HORUS_MODEM_LIST[_current_modem]["default_baud_rate"])
    )

    # Set Mask Estimator checkbox.
    widgets["horusMaskEstimatorSelector"].setChecked(
        HORUS_MODEM_LIST[_current_modem]["use_mask_estimator"]
    )

    # Set Tone Spacing Input Box
    widgets["horusMaskSpacingEntry"].setText(
        str(HORUS_MODEM_LIST[_current_modem]["default_tone_spacing"])
    )
