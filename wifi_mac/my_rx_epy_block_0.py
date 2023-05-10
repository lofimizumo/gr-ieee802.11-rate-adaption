import numpy as np
from gnuradio import gr
import pmt
import time

class message_handler(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(
            self,
            name='Message Handler',
            in_sig=[],
            out_sig=[]
        )
        self.message_port_register_in(gr.pmt.intern('in'))
        self.set_msg_handler(gr.pmt.intern('in'), self.handle_message)
        self.bytes_received_last_second = 0
        self.last_reset_time = time.time()

    def handle_message(self, msg):
        # Extract metadata
        metadata = pmt.car(msg)
        metadata_dict = pmt.to_python(metadata)
        frame_bytes = metadata_dict['frame bytes']

        # Update bytes received in the last second
        self.bytes_received_last_second += frame_bytes

        # Check if one second has passed since the last reset
        current_time = time.time()
        elapsed_time = current_time - self.last_reset_time

        if elapsed_time >= 1.0:
            # Calculate and print throughput for the last second
            throughput = self.bytes_received_last_second * 8 / elapsed_time / 1e6  # Convert to Mbps
            print(f"Throughput: {throughput} Mbps")

            # Reset the counter and update the reset time
            self.bytes_received_last_second = 0
            self.last_reset_time = current_time

