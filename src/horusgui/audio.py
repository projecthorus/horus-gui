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
    widgets['audioDeviceSelector'].clear()

    # Iterate through PyAudio devices
    for x in range(0, pyAudio.get_device_count()):
        _dev = pyAudio.get_device_info_by_index(x)

        # Does the device have inputs?
        if _dev['maxInputChannels'] > 0:
            # Get the name
            _name = _dev['name']
            # Add to local store of device info
            audioDevices[_name] = _dev
            # Add to audio device selection list.
            widgets['audioDeviceSelector'].addItem(_name)
        
    # Select first item.
    if len(list(audioDevices.keys())) > 0:
        widgets['audioDeviceSelector'].setCurrentIndex(0)

    # Initial population of sample rates.
    populate_sample_rates(widgets)

    return audioDevices


def populate_sample_rates(widgets):
    """ Populate the sample rate ComboBox with the sample rates of the currently selected audio device """
    global audioDevices

    # Clear list of sample rates.
    widgets['audioSampleRateSelector'].clear()

    # Get information on current audio device
    _dev_name = widgets['audioDeviceSelector'].currentText()

    if _dev_name in audioDevices:
        # TODO: Determine valid samples rates. For now, just use the default.
        _samp_rate = int(audioDevices[_dev_name]['defaultSampleRate'])
        widgets['audioSampleRateSelector'].addItem(str(_samp_rate))
        widgets['audioSampleRateSelector'].setCurrentIndex(0)
    else:
        logging.error("Audio - Unknown Audio Device")




class AudioStream(object):
    """ Start up a pyAudio input stream, and pass data around to different callbacks """

    def __init__(
        self,
        audio_device,
        fs,
        block_size = 8192,

        fft_input = None,
        modem = None
    ):
        
        self.audio_device = audio_device
        self.fs = fs
        self.block_size = block_size

        self.fft_input = fft_input

        self.modem = modem
        

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
            stream_callback=self.handle_samples
        )


    def handle_samples(self, data, frame_count, time_info="", status_flags=""):
        """ Handle incoming samples from pyaudio """


        # Pass samples directly into fft.
        if self.fft_input:
            self.fft_input(data)

        
        # TODO: Handle modem sample input.


        return (None, pyaudio.paContinue)

    
    def stop(self):
        """ Halt stream """
        self.stream.close()

