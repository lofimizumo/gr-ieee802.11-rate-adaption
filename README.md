Greetings,

This project implements the complete IEEE802.11 protocol, including PHY, MAC, and rate adaptation approaches upon GNURadio/USRP software-defined radio platform. The project integrates the existing open-source projects (See literature [2,3]) and makes them a unity that works under the latest GNURadio platform. In addition, mainstream rate adaptation approaches Minstrel and Adaptive Auto Rate Fallback (AARF) are implemented. The rate adaptation module continuously collects the data transmission status, i.e, whether acknowledgement frames are received after data transmission, and decides the next data transmission rate to be used according to such statistics. The new data rate is then being transferred to the PHY module and applied in the subsequent frame encoding and modulation.
 
To use this project, please cite the following literatures:

[1] Implementation of rate adaptation approach and complete system integration

@inproceedings{lu2016scheduling,
  title={Scheduling Dynamic Wireless Networks with Limited Operations},
  author={Haoyang Lu and Wei Gao},
  booktitle={IEEE International Conference on Network Protocols},
  year={2016},
  organization={IEEE}
}

[2] The PHY implementation is based on (https://github.com/bastibl/gr-ieee802-11/)

@inproceedings{bloessl2013ieee,
  title={An IEEE 802.11 a/g/p OFDM Receiver for GNU Radio},
  author={Bloessl, Bastian and Segata, Michele and Sommer, Christoph and Dressler, Falko},
  booktitle={Proceedings of the second workshop on Software radio implementation forum},
  pages={9--16},
  year={2013},
  organization={ACM}
}

[3] The MAC implementation is based on (http://www.uwicore.umh.es/mhop-software.html)

@inproceedings{gutierrez2010ieee,
  title={An IEEE 802.11 MAC Software Defined Radio implementation for experimental wireless communications and networking research},
  author={Gutierrez-Agullo, Juan R and Coll-Perales, Baldomero and Gozalvez, Javier},
  booktitle={Wireless Days (WD), 2010 IFIP},
  pages={1--5},
  year={2010},
  organization={IEEE}
}

# Installation
Please go through [[2]](https://github.com/bastibl/gr-ieee802-11/) for installation and settings.

The software is tested on Ubuntu 16.04 and GNU Radio Companion 3.7.11.1. To check your GNURadio version, use

    gnuradio-companion --version
    
# Troubleshooting
- If you see ```ImportError: No module named wifi_phy_hier``` when running ```./phy_wifi.py```, open ```example\wifi_phy_hier.grc``` in GNURadio and generate the flow graph. You should be able to see ```wifi_phy_hier.py``` is generated under ```~/.grc_gnuradio/```.
- If you see ```return _fft_swig.fft_vcc_make(fft_size, forward, window, shift, nthreads) RuntimeError: std::exception``` when running ```./phy_wifi.py```, use ```sudo ./phy_wifi.py```

# Usage
1. Open a terminal and run
    ./ul_buffer.py
    
   This program stores the packets to be sent and those received into TX and RX buffers, respectively. ```mac_wifi.py``` continuously checks if the TX buffer is non-empty, i.e., there is packet to deliver, and stores the received packets into the RX buffer. The buffer sizes would be displayed once changed.
   
2. Open another terminal and run
    ./ul_traffic.py
    
   This program generates ```n``` packets every ```t``` seconds and sends them to the TX buffer in 1. For test purpose, the generated packets are ```TEST_k``` (k=1,2,3,4).
   Note: only run ```ul_traffic.py``` after the ```ul_buffer.py``` starts, as the latter is on the server side of the socket communication.

3. Open a new terminal and run
   ./phy_wifi.py
   
   This is the physical layer implementation, which is based on the hierarchical flow graph ```wifi_phy_hier.grc```. PHY sends valid received packets for MAC for further process, and takes care of the packet transmission.
   The simulated MAC address of the USRP node is decided by the node number, which can be specified using parameter ```-n```, e.g., ```./phy_wifi.py -n 1```.
   
4. Open a terminal and run
   ./mac_wifi.py
   
   This program simulates the MAC layer behaviors, such as Clear Channel Assessment (CCA), waiting for the ack. It will ask ```phy_wifi.py``` for node ID and delivers its packets to Node (node + 1), such as Node 1 -> Node 2 -> Node 3 ... So if you configure one USRP as Node 1 and another as Node 2, you would only receive ACK on Node 1, as all traffic on Node 2 targets Node 3. To allow bidirectional data transfer between Node 1 and Node 2, you can modify the ```dest_mac``` in the source code.
   
# Tricks
Use ```tmux``` to manage multiple terminals.

# Further information
If you have any further questions or suggestions, please feel free to contact
Haoyang Lu, (haoyanglu@pitt.edu)
University of Pittsburgh
