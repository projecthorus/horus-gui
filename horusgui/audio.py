# Audio Interfacing
import logging
import pyaudio


# Global PyAudio object
pyAudio = None
audioStream = None

audioDevices = {}


def init_audio(widgets):
    """ Initialise pyaudio object, and populate list of sound card in GUI """
    global pyAudio, audioDevices

    # Init PyAudio
    pyAudio = pyaudio.PyAudio()
    audioDevices = {}

    # Clear list
    widgets["audioDeviceSelector"].clear()
    # Add in the 'dummy' GQRX UDP interface
    widgets["audioDeviceSelector"].addItem('UDP Audio (127.0.0.1:7355)')
    
    
    # Get list of Host APIs
    _host_apis = []
    for y in range(0, pyAudio.get_host_api_count()):
        _hapi = pyAudio.get_host_api_info_by_index(y)['name']
        
        # Shorten the Host API name a little.
        if 'Windows ' in _hapi:
            _host_apis.append(_hapi.replace("Windows ",""))
        else:
            _host_apis.append(_hapi)

    # Iterate through PyAudio devices
    for x in range(0, pyAudio.get_device_count()):
        _dev = pyAudio.get_device_info_by_index(x)

        # Does the device have inputs?
        if _dev["maxInputChannels"] > 0:
            _hapi = _dev['hostApi']
            # Get the name
            _name = _dev["name"] + " (" + _host_apis[_hapi] + ")"
            # Add to local store of device info
            audioDevices[_name] = _dev
            # Add to audio device selection list.
            widgets["audioDeviceSelector"].addItem(_name)
            logging.debug(f"Found audio device: {_name}")

    # Select first item.
    if len(list(audioDevices.keys())) > 0:
        widgets["audioDeviceSelector"].setCurrentIndex(0)

    # Initial population of sample rates.
    populate_sample_rates(widgets)

    return audioDevices


def populate_sample_rates(widgets):
    """ Populate the sample rate ComboBox with the sample rates of the currently selected audio device """
    global audioDevices, pyAudio

    # Clear list of sample rates.
    widgets["audioSampleRateSelector"].clear()

    # Get information on current audio device
    _dev_name = widgets["audioDeviceSelector"].currentText()

    
    if _dev_name == 'UDP Audio (127.0.0.1:7355)':
        # Add in fixed sample rate for GQRX/SDR++ input, which only outputs at 48 kHz.
        widgets["audioSampleRateSelector"].addItem(str(48000))
        widgets["audioSampleRateSelector"].setCurrentIndex(0)

        return

    if _dev_name in audioDevices:
        # Determine which sample rates from a common list are valid for this device.
        _possible_rates = [8000.0, 22050.0, 44100.0, 48000.0, 96000.0]
        _valid_rates = []
        for _rate in _possible_rates:
            _dev_info = audioDevices[_dev_name]
            _valid = False
            try:
                _valid = pyAudio.is_format_supported(
                    _rate,
                    input_device=_dev_info['index'],
                    input_channels=1,
                    input_format=pyaudio.paInt16
                )
            except ValueError:
                # Why oh why do you throw an exception instead of returning FALSE pyaudio...
                _valid = False
            
            if _valid:
                widgets["audioSampleRateSelector"].addItem(str(int(_rate)))
                _valid_rates.append(str(int(_rate)))

        # Use 48 kHz sample rate if the sound card supports it.
        if "48000" in _valid_rates: 
            widgets["audioSampleRateSelector"].setCurrentText("48000")
        else:
            # Otherwise use the default.
            _default_samp_rate = int(audioDevices[_dev_name]["defaultSampleRate"])
            widgets["audioSampleRateSelector"].setCurrentText(str(_default_samp_rate))
    else:
        logging.error(f"Audio - Unknown Audio Device ({_dev_name})")


class AudioStream(object):
    """ Start up a pyAudio input stream, and pass data around to different callbacks """

    def __init__(self, audio_device, fs, block_size=8192, fft_input=None, modem=None, stats_callback = None):

        self.audio_device = audio_device
        self.fs = fs
        self.block_size = block_size

        self.fft_input = fft_input

        self.modem = modem
        self.stats_callback = stats_callback

        # Start audio stream
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.fs,
            frames_per_buffer=self.block_size,
            input=True,
            input_device_index=self.audio_device,
            output=False,
            stream_callback=self.handle_samples,
        )

    def handle_samples(self, data, frame_count, time_info="", status_flags=""):
        """ Handle incoming samples from pyaudio """

        # Pass samples directly into fft.
        if self.fft_input:
            self.fft_input(data)

        if self.modem:
            # Add samples to modem
            _stats = self.modem.add_samples(data)
            # Send any stats data back to the stats callback
            if _stats:
                if self.stats_callback:
                    self.stats_callback(_stats)

        return (None, pyaudio.paContinue)

    def stop(self):
        """ Halt stream """
        self.stream.close()
