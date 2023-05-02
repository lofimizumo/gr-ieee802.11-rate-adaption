import threading
import yaml
import time
from optparse import OptionParser
from gnuradio.eng_option import eng_option
import uwicore_mac_utils as mac
from RateAdapt import MinstrelController, AarfController

def load_config(config_file):
    with open(config_file, 'r') as file:
        config = yaml.safe_load(file)
    return config

def print_msg(msg, node, log=True):
    """
    Print debug info
    :param msg: message to print
    :param node: node ID as prefix
    :param log: print flag
    :return: none
    """
    if log:
        print("[%d] %s" % (node, msg))

class MacWifi(threading.Thread):
    def __init__(self, options):
        threading.Thread.__init__(self)
        self.options = options
        self.options['time_slot'] = float(self.options['time_slot'])
        self.options['SIFS'] = float(self.options['SIFS'])

    def run(self):
    # log info
        print_state_trans = False  # print state transitions
        print_chan_sense = False  # print channel states after CSMA
        print_data = True  # print TX/RX data
        print_rate = True  # print rate adaptation results

        # Set socket ports
        phy_port = self.options['PHYport']  # Socket talks to PHY layer
        mac_port = self.options['MACport']  # Socket talks to upper layer (buffer)

        # Obtain node id from PHY server
        reply_phy, node = mac.read_phy_response(phy_port, "NODE")
        assert reply_phy == "YES", "[%d] Can't get node ID" % node

        # Configure local and destination MAC address according to the Node ID
        assert node != self.options['dest_node'], "[%d] Destination node ID can't be set to itself's" % node
        my_mac = mac.assign_mac(node)  # MAC address for this node
        dest_mac = mac.assign_mac(self.options['dest_node'])  # Destination address of upper layer packets

        # Obtain sample rate from PHY server
        reply_phy, samp_rate = mac.read_phy_response(phy_port, "SAMP_RATE")
        assert reply_phy == "YES", "[%d] Can't get sample rate" % node

        t_sym = mac.cal_sym_duration(samp_rate)  # calculate OFDM symbol duration

        retx_max = self.options['retx_max']  # maximum number of retransmission

        encoding = self.options['encoding']  # data rate for DATA frames
        encoding_ctrl_frame = 0  # use the lowest data rate to transmit control frames such as ACK, RTS, CTS

        # Timing parameters
        beta = self.options['beta']  # scaling time parameter
        tslot = self.options['time_slot'] * beta
        SIFS = self.options['SIFS'] * beta
        DIFS = SIFS + 2 * tslot
        Preamble = DIFS  # 16e-6
        PLCP_header = 4e-6 * beta
        ACK_time = Preamble + PLCP_header
        CW_min = 15
        CW_max = 1023
        RTS_THRESHOLD = 150
        dot11FragmentationTh = 1036

        # TX time estimation for a CTS and an ACK packet
        empty_values = {"duration": 0, "mac_ra": my_mac, "timestamp": time.time()}
        CTS_empty = mac.generate_pkt("CTS", t_sym, encoding_ctrl_frame, empty_values)
        T_cts = CTS_empty["INFO"]["tx_time"]
        ACK_empty = mac.generate_pkt("ACK", t_sym, encoding_ctrl_frame, empty_values)
        T_ack = ACK_empty["INFO"]["tx_time"]
        empty_values = {"payload": "x" * 2034, "address1": dest_mac, "address2": my_mac, "N_SEQ": 0, "N_FRAG": 0,
                        "timestamp": 0}
        DATA_empty = mac.generate_pkt("DATA", t_sym, 0, empty_values)
        T_data_max = DATA_empty["INFO"]["tx_time"]  # maximum transmission time

        # ACK Timeout = 2 * Air Propagation Time (max) + SIFS + Time to transmit 14 byte ACK frame [14*8 / bitrate in Mbps]
        air_delay_max = 200 / 299792458  # 20 meters / speed of light

        # Consider increase processing_delay if the generated ack from RX can't be captured within the timeout window
        processing_delay = 0.2  # data processing delay
        t_ack_timeout = (T_data_max + T_ack) * 1e-6 + SIFS + 2 * air_delay_max + processing_delay

        print_msg("ACK_time (s):%f, T_ack (s):%f" % (ACK_time, T_ack * 1e-6), node)
        print_msg("T_data_max (s):%f" % (T_data_max * 1e-6), node)
        print_msg("air_delay_max (s):%f" % air_delay_max, node)

        # Variables involving MAC tests
        t_csense = 0  # CS time

        state = "IDLE"  # MAC state

        # Initial Conditions of the Finite State Machine
        NAV = 0  # Network Allocation Vector
        busy_in_wfd = False  # Busy in Wait_for_DIFS state
        BO_frozen = "NO"  # Backoff frozen
        TX_attempts = 0  # Tries to send a packet counter
        CTS_failed = False  # CTS reception failed
        chan = "FREE"  # Channel state = IDDLE
        N_SEQ = 0  # Sequence number counter
        N_FRAG = 0  # Fragment number counter
        first_tx = True  # Is the first attempt to send a packet?
        frag_count = 0  # Counter used during fragmentation
        data_temp_reass = ""  # Initial variable to perform de re-assembly process
        beaconing = False  # Is ON the Beaconing process?
        fragmenting = 0  # Is the packet received a fragment?

        timing_error = "[%d] Timing Error. Please increase the beta parameter." % node

        print_msg("=============================================", node)
        print_msg(" \t  MAC layer: DCF + RTS/CTS", node)
        print_msg("=============================================", node)
        print_msg("Node %d - %s" % (node, mac.format_mac(my_mac)), node)
        print_msg("Target Node %d - %s" % (self.options['dest_node'], mac.format_mac(dest_mac)), node)
        print_msg("Rate: %d" % encoding, node)
        if retx_max != 0:
            print_msg("Retransmissions: Enabled (Maximum retries: %d)" % retx_max, node)
        else:
            print_msg("Retransmissions: Disabled", node)
        print_msg("Scaling time parameter: %d" % beta, node)
        print_msg("tslot(s): %f \t SIFS(s): %f" % (tslot, SIFS), node)
        print_msg("DIFS(s): %f \t T_ACK(s): %f" % (DIFS, ACK_time), node)
        print_msg("ACK Timeout (s): %f" % t_ack_timeout, node)
        print_msg("pseudo-random exp. BACKOFF [%i,%i]" % (CW_min, CW_max), node)
        if self.options['RTS']:
            print_msg("RTS/CTS: Dnabled", node)
            print_msg("\t with RTS Threshold(Bytes): %i" % RTS_THRESHOLD, node)
        else:
            print_msg("RTS/CTS: Disabled", node)
        print_msg("Fragmentation Threshold (Bytes):%i" % dot11FragmentationTh, node)
        print_msg("=============================================", node)
        """
        Starts the MAC operation
            1. AARF, using int data_sel(int rate, bool success) to update the data rate
            2. MINSTREL, using int data_sel(int rate, bool success)
        """

        rate_control = self.options['rate_control'].lower()
        assert rate_control in ["none", "minstrel", "aarf"], "Invalid rate adaptation setting"
        rate_control_enabled = rate_control != "none"

        if rate_control_enabled:
            if rate_control == "minstrel":
                assert retx_max != 0, "To use Minstrel adaptation, retransmission must be enabled"
                R = MinstrelController(encoding, retx_max)
            elif rate_control == "aarf":
                R = AarfController(self.options['encoding'], 8)  # encoding_init, n_data_rates=8, aarf_n=8

        while True:

            if state == "IDLE":
                reply_phy1, rts_pkt = mac.read_phy_response(phy_port, "RTS")
                if reply_phy1 == "YES":  # RTS received
                    if my_mac == rts_pkt["RX_add"]:
                        print_msg("[R]-[RTS]-[DA:%s]-[SA:%s]-[duration:%f]-[IFM:1]" % (
                            mac.format_mac(rts_pkt["RX_add"]), mac.format_mac(rts_pkt["TX_add"]), rts_pkt["tx_time"]),
                                node, print_data)
                        dest_mac = rts_pkt["TX_add"]  # Receiver Address of the CTS frame
                        print_msg("Dest MAC is %s ......" % dest_mac, node)
                        RTS_duration = rts_pkt["tx_time"]  # Value of RTS' TX time
                        print_msg("RTS duration is %s......" % RTS_duration, node)
                        """
                        #============================================================
                        # /TEST/ UNCOMMENT TO CHECK RTS/CTS FUNCTIONALITY
                        #============================================================
                        # STEP 1/4: Node 1 --> RTS
                        values = {"duration":pkt_phy1["tx_time"], "mac_ra":pkt_phy1["RX_add"], "mac_ta":pkt_phy1["TX_add"], 
                        "timestamp":time.time()}
                        RTS_forced = mac.generate_pkt("RTS", t_sym, encoding_ctrl_frame, values)
                        packet_RTS_forced = mac.create_packet("PKT", RTS_forced)
                        mac.send_wo_response(packet_RTS_forced, phy_port)
                        time.sleep(tslot)
                        #============================================================
                        """
                        state = "TRANSMITTING_CTS"
                        print_msg("| IDLE | RTS received | %s |" % state, node, print_state_trans)
                    else:
                        print_msg("[R]-[RTS]-[DA:%s]-[SA:%s]-[duration:%f]-[IFM:0]" % (
                            mac.format_mac(rts_pkt["RX_add"]), mac.format_mac(rts_pkt["TX_add"]), rts_pkt["tx_time"]),
                                node, print_data)
                        sleep_time = rts_pkt["tx_time"] / (1.0e3)  # Divided by 1e3 because tx_time is on milliseconds
                        NAV = mac.update_nav(time.time(), sleep_time, tslot)
                        print_msg("| IDLE | RTS captured (update NAV) | %s |" % state, node, print_state_trans)

                else:  # RTS is not received
                    reply_phy3, data_pkt = mac.read_phy_response(phy_port, "DATA")  # Check if DATA frame received
                    if reply_phy3 == "YES":
                        WF_DATA_first_time = 1
                        state = "TRANSMITTING_ACK"
                        ack_addr = data_pkt["mac_add2"]  # address to respond
                        print_msg("[R]-[DATA]-[DA:%s]-[SA:%s]-[MF:0]-[Seq#:%i]-[""%s""]" % (
                            mac.format_mac(data_pkt["mac_add1"]), mac.format_mac(data_pkt["mac_add2"]), data_pkt["N_SEQ"],
                            data_pkt["PAYLOAD"]), node, print_data)
                        print_msg("| IDLE | DATA received | %s |" % state, node, print_state_trans)
                        mac.send_ul_buff_packet(mac_port, data_pkt["packet"][24:])
                    else:  # Check upper layer buffer for data to send
                        reply_up, PAYLOAD = mac.read_ul_buffer(mac_port)
                        if reply_up == "YES":
                            state = "WAIT_FOR_NAV"
                            print_msg("| IDLE | MAC has DATA to Tx | %s |" % state, node, print_state_trans)
                        elif reply_up == "BEACON":
                            beaconing = True
                            state = "TRANSMITTING_RTS"
                            print_msg("| IDLE | Transmit BEACON FRAME | WAIT_FOR_NAV |", node, print_state_trans)
                        elif reply_up == "NO":
                            # is a CTS?
                            reply_phy2, cts_pkt = mac.read_phy_response(phy_port, "CTS")
                            if reply_phy2 == "YES":
                                tiempo = cts_pkt["tx_time"] / 1.0e3
                                state = "IDLE"
                                print_msg("[R]-[CTS]-[DA:%s]-[duration:%f]-[IFM:0]" % (
                                    mac.format_mac(cts_pkt["RX_add"]), cts_pkt["txtime"]), node, print_data)
                                print_msg("| IDLE | CTS captured (update NAV) | %s |" % state, node, print_state_trans)
                                NAV = mac.update_nav(time.time(), tiempo, tslot)

                if state == "IDLE":
                    time.sleep(tslot)  # Time-slotted MAC
                    print_msg("=> %s (%s)" % (state, time.time()), node, False)

            elif state == "WAIT_FOR_NAV":
                NAV = mac.update_nav(time.time(), NAV, tslot)
                if NAV > 0:
                    print_msg("| WAIT_FOR_NAV | NAV > 0 | WAIT_FOR_NAV |", node, False)
                    continue

                # NAV = 0
                state = "WAIT_FOR_DIFS"
                print_msg("| WAIT_FOR_NAV | NAV = 0 | %s |" % state, node, print_state_trans)
                chan = "FREE"

            elif state == "WAIT_FOR_DIFS":
                # This state performs the channel sensing process and decides whether the channel is BUSY or IDLE
                t_inicial = time.time()
                t_final = t_inicial + DIFS
                n_sensing = 0

                while n_sensing < 2:
                    t_testB = time.time()
                    channel_status, t, sig_power = mac.sense_channel(phy_port)
                    print_msg("Channel is %s (%5.2f dBw)......" % (channel_status, sig_power), node, print_chan_sense)
                    t_testC = time.time()
                    assert (tslot - (t_testC - t_testB) >= 0), timing_error
                    time.sleep(tslot - (t_testC - t_testB))
                    if channel_status == "OCCUPIED":
                        chan = "OCCUPIED"
                    t_csense = t_csense + (t_testC - t_testB)
                    n_sensing += 1
                assert (t_final - time.time() >= 0), timing_error
                time.sleep(t_final - time.time())
                t_csense = t_csense / 3

                if chan == "FREE":
                    if BO_frozen == "NO" and busy_in_wfd is False and CTS_failed is False:
                        BACKOFF = 0  # Channel IDLE for the first time, BOtimer = 0
                    state = "BACKING_OFF"
                    print_msg("| WAIT_FOR_DIFS | Channel idle | %s |" % state, node, print_state_trans)
                else:
                    if BO_frozen == "NO" and CTS_failed is False:  # If it is the 1st time, set the CW
                        BACKOFF = mac.retry(TX_attempts, CW_min)
                        print_msg("Backoff window is...... %d" % BACKOFF, node)
                        TX_attempts = TX_attempts + 1
                    state = "IDLE"
                    chan = "FREE"
                    print_msg("| WAIT_FOR_DIFS | Channel busy | %s |" % state, node, print_state_trans)

            elif state == "BACKING_OFF":
                busy_in_wfd = False

                if BACKOFF == 0:
                    state = "TRANSMITTING_RTS"
                    print_msg("| BACKING_OFF | Channel idle (CW = %i) | %s |" % (BACKOFF, state), node, print_state_trans)
                    continue

                tx = time.time()
                channel_status, t, sig_power = mac.sense_channel(phy_port)
                print_msg("Channel is %s (%5.2f dBw)......" % (channel_status, sig_power), node, print_chan_sense)
                BACKOFF = BACKOFF - 1
                if channel_status == "FREE":  # Channel idle
                    if BACKOFF == 0:
                        state = "TRANSMITTING_RTS"
                        busy_in_wfd = False

                else:  # Channel busy
                    BO_frozen = "YES"
                    state = "IDLE"

                print_msg("| BACKING_OFF | Channel busy (CW = %i) | %s |" % (BACKOFF, state), node, print_state_trans)
                ty = time.time()
                assert (tslot - (ty - tx) >= 0), timing_error
                time.sleep(tslot - (ty - tx))

            elif state == "TRANSMITTING_RTS":

                if beaconing:  # Transmit a Beacon frame
                    values = {"address2": my_mac, "N_SEQ": N_SEQ, "N_FRAG": 0, "BI": self.options['BI'], "timestamp": time.time()}
                    print_msg("[T]-[BEACON]-[SA:%s]-[BI=%f]-[Seq#:%i]" % (mac.format_mac(my_mac), self.options['BI'], N_SEQ),
                            node, print_data)

                    state = "IDLE"
                    print_msg("| TRANSMITTING_RTS | Send BEACON | %s |" % state, node, print_state_trans)
                    BEACON = mac.generate_pkt("BEACON", t_sym, encoding, values)
                    packet_BEACON = mac.create_packet("PKT", BEACON)
                    mac.send_wo_response(packet_BEACON, phy_port)
                    mac.remove_ul_buff_packet(mac_port)
                    N_SEQ = mac.next_seq_num(N_SEQ)
                    beaconing = False

                    continue

                # MAC has DATA frame to send
                if self.options['RTS']:  # RTS is enabled
                    values = {"payload": PAYLOAD, "address1": dest_mac, "address2": my_mac, "N_SEQ": N_SEQ,
                            "N_FRAG": N_FRAG, "timestamp": time.time()}
                    packet = mac.generate_pkt("DATA", t_sym, encoding, values)
                    T_data = packet["INFO"]["tx_time"]

                    if PAYLOAD > RTS_THRESHOLD:
                        if first_tx:
                            retx_retries = retx_max
                            fail_tx = False
                        first_tx = False
                        duration = (3 * SIFS) + (T_cts + T_ack + T_data) / 1000  # Txtime in milliseconds
                        mac_ra = dest_mac
                        mac_ta = my_mac
                        values = {"duration": duration, "mac_ra": mac_ra, "mac_ta": mac_ta, "timestamp": time.time()}
                        RTS = mac.generate_pkt("RTS", t_sym, encoding_ctrl_frame, values)
                        packet_RTS = mac.create_packet("PKT", RTS)
                        mac.send_wo_response(packet_RTS, phy_port)
                        state = "WAITING_FOR_CTS"
                        print_msg("| TRANSMITTING_RTS | (PAYLOAD > RTS_Th) Send RTS | %s |" % state, node,
                                print_state_trans)
                        print_msg("[T]-[RTS]-[SA:%s]-[DA=%s]-[duration:%i]" % (
                            mac.format_mac(my_mac), mac.format_mac(mac_ta), duration), node, print_data)

                        WFC_first_time = 1  # First time in WAITING_FOR_CTS state
                    else:
                        if first_tx:
                            retx_retries = retx_max
                            fail_tx = False
                        first_tx = False
                        state = "TRANSMITTING_UNICAST"
                        print_msg("| TRANSMITTING_RTS | (PAYLOAD < RTS_Th) Send DATA | %s |" % state, node,
                                print_state_trans)

                else:  # RTS is disabled
                    if first_tx:
                        retx_retries = retx_max
                        fail_tx = False
                        first_tx = False
                    state = "TRANSMITTING_UNICAST"
                    print_msg("| TRANSMITTING_RTS | (RTS OFF) Send DATA | %s |" % state, node, print_state_trans)

            elif state == "TRANSMITTING_UNICAST":
                '''
                Send packet to PHY for its transmission using the USRP2
                packet = [MPDU][LENGHT][INFO]
                pkt = [Header: PKT][Data: packet]
                '''
                if len(PAYLOAD) > dot11FragmentationTh:
                    state = "TRANSMITTING_FRAGMENTED_PACKET"
                    print_msg("| TRANSMITTING_UNICAST | Send Fragmented Data | %s |" % state, node, print_state_trans)
                    first_time_fg = True
                    WF_ACK_FG_first_time = True
                else:
                    values = {"payload": PAYLOAD, "address1": dest_mac, "address2": my_mac, "N_SEQ": N_SEQ,
                            "N_FRAG": N_FRAG, "timestamp": time.time()}
                    state = "WAITING_FOR_ACK"

                    if not fail_tx:
                        packet = mac.generate_pkt("DATA", t_sym, encoding, values)
                        tx_type = "Send"
                    else:
                        packet = mac.generate_pkt("DATA_RETX", t_sym, encoding, values)
                        tx_type = "Resend"

                    print_msg("| TRANSMITTING_UNICAST | %s DATA | %s |" % (tx_type, state), node, print_state_trans)
                    print_msg("[T]-[DATA]-[DA:%s]-[SA:%s]-[MF:0]-[Seq#:%i]-[""%s""]%s" % (
                        mac.format_mac(dest_mac), mac.format_mac(my_mac), N_SEQ, PAYLOAD,
                        "-[RETX]" if tx_type == "Resend" else ""), node, print_data)

                    N_SEQ = mac.next_seq_num(N_SEQ)
                    N_FRAG = 0

                    pkt = mac.create_packet("PKT", packet)
                    mac.send_wo_response(pkt, phy_port)
                    WF_ACK_first_time = True  # First time in WAITING_FOR_ACK state

            # WAITING_FOR_CTS STATE
            elif state == "WAITING_FOR_CTS":
                if WFC_first_time == 1:
                    CTS_time = SIFS
                    CTS_fin = 0
                t0 = time.time()
                no_packet, cts_pkt = mac.read_phy_response(phy_port, "CTS")

                '''
                #============================================================
                # /TEST/ UNCOMMENT TO CHECK RTS/CTS FUNCTIONALITY
                #============================================================
                # STEP 2/4: Node 2 --> CTS
                mac_ra = my_mac
                values = {"duration":0, "mac_ra":mac_ra,"timestamp":time.time()}
                CTS_forced = mac.generate_pkt("CTS", t_sym, encoding_ctrl_frame, values)
                packet_CTS_forced = mac.create_packet("PKT", CTS_forced)
                mac.send_wo_response(packet_CTS_forced, phy_port)
                time.sleep(tslot)
                #============================================================
                '''
                if no_packet == "YES":
                    # Is the CTS frame for this station?
                    if cts_pkt["RX_add"] == my_mac:
                        WFC_first_time = 1
                        state = "TRANSMITTING_UNICAST"
                        CTS_fin = 1
                        TX_attempts = 0
                        CTS_failed = False
                        print_msg("| WAITING_FOR_CTS | CTS received | %s |" % state, node, print_state_trans)
                        print_msg("[R]-[CTS]-[RA: %s]-[duration: %f]-[IFM:1]" % (
                            mac.format_mac(cts_pkt["RX_add"]), cts_pkt["tx_time"]), node, print_data)
                    else:
                        CTS_fin = 1  # CTS captured! Transmission aborted to avoid a collision
                        print_msg("[R]-[CTS]-[RA:%s]-[duration:%f]-[IFM:0]" % (
                            mac.format_mac(cts_pkt["RX_add"]), cts_pkt["tx_time"]), node, print_data)
                        state = "IDLE"
                        nuevo_NAV = cts_pkt["tx_time"] / 1e3
                        NAV = mac.update_nav(time.time(), nuevo_NAV, tslot)
                        print_msg("| WAITING_FOR_CTS | CTS captured (Update NAV = %f) | %s |" % (NAV, state),
                                node, print_state_trans)

                else:
                    state = "WAITING_FOR_CTS"
                    WFC_first_time = 0
                    # CTS_fin = 0

                t1 = time.time()
                CTS_time = CTS_time - (t1 - t0)

                if CTS_fin == 0:
                    if CTS_time > 0:
                        state = "WAITING_FOR_CTS"
                    else:
                        TX_attempts = TX_attempts + 1
                        BACKOFF = mac.retry(TX_attempts, CW_min)
                        state = "IDLE"  # Timer expired and CTS hasn't been received
                        print_msg("| WAITING_FOR_CTS | CTS not received | %s |" % state, node, print_state_trans)
                        CTS_failed = True

            elif state == "TRANSMITTING_FRAGMENTED_PACKET":
                if first_time_fg:
                    fragments = mac.fragment(PAYLOAD,
                                            dot11FragmentationTh)  # fragment PAYLOAD based on fragmentation threshold
                    first_time_fg = False
                    continue

                if len(fragments) > 1:
                    payload_tmp = fragments[0]
                    # Create packet with MORE FRAGMENT = 1 and payload = payload_tmp
                    values = {"payload": payload_tmp, "address1": dest_mac, "address2": my_mac, "N_SEQ": N_SEQ,
                            "N_FRAG": N_FRAG, "timestamp": time.time()}
                    packet = mac.generate_pkt("DATA_FRAG", t_sym, encoding, values)
                    N_SEQ += 1
                    N_FRAG += 1
                    pkt = mac.create_packet("PKT", packet)

                    state = "WAIT_ACK_FRAGMENTED"
                    print_msg("| TRANSMITTING_FRAGMENTED_PACKET | Send DATA FRAG | %s |" % state, node, print_state_trans)
                    print_msg("[T]-[FRAGMENTED DATA]-[DA:%s]-[SA:%s]-[MF:1]-[Seq#:%i]-[Frag#:%i]-[""%s""]" % (
                        mac.format_mac(dest_mac), mac.format_mac(my_mac), N_SEQ, N_FRAG, payload_tmp), node, print_data)
                    mac.send_wo_response(pkt, phy_port)
                    fragments.pop(0)  # FIXME Retransmission for Fragmented packets is required
                    fin_wait_ack_fragmented = False
                else:
                    payload_tmp = fragments[0]
                    # Create packet with MORE FRAGMENT = 0 and payload = payload_tmp
                    values = {"payload": payload_tmp, "address1": dest_mac, "address2": my_mac, "N_SEQ": N_SEQ,
                            "N_FRAG": N_FRAG, "timestamp": time.time()}
                    N_SEQ += 1
                    N_FRAG += 1
                    N_FRAG = 0
                    state = "WAIT_ACK_FRAGMENTED"
                    print_msg("| TRANSMITTING_FRAGMENTED_PACKET | Send DATA FRAG (last fragment) | %s |" % state,
                            node, print_state_trans)
                    print_msg("[T]-[DATA]-[DA:%s]-[SA:%s]-[MF:0]-[Seq#:%i]-[""%s""]" % (
                        mac.format_mac(dest_mac), mac.format_mac(my_mac), N_SEQ, payload_tmp), node, print_data)
                    packet = mac.generate_pkt("DATA", t_sym, encoding, values)
                    pkt = mac.create_packet("PKT", packet)
                    mac.send_wo_response(pkt, phy_port)
                    fin_wait_ack_fragmented = True

            elif state == "WAIT_ACK_FRAGMENTED":
                if WF_ACK_FG_first_time == 1:
                    T_ACK = SIFS
                ta1 = time.time()
                no_packet, cts_pkt = mac.read_phy_response(phy_port, "ACK")
                if no_packet == "YES":  # ACK addressed to this station
                    x = cts_pkt
                    print_msg("[R]-[ACK]-[DA:%s]-[IFM:1]" % mac.format_mac(x["RX_add"]), node, print_data)
                    if fin_wait_ack_fragmented:  # Last fragment sent
                        state = "IDLE"
                        print_msg("| WAIT_ACK_FRAGMENTED | All fragments acknowledged  | %s |" % state, node,
                                print_state_trans)
                        mac.remove_ul_buff_packet(mac_port)  # Remove the packet from upper layers
                        first_tx = True
                    else:
                        state = "TRANSMITTING_FRAGMENTED_PACKET"
                        print_msg("| WAIT_ACK_FRAGMENTED | ACK received | %s |" % state, node, print_state_trans)
                    BACKOFF = 0
                    WF_ACK_FG_first_time = 1
                    ACK_FG_fin = 1
                else:
                    state = "WAIT_ACK_FRAGMENTED"  # Not an ACK
                    WF_ACK_FG_first_time = 0
                    ACK_FG_fin = 0
                ta2 = time.time()

                assert (tslot - (ta2 - ta1) >= 0), timing_error
                time.sleep(tslot - (ta2 - ta1))
                tb = time.time()
                T_ACK = T_ACK - (tb - ta1)
                if ACK_FG_fin == 0:
                    if T_ACK > 0:
                        state = "WAIT_ACK_FRAGMENTED"
                        print_msg("| WAIT_ACK_FRAGMENTED | ACK not received yet | %s |" % state, node, print_state_trans)
                    else:
                        state = "IDLE"
                        print_msg("| WAIT_ACK_FRAGMENTED | ACK not received | %s |" % state, node, print_state_trans)
                        mac.remove_ul_buff_packet(mac_port)  # ACK not received within the Waiting_for_ack interval
                        first_tx = True

            elif state == "WAITING_FOR_ACK":
                if WF_ACK_first_time:
                    T_ACK = t_ack_timeout
                ta = time.time()
                no_packet, cts_pkt = mac.read_phy_response(phy_port, "ACK")
                if no_packet == "YES":
                    x = cts_pkt
                    print_msg("[R]-[ACK]-[DA:%s]-[IFM:1]" % mac.format_mac(x["RX_add"]), node, print_data)
                    '''
                    #============================================================
                    # /TEST/ UNCOMMENT TO CHECK RTS/CTS FUNCTIONALITY
                    #============================================================
                    # STEP 4/4: Node 2 --> ACK
                    mac_ra = my_mac
                    values = {"duration":x["tx_time"], "mac_ra":mac_ra,"timestamp":time.time()}
                    ACK_forced = mac.generate_pkt("ACK", t_sym, encoding_ctrl_frame, values)
                    packet_ACK_forced = mac.create_packet("PKT", ACK_forced)
                    mac.send_wo_response(packet_ACK_forced, phy_port)
                    time.sleep(tslot)
                    #============================================================
                    '''
                    state = "IDLE"
                    print_msg("| WAITING_FOR_ACK | ACK received | %s | (remove one packet from buffer)" % state,
                            node, print_state_trans)
                    BACKOFF = 0
                    WF_ACK_first_time = True
                    mac.remove_ul_buff_packet(mac_port)  # Packet acknowledged, remove from upper layers
                    first_tx = True
                    if rate_control_enabled:
                        encoding_prev = encoding
                        encoding = R.data_sel(encoding, True)
                        print_msg("Rate adaptation %d -> %d" % (encoding_prev, encoding), node, print_rate)

                else:
                    WF_ACK_first_time = False

                ta_fin = time.time()
                assert (tslot - (ta_fin - ta) >= 0), timing_error
                time.sleep(tslot - (ta_fin - ta))
                tb = time.time()
                T_ACK -= (tb - ta)

                if state == "IDLE":  # ACK is received
                    continue

                if T_ACK > 0:  # time window to receive ACK is not closed
                    state = "WAITING_FOR_ACK"
                    print_msg("| WAITING_FOR_ACK | ACK not received yet | %s |" % state, node, False)
                    continue

                # Doesn't received ACK during the time window, Reset CW to CWmin and go to IDLE
                state = "IDLE"
                if retx_max != 0:  # Retransmission is enabled
                    retx_retries -= 1
                    if retx_retries < 0:
                        CW = CW_min
                        mac.remove_ul_buff_packet(mac_port)
                        first_tx = True
                        print_msg("| WAITING_FOR_ACK | Remove packet from upper layers after retries | %s |" % state,
                                node, print_state_trans)
                        N_FRAG = 0
                        fail_tx = False

                    else:
                        print_msg("| WAITING_FOR_ACK | ACK not received (retries left = %i) | %s |" % (
                            retx_retries, state), node, print_state_trans)
                        fail_tx = True

                else:  # Retransmission is disabled
                    print_msg("| WAITING_FOR_ACK | Remove packet from upper layers (ReTX disabled) | %s |" % state,
                            node, print_state_trans)
                    mac.remove_ul_buff_packet(mac_port)  # No Re-TX!
                    first_tx = True

                if rate_control_enabled:  # Adjust the data rate
                    encoding_prev = encoding
                    encoding = R.data_sel(encoding, False)  # transmission fails
                    print_msg("Rate adaptation %d -> %d" % (encoding_prev, encoding), node, print_rate)

            elif state == "TRANSMITTING_CTS":
                '''
                RTS received. NAV allows channel access.
                Send CTS to PHY for its transmission.
                    - packet = [CTS][LENGHT][INFO]
                    - pkt = [Header: PKT][Data: packet]
                '''
                NAV = mac.update_nav(time.time(), NAV, tslot)
                if NAV > 0:
                    state = "TRANSMITTING_CTS"
                    print_msg("| TRANSMITTING_CTS | NAV > 0 | %s |" % state, node, print_state_trans)
                else:
                    duration = RTS_duration - (2 * T_cts) / 10 - SIFS
                    mac_ra = dest_mac
                    values = {"duration": duration, "mac_ra": mac_ra, "timestamp": time.time()}
                    CTS = mac.generate_pkt("CTS", t_sym, encoding_ctrl_frame, values)
                    packet_CTS = mac.create_packet("PKT", CTS)
                    state = "WAITING_FOR_DATA"
                    print_msg("| TRANSMITTING_CTS | CTS sent | %s |" % state, node, print_state_trans)
                    print_msg("[T]-[CTS]-[DA:%s]-[duration=%f]" % (mac.format_mac(mac_ra), duration), node, print_data)
                    mac.send_wo_response(packet_CTS, phy_port)
                    WF_DATA_first_time = 1

            elif state == "WAITING_FOR_DATA":
                '''
                Once the CTS is transmitted, wait for Data arrival
                    -> If a data packet arrives, go to TRANSMITTING_ACK
                    -> If no, go to IDLE
                '''
                if WF_DATA_first_time == 1:
                    T_DATA = SIFS
                t_1 = time.time()
                no_packet, cts_pkt = mac.read_phy_response(phy_port, "DATA")
                if no_packet == "YES":
                    x = cts_pkt  # DATA packet addressed to this station
                    '''
                    #============================================================
                    # /TEST/ UNCOMMENT TO CHECK RTS/CTS FUNCTIONALITY
                    #============================================================
                    # STEP 3/4: Node 1 --> DATA
                    values = {"payload":"Paquete_que_llega12", "address1":x["mac_add1"], "address2":x["mac_add2"], "N_SEQ":N_SEQ, "N_FRAG":0, "timestamp":time.time()}
                    DATA_forced = mac.generate_pkt("DATA", t_sym, encoding, values)
                    packet_DATA_forced = mac.create_packet("PKT", DATA_forced)
                    mac.send_wo_response(packet_DATA_forced, phy_port)
                    time.sleep(2*tslot)
                    #============================================================
                    '''
                    ack_addr = x["mac_add2"]
                    if x["MF"] == 0:  # More Fragments = 0
                        if fragmenting == 0:  # Not a fragmented packet
                            state = "TRANSMITTING_ACK"
                            print_msg("| WAITING_FOR_DATA | DATA received | %s |" % state, node, print_state_trans)
                            print_msg("[R]-[DATA]-[DA:%s]-[SA:%s]-[MF:0]-[IFM:1]-[""%s""]" % (
                                mac.format_mac(x["mac_add1"]), mac.format_mac(x["mac_add2"]), x["PAYLOAD"]), node,
                                    print_data)

                            WF_DATA_first_time = 1
                            DATA_ok = 1
                            frag_count = 0
                            mac.send_ul_buff_packet(mac_port, x["PAYLOAD"])
                        else:  # Last fragmented packet
                            fragmenting = 0
                            frag_count += 1
                            print_msg(
                                "[R]-[FRAGMENTED DATA]-[DA:%s]-[SA:%s]-[MF:0]-[Seq#:%i]-[Frag#:%i]-[IFM:1]-[""%s""]" % (
                                    mac.format_mac(x["mac_add2"]), mac.format_mac(my_mac), x["N_SEQ"], x["N_FRAG"],
                                    x["PAYLOAD"]), node, print_data)
                            test_seq = x["N_FRAG"] + 1 - frag_count
                            if test_seq == 0:
                                dato_leido = data_temp_reass + x["PAYLOAD"]
                                state = "TRANSMITTING_ACK"
                                print_msg("| WAITING_FOR_DATA | DATA_FRAG received  (MF = 0)| %s |" % state,
                                        node, print_state_trans)
                                WF_DATA_first_time = 1
                                frag_count = 0
                                DATA_ok = 1
                                fragmenting = 0
                                mac.send_ul_buff_packet(mac_port, dato_leido)
                            else:
                                state = "IDLE"  # TODO: state mismatch
                                print_msg(
                                    "| WAITING_FOR_DATA | Error: one or more fragments not received | TRANSMITTING_ACK |",
                                    node, print_state_trans)
                                WF_DATA_first_time = 1
                                DATA_ok = 0
                                frag_count = 0
                                fragmenting = 0
                    else:  # More Fragments = 1. It's a fragment
                        state = "TX_ACK_FG"  # TODO: state mismatch
                        print_msg("| WAITING_FOR_DATA | DATA_FRAG received  (MF = 1)| TRANSMITTING_ACK |",
                                node, print_state_trans)
                        print_msg("[R]-[FRAGMENTED DATA]-[DA:%s]-[SA:%s]-[MF:1]-[Seq#:%i]-[Frag#:%i]-[IFM:1]-[""%s""]" % (
                            mac.format_mac(x["mac_add2"]), mac.format_mac(my_mac), x["N_SEQ"], x["N_FRAG"], x["PAYLOAD"]),
                                node, print_data)

                        fragmenting = 1
                        frag_count += 1
                        DATA_ok = 1
                        data_temp_reass = data_temp_reass + x["PAYLOAD"]
                else:
                    DATA_ok = 0
                    state = "WAITING_FOR_DATA"  # Not a DATA packet
                    WF_DATA_first_time = 0
                tdiff = (time.time() - t_1)
                assert (tslot - tdiff >= 0), timing_error
                time.sleep(tslot - tdiff)
                T_DATA = T_DATA - (time.time() - t_1)
                if DATA_ok == 0:
                    if T_DATA > 0:
                        state = "WAITING_FOR_DATA"
                        print_msg("| WAITING_FOR_DATA | DATA not received yet | %s |" % state, node, print_state_trans)
                    else:
                        # DATA didn't arrive, go to IDLE
                        state = "IDLE"
                        print_msg("| WAITING_FOR_DATA | DATA not received  | %s |" % state, node, print_state_trans)
                        DATA_ok = 1

            elif state == "TX_ACK_FG":
                values = {"duration": 0, "mac_ra": ack_addr,
                        "timestamp": time.time()}  # ack_addr copied from the previous Data packet
                state = "WAITING_FOR_DATA"
                print_msg("| TX_ACK_FG | ACK sent | %s |" % state, node, print_state_trans)
                print_msg("[T]-[ACK]-[DA:%s]" % mac.format_mac(ack_addr), node, print_data)
                ACK = mac.generate_pkt("ACK", t_sym, encoding_ctrl_frame, values)
                packet_ACK = mac.create_packet("PKT", ACK)
                mac.send_wo_response(packet_ACK, phy_port)

            elif state == "TRANSMITTING_ACK":
                values = {"duration": 0, "mac_ra": ack_addr,
                        "timestamp": time.time()}  # ack_addr copied from the previous Data packet
                state = "IDLE"
                print_msg("| TRANSMITTING_ACK | ACK sent | %s |" % state, node, print_state_trans)
                print_msg("[T]-[ACK]-[DA:%s]" % mac.format_mac(ack_addr), node, print_data)
                ACK = mac.generate_pkt("ACK", t_sym, encoding_ctrl_frame, values)
                packet_ACK = mac.create_packet("PKT", ACK)
                mac.send_wo_response(packet_ACK, phy_port)
