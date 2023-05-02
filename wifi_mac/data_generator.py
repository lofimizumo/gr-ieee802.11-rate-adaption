import pickle
import socket
import time
import random
from threading import Thread
from buffer_lib import Buffer as buffer
import uwicore_mpif as plcp
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class UlBuffer:
    '''
    This class is used to create a buffer for upper layer traffic generator.
    the client class is used to handle multiple packet arrival (from PHY traffic generator or from MAC).
    '''
    def __init__(self, MACport=8001):
        self.MACport = MACport
        self.cs = buffer()
        self.cs2 = buffer()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((socket.gethostname(), self.MACport))
        self.server.listen(1)

    def run(self):
        while 1:
            socket_client, data_client = self.server.accept()
            thread = Client(socket_client, data_client, self.cs, self.cs2)
            thread.start()

class UlTraffic:
    '''
    This class is used to create a traffic generator for upper layer.
    it sends a packet to MAC layer every interval seconds.
    then it waits for interval seconds and sends another packet.
    the pickle library is used to serialize the packet.
    '''
    def __init__(self, MACport=8001, pkt_num=50, interval=0.05):
        self.MACport = MACport
        self.pkt_num = pkt_num
        self.interval = interval

    def run(self):
        while self.pkt_num > 0:
            self.pkt_num -= 1
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((socket.gethostname(), self.MACport))

            num = random.randint(0, 3)
            pkt = self.create_packet("PAYLOAD", f"TEST_{num + 1}")

            packet = pickle.dumps(pkt, 1)
            s.send(packet)
            s.close()
            time.sleep(self.interval)

    @staticmethod
    def create_packet(header, data):
        packet = {"HEADER": header, "DATA": data}
        return packet


class Client(Thread):
    """
    This class is used to handle multiple packet arrival (from PHY traffic generator or from MAC).
    """
    

    def __init__(self, socket_client, data_client, cs, cs2, print_buffer=False):
        Thread.__init__(self)
        self.socket = socket_client
        self.data = data_client
        self.cs = cs
        self.cs2 = cs2
        self.print_buffer = print_buffer

    def run(self):
        BUFFER_FULL_RESPONSE = b"BUFFER_FULL"
        pkt = self.socket.recv(1000)
        arrived_packet = pickle.loads(pkt)

        if "no_packet" == arrived_packet["HEADER"]:
            if self.cs.isEmpty():
                x = plcp.create_packet("NO", "")
                plcp.send_to_mac(self.socket, x)
                return

            self.cs.elements.reverse()
            if self.cs.read(0) == "[beacon packet]":
                x = plcp.create_packet("BEACON", "")
                logging.info("Buffer has BEACON to send.")
            else:
                x = plcp.create_packet("YES", self.cs.read(0))
                logging.info("Buffer has a DATA to send.")
            self.cs.elements.reverse()
            plcp.send_to_mac(self.socket, x)

            return

        if "remove" == arrived_packet["HEADER"]:
            logging.info("Upper buffer is set to remove a packet.")
            self.cs.elements.pop()

        elif "copy" == arrived_packet["HEADER"]:
            self.cs2.push(arrived_packet["DATA"])

        elif arrived_packet["HEADER"] == "PAYLOAD":
            self.cs.push(arrived_packet["DATA"])

        elif "BEACON" == arrived_packet["HEADER"]:
            logging.info("Buffer receives a BEACON from upper layer.")
            self.cs.push(arrived_packet["DATA"])

        if self.print_buffer:
            logging.info("== Statistics %s ==", time.time())
            logging.info("========== TX Buffer ============")
            logging.info(self.cs.elements)
            logging.info("========== RX Buffer ============")
            logging.info(self.cs2.elements)
        else:
            logging.info("TX [%d], RX [%d]", self.cs.length(), self.cs2.length())



def run_ul_buffer():
    ul_buffer = UlBuffer()
    ul_buffer.run()

def run_ul_traffic():
    ul_traffic = UlTraffic()
    ul_traffic.run()
