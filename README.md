# Project Horus Telemetry Decododer

Written by Mark Jessop <vk5qi@rfhead.net>


### TODO LIST - Important Stuff
* Audio input via pyAudio and spectrum display. - DONE
* Integrate Horus Modems (need help from @xssfox!)
* Basic display of decoded data (RTTY or HEX data for binary)
* Decode horus binary data (move horusbinary.py into a library?)
* Upload telemetry to Habitat, with upload status.

### TODO LIST - Extras
* Save/Reload settings to file.
* UDP input from GQRX
* Waterfall Display

## Usage

### Dependencies
* [horuslib](https://github.com/projecthorus/horuslib) built, and libhorus.so available either on the system path, or in this directory.

### Create a Virtual Environment

Create a virtual environment and install dependencies.

```console
$ python3 -m venv venv
$ source venv/bin/activate
(venv) $ pip install pip -U       (Optional - this updates pip)
(venv) $ pip install -r requirements.txt
```

### Install Package

Install package in a editable state. This type of installation allows a
developer to make changes to the source code while retaining the installation
entry points so it can be used like a normal install.

```console
(venv) $ pip install -e .
```

### Run
`$ python -m horusgui.gui`