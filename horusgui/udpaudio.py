# UDP Audio Source (Obtaining audio from GQRX)
import socket
import traceback
from threading import Thread

class UDPStream(object):
    """ Listen for UDP Audio data from GQRX (s16, 48kHz), and pass data around to different callbacks """

    def __init__(self, udp_port=7355, fs=48000, block_size=8192, fft_input=None, modem=None, stats_callback = None):

        self.udp_port = udp_port
        self.fs = fs
        self.block_size = block_size

        self.fft_input = fft_input

        self.modem = modem
        self.stats_callback = stats_callback

        # Start audio stream
        self.listen_thread_running = True
        self.listen_thread = Thread(target=self.udp_listen_thread)
        self.listen_thread.start()


    def udp_listen_thread(self):
        """ Open a UDP socket and listen for incoming data """

        self.s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.s.settimeout(1)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # OSX Specific
        try:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except:
            pass
    
        self.s.bind(('127.0.0.1',self.udp_port))
        while self.listen_thread_running:
            try:
                m = self.s.recvfrom(65535)
            except socket.timeout:
                m = None
            except:
                traceback.print_exc()
            
            if m != None:
                self.handle_samples(m[0], len(m[0])//2)

        self.s.close()


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

        return (None, None)

    def stop(self):
        """ Halt stream """
        self.listen_thread_running = False


if __name__ == "__main__":
    import time

    udp = UDPStream()

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        udp.close()