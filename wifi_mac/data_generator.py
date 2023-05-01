import pickle
import socket
import time
from threading import Thread

from buffer_lib import Buffer as buffer

class UlBuffer:
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
            threadd = Client(socket_client, data_client, self.cs, self.cs2)
            threadd.start()


class Client(Thread):
    def __init__(self, socket_client, data_client, cs, cs2):
        Thread.__init__(self)
        self.socket = socket_client
        self.data = data_client
        self.cs = cs
        self.cs2 = cs2

    def run(self):
        # (Same content as original run() method)


if __name__ == '__main__':
    try:
        ul_buffer = UlBuffer()
        ul_buffer.run()
    except KeyboardInterrupt:
        pass
