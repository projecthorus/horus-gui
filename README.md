# Project Horus Telemetry Decododer

Written by Mark Jessop <vk5qi@rfhead.net>




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