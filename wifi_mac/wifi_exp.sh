#!/bin/bash

set -e  # terminate installation upon error occurs

# PHY parameters
PHYport=8013      # Socket No. of PHY
PHYRXport=8513    # Socket No. of PHY RX
localNodeId=1     # Local node
destNodeId=2      # Destination node
usrp_addr="192.168.10.2"    # 192.168.10.2

# Buffer parameters
MACport=8001      # Socket No. of upper layer (buffer)
n_pkt=100         # No. of pkt generated
t_interval=0.02   # Interval of pkt generation (s)

# MAC parameters
rate_control=aarf   # rate adaptation approach
                    # "none"
                    # "aarf"
                    # "minstrel"
encoding=0          # initial data rate
beta=1000           # scaling factor of timing
retx_max=4          # Maximum No. of retries

if [ "$rate_control" != none ] && [ "$rate_control" != "aarf" ] && [ "$rate_control" != "minstrel" ]
then
    echo "Wrong rate adaptation parameter: $rate_control"
    echo "Expected: none, aarf, minstrel"
    exit
fi

# Commands
buf_cmd="ul_buffer.py --MACport=$MACport"
tra_cmd="ul_traffic.py --MACport=$MACport -n $n_pkt -t $t_interval"

phy_cmd="phy_wifi.py -n $localNodeId --PHYport=$PHYport --PHYRXport=$PHYRXport"
if [ "$usrp_addr" != ""]
then
    phy_cmd = "$phy_cmd"-a $usrp_addri
fi
mac_cmd="mac_wifi.py --MACport=$MACport --PHYport=$PHYport --encoding=$encoding\
 --beta=$beta -r $retx_max -R $rate_control"

# Run commands
dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $dir
echo "Entering $PWD"

prefix="python "
# Commands
echo "============================"
echo "CMD 1: $buf_cmd"
echo "CMD 2: $tra_cmd"
echo "CMD 3: $phy_cmd"
echo "CMD 4: $mac_cmd"
echo "============================"


echo "Start PHY"
($prefix$phy_cmd) &
sleep 5

echo "Start buffer"
($prefix$buf_cmd) &
sleep 5

echo "Generate traffic"
$prefix$tra_cmd
echo "Traffic generated"
sleep 5

echo "Start MAC"
($prefix$mac_cmd) &

cd --

trap 'kill $BGPID; exit' SIGINT
sleep 1024 &    # background command
BGPID=$!
sleep 1024      # foreground command of the script
