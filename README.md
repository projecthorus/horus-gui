# Project Horus Telemetry Decoder

Telemetry demodulator for the following modems in use by Project Horus
* Horus Binary Modes
  * v1 - Legacy 22 byte mode, Golay FEC
  * v2 - 16/32-byte modes, LDPC FEC (Still in development)
* RTTY (7N2 only)


Written by Mark Jessop <vk5qi@rfhead.net>

**Note: This is very much a work in progress!**


### TODO LIST - Important Stuff
* Audio input via pyAudio and spectrum display. - DONE
* Integrate Horus Modems (need help from @xssfox!) - First pass DONE
* Basic display of decoded data (RTTY or HEX data for binary) - DONE
* Save/Reload settings to file - Initial pass done.
* Decode horus binary data (move horusbinary.py into a library?)
* Upload telemetry to Habitat, with upload status - DONE
* Better build system (build horuslib as part of package build?)
* Windows binary

### TODO LIST - Extras
* UDP input from GQRX
* Waterfall Display 

## Usage

### Build HorusLib

```
$ git clone https://github.com/projecthorus/horuslib.git
$ cd horuslib && mkdir build_linux && cd build_linux
$ cmake ..
$ make
$ cp src/libhorus.so ../../
```

(Replace .so with .dylib under OSX)

TODO: Make a separate horuslib python package, which handles building of the library.

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