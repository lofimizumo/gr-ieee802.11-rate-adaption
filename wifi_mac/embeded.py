import numpy as np
from gnuradio import gr
import pmt

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

    def handle_message(self, msg):
        metadata = pmt.car(msg)
        metadata_dict = pmt.to_python(metadata)
        frame_bytes = metadata_dict['frame bytes']
        print(frame_bytes)

        # calculate the throughput from frame_bytes

