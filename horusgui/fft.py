# FFT
import logging
import time
import numpy as np
from queue import Queue
from threading import Thread


class FFTProcess(object):
    """ Process an incoming stream of samples, and calculate FFTs """

    def __init__(
        self,
        nfft=8192,
        stride=4096,
        fs=48000,
        sample_width=2,
        range=[100, 4000],
        callback=None,
    ):
        self.nfft = nfft
        self.stride = stride
        self.fs = fs
        self.sample_width = sample_width
        self.range = range

        self.callback = callback

        self.sample_buffer = bytearray(b"")

        self.input_queue = Queue(512)

        self.init_window()

        self.processing_thread_running = True

        self.t = Thread(target=self.processing_thread)
        self.t.start()

    def init_window(self):
        """ Initialise Window functions and FFT scales. """
        self.window = np.hanning(self.nfft)
        self.fft_scale = np.fft.fftshift(np.fft.fftfreq(self.nfft)) * self.fs
        self.mask = (self.fft_scale > self.range[0]) & (self.fft_scale < self.range[1])

    def perform_fft(self):
        """ Perform a FFT on the first NFFT samples in the sample buffer, then shift the buffer along """

        # Convert raw data to floats.
        raw_data = np.fromstring(
            bytes(self.sample_buffer[: self.nfft * self.sample_width]), dtype=np.int16
        )
        raw_data = raw_data.astype(np.float64) / (2 ** 15)

        # Advance sample buffer
        self.sample_buffer = self.sample_buffer[self.stride * self.sample_width :]

        # Calculate FFT
        _fft = 20 * np.log10(
            np.abs(np.fft.fftshift(np.fft.fft(raw_data * self.window)))
        ) - 20 * np.log10(self.nfft)

        if self.callback != None:
            self.callback({"fft": _fft[self.mask], "scale": self.fft_scale[self.mask]})

    def process_block(self, samples):
        """ Add a block of samples to the input buffer. Calculate and process FFTs if the buffer is big enough """

        self.sample_buffer.extend(samples)

        while len(self.sample_buffer) > self.nfft * self.sample_width:
            self.perform_fft()

    def processing_thread(self):

        while self.processing_thread_running:
            if self.input_queue.qsize() > 0:
                data = self.input_queue.get()
                self.process_block(data)
            else:
                time.sleep(0.01)

    def add_samples(self, samples):
        """ Add a block of samples to the input queue """
        try:
            self.input_queue.put_nowait(samples)
        except:
            logging.error("Input overrun!")

    def flush(self):
        """ Clear the sample buffer """
        self.sample_buffer = bytearray(b"")

    def stop(self):
        """ Halt processing """
        self.processing_thread_running = False
