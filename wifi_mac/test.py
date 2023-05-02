import time
import threading
from data_generator import run_ul_buffer,run_ul_traffic
from mac import load_config, MacWifi
from phy_wifi import Phy

if __name__ == '__main__':
    buffer_thread = threading.Thread(target=run_ul_buffer)
    traffic_thread = threading.Thread(target=run_ul_traffic)
    buffer_thread.start()
    time.sleep(2)
    traffic_thread.start()
    
    # start PHY
    config_phy = "wifi_mac/phy_config.yaml"
    phy = Phy(load_config(config_phy))
    phy.start()

    # start MAC
    time.sleep(5)
    config_mac = "wifi_mac/mac_config.yaml"
    config = load_config(config_mac)
    mac_wifi_thread = MacWifi(config)
    mac_wifi_thread.start()
    mac_wifi_thread.join()
    buffer_thread.join()
    traffic_thread.join()
