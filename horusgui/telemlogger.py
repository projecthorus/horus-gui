# Telemetry Logging
import csv
import datetime
import json
import logging
import os.path
import time
from threading import Thread
from queue import Queue


class TelemetryLogger(object):
    """
    Telemetry Logger Class

    Queued telemetry logging class
    """

    def __init__(
        self,
        log_directory = None,
        log_format = "CSV",
        enabled = False
    ):
        self.log_directory = log_directory
        self.log_format = log_format
        self.enabled = enabled

        self.log_directory_updated = False

        self.input_queue = Queue()
        self.json_filenames = {}
        self.csv_filenames = {}

        self.processing_running = True

        self.processing_thread = Thread(target=self.process_telemetry)
        self.processing_thread.start()


    def write_json(self, telemetry):

        # Remove detailed packet format information if it exists.
        if 'packet_format' in telemetry:
            telemetry.pop('packet_format')

        if telemetry['callsign'] not in self.json_filenames:
            _filename = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S") + f"_{telemetry['callsign']}.json"
            _filepath = os.path.join(self.log_directory, _filename)

            try:
                _current_f = open(_filepath, 'a')
                self.json_filenames[telemetry['callsign']] = _filepath
                logging.info(f"Telemetry Logger - Opened new log file: {_filepath}")

            except Exception as e:
                logging.error(f"Telemetry Logger - Could not open log file in directory {self.log_directory}. Disabling logger.")
                self.enabled = False
                return
        
        else:
            # Open the file we already have started writing to.
            try:
                _current_f = open(self.json_filenames[telemetry['callsign']], 'a')
            except Exception as e:
                # Couldn't open log file. Remove filename from local list so we try and make a new file on next telemetry.
                logging.error(f"Telemetry Logger - Could not open existing log file {self.json_filenames[telemetry['callsign']]}.")
                self.json_filenames.pop(telemetry['callsign'])
                return

        # Convert telemetry to JSON
        _data = json.dumps(telemetry) + "\n"
        # Write to file.
        _current_f.write(_data)
        # Close file.
        _current_f.close()


    def write_csv(self, telemetry):
        # Remove detailed packet format information if it exists.
        if 'packet_format' in telemetry:
            telemetry.pop('packet_format')

        if 'ukhas_str' in telemetry:
            telemetry.pop('ukhas_str')

        if 'custom_field_names' in telemetry:
            telemetry.pop('custom_field_names')

        csv_keys = list(telemetry.keys())
        csv_keys.sort()
        csv_keys.remove("time")
        csv_keys.remove("callsign")
        csv_keys.remove("latitude")
        csv_keys.remove("longitude")
        csv_keys.remove("altitude")
        csv_keys.insert(0,"time") # datetime should be at the front of the CSV
        csv_keys.insert(1,"callsign")
        csv_keys.insert(2,"latitude")
        csv_keys.insert(3,"longitude")
        csv_keys.insert(4,"altitude")


        if telemetry['callsign'] not in self.csv_filenames:
            _filename = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S") + f"_{telemetry['callsign']}.csv"
            _filepath = os.path.join(self.log_directory, _filename)

            try:
                _current_f = open(_filepath, 'a')
                self.csv_filenames[telemetry['callsign']] = _filepath
                logging.info(f"Telemetry Logger - Opened new log file: {_filepath}")

                fc = csv.DictWriter(_current_f, fieldnames=csv_keys)
                fc.writeheader()

            except Exception as e:
                logging.error(f"Telemetry Logger - Could not open log file in directory {self.log_directory}. Disabling logger.")
                self.enabled = False
                return
        
        else:
            # Open the file we already have started writing to.
            try:
                _current_f = open(self.csv_filenames[telemetry['callsign']], 'a')
            except Exception as e:
                # Couldn't open log file. Remove filename from local list so we try and make a new file on next telemetry.
                logging.error(f"Telemetry Logger - Could not open existing log file {self.csv_filenames[telemetry['callsign']]}.")
                self.csv_filenames.pop(telemetry['callsign'])
                return

        fc = csv.DictWriter(_current_f, fieldnames=csv_keys)
        fc.writerows([telemetry])
        # Close file.
        _current_f.close()


    def handle_telemetry(self, telemetry):

        if self.log_directory.strip() == "" or self.log_directory is None:
            return

        if self.log_directory_updated:
            # Log directory has been moved, clear out existing filenames.
            self.json_filenames = {}
            self.csv_filenames = {}
            self.log_directory_updated = False
        
        if self.log_format == "JSON":
            self.write_json(telemetry)
        elif self.log_format == "CSV":
            self.write_csv(telemetry)
        else:
            logging.error(f"Telemetry Logger - Unknown Logging Format {self.log_format}")

    def process_telemetry(self):

        logging.debug("Started Telemetry Logger Thread")
        
        while self.processing_running:

            while self.input_queue.qsize() > 0:
                try:
                    self.handle_telemetry(self.input_queue.get())
                except Exception as e:
                    logging.error(f"Telemetry Logger - Error handling telemetry - {str(e)}")

            time.sleep(1)

        logging.debug("Closed Telemetry Logger Thread")

    def add(self, telemetry):
        if self.enabled:
            try:
                self.input_queue.put_nowait(telemetry)
            except Exception as e:
                logging.error("Telemetry Logger - Error adding sentence to queue: %s" % str(e))

    def update_log_directory(self, directory):
        """ Update the log directory in a hopefully clean manner """
        self.log_directory = directory
        self.log_directory_updated = True

    def close(self):
        self.processing_running = False