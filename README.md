# Project Horus Telemetry Decoder

Telemetry demodulator for the following modems in use by Project Horus
* Horus Binary Modes
  * v1 - Legacy 22 byte mode, Golay FEC
  * v2 - 16/32-byte modes, LDPC FEC (Still in development)
* RTTY (7N2 only, for now)


Written by Mark Jessop <vk5qi@rfhead.net>

**Note: This is very much a work in progress!**


### TODO LIST - Important Stuff
* Stop decoded data pane from resizing on bad/long decodes - TODO
* Export of telemetry via Horus UDP
* Better build system 
* Windows binary

### TODO LIST - Extras
* UDP input from GQRX
* Waterfall Display  (? Need something GPU accelerated if possible...)

## Usage

### Build HorusLib

```console
$ git clone https://github.com/projecthorus/horusdemodlib.git
$ cd horusdemodlib && mkdir build && cd build
$ cmake ..
$ make
$ make install
```

### Grab this Repo
```console
$ git clone https://github.com/projecthorus/horus-gui.git
$ cd horus-gui
```

### (Optional) Create a Virtual Environment

Create a virtual environment and install dependencies.
```console
$ python3 -m venv venv
$ source venv/bin/activate
(venv) $ pip install pip -U       (Optional - this updates pip)
```

### Install Python Dependencies
```console
$ pip install -r requirements.txt
```

NOTE: If you get errors relating to pyaudio when trying to install into a venv, make sure that portaudio is installed (`libportaudio-dev` under Linux distros, or `portaudio` under Macports), and then install pyaudio pointing to the portaudio lib by running:
```
(Linux) $ pip install --global-option='build_ext' --global-option='-I/usr/include' --global-option='-L/usr/lib' pyaudio
(OSX)   $ pip install --global-option='build_ext' --global-option='-I/opt/local/include' --global-option='-L/opt/local/lib' pyaudio
```
You should then be able to re-run the install requirements command above.

### Install Package

Install package in a editable state. This type of installation allows a
developer to make changes to the source code while retaining the installation
entry points so it can be used like a normal install.

```console
(venv) $ pip install -e .
```

### Run
```console
$ python -m horusgui.gui
```