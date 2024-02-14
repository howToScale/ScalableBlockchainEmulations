#!/usr/bin/env python3

import os
import shutil
import json
import time

from re import search,sub,findall,match
from sys import exit
from subprocess import run, PIPE, DEVNULL
from collections import defaultdict
from itertools import islice , groupby, repeat

from pathlib import Path

from numpy import loadtxt, sqrt, ceil


from multiprocessing import Pool, Lock


import networkx as nx
import matplotlib.pyplot as plt

import random
import yaml


from fileinput import FileInput


import docker
import code


BOOTSTATS_PATH = "run/bootStats.txt"
TC_BATCH_FILE_PATH = "run/tc_batch_file"
NFT_FILE_PATH = "run/nft_dir"
NFT_FILE_PREFIX = NFT_FILE_PATH+"/nft_"
TCP_RTO_FILE	= "bin/tcp-rto.c"
MATRIX_PATH     = "data/latencies.gz"
BUCKET_SIZE     = 10 # buckets are rounded each X milliseconds

BR_IFACES      = 'br-'+run('docker network ls --filter Name=lite-full_net --format {{.ID}}', shell=True, check=True, stdout=PIPE, text=True).stdout[:-1]


def init(l):
    global lock
    lock = l



client = docker.from_env()

machines = [elem['Command'] for elem in client.api.containers(trunc=True)]

Path("/var/run/netns").mkdir(exist_ok=True)



def machineNS(m):
	ID=search(r'bin/node\.py\s+(\d+)',m).group(1)
	pid=run(f"pgrep -f 'python3 bin/node.py {ID}'", shell=True, check=True, stdout=PIPE, text=True).stdout[:-1].split("\n")[0]
	os.symlink(f"/proc/{pid}/ns/net",f"/var/run/netns/{ID}")
	while not os.path.islink(f"/var/run/netns/{ID}"):
		time.sleep(0.5)



print(f"loading {len(machines)} containers information")
bootStatsInfo=f"number of Machine: {len(machines)}\n"


ts = time.time()
with Pool(processes=os.cpu_count()) as p:
	p.map(machineNS,machines)

detailsNodes=run(f"sudo ip --all netns exec ip a show eth0", shell=True, check=True, stdout=PIPE, text=True).stdout[:-1]
m=run(f"ip a", shell=True, check=True, stdout=PIPE, text=True).stdout[:-1]
detailsHostVeth=findall(r"veth.*@if[^:]*",m)


shutil.rmtree("/var/run/netns",ignore_errors=True)
nodesName=[f'"Name": "node_{x[7:]}"' for x in findall(r"netns: [0-9]+",detailsNodes)]
vethsIndexRAW=[x[:-6] for x in findall(r"[0-9]+: eth0",detailsNodes)]
vethsRAW=[f'"Veth": "{match(r"[^@]*",v).group()}"' for i in vethsIndexRAW for v in detailsHostVeth if match(rf".*if{i}",v) ]
vethsIndexRAW=[f'"Index": {x}' for x in vethsIndexRAW]
ipRAW=[f'"IP": "{x[5:]}"' for x in findall(r"inet[^/]*",detailsNodes)]
macRAW=[f'"MAC": "{x[6:]}"' for x in findall(r"ether [^ ]*",detailsNodes)]


detailsList=[json.loads("{"+", ".join(e)+"}") for e in zip(nodesName,vethsRAW,vethsIndexRAW,ipRAW,macRAW)]


tf = time.time()



print(f'time gathering Info start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time gathering Info fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')


######################## SET FDB BRIDGE #######################

print("set FDB configuration")

ts = time.time()
for c in detailsList:
	run(f"sudo bridge fdb add {c['MAC']} dev {c['Veth']} master static", shell=True, check=True)


tf = time.time()



print(f'time FDB start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time FDB fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')




######################## SET ROUTING TABLE FILE #######################

print("set Routing Table File")

ts = time.time()

with open("data/config.yml", "r") as yamlfile:
	dataConf = yaml.load(yamlfile, Loader=yaml.FullLoader)

with open("./run/nodesInfo.txt", "r") as n:
	nodesInfoJS = json.load(n)



SLOW_MULTIPLIER = dataConf["SLOW_MULTIPLIER"]


random.seed(dataConf["seed"])
randomizedNodes = random.sample(detailsList, len(detailsList))

nodes_mapping_table= {}
print("----SMALL-WORLD GRAPH")
#WATTS–STROGATZ SMALL-WORLD GRAPH (without rewiring only add)
randomNodesGRAPH = nx.newman_watts_strogatz_graph(len(detailsList), int(dataConf["network"]["routing_table_size"])//2, 0.5, dataConf["seed"])


for nodeIndex, nodeNeighbors in randomNodesGRAPH.adjacency():
	nodeNeighbors_indexes = list(nodeNeighbors.keys())
	neighbors = list(map(randomizedNodes.__getitem__,nodeNeighbors_indexes))
	n = [ng['IP'] for ng in neighbors ]
	nodes_mapping_table[randomizedNodes[nodeIndex]['IP']] = n
	with open(f"./run/{randomizedNodes[nodeIndex]['Name']}/beaconPeers.txt", "w") as bp:
		bp.write("\n".join(n))


tf = time.time()



print(f'time routingTable Info start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time routingTable Info fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')

maxETH1Connection = max(map(lambda x: len(x), nodes_mapping_table.values()))

tmp=f"""
P2P connections: {len(sum(nodes_mapping_table.values(), []))/2}
P2P maxconnection : {maxETH1Connection}

"""

print(tmp)
bootStatsInfo+=tmp



######################## SET SLOW FILES #######################



print("set Slow Files")

ts = time.time()
# === read table ===
matrix=loadtxt(MATRIX_PATH, usecols=range(len(randomizedNodes)), max_rows=len(randomizedNodes))




# === extract buckets ===
buckets = defaultdict(list)
for i in range(len(randomizedNodes)):
	for j in range(i+1):
		q_delay = int((matrix[i][j] // BUCKET_SIZE * BUCKET_SIZE) * SLOW_MULTIPLIER) 
		if q_delay > 0:
			buckets[q_delay].append((i,j))

buckets = dict(sorted(buckets.items()))



def delay_to_mark(lat):
	return list(buckets.keys()).index(lat) + 1



# === dump delay stats ===

n_qdisc = len(buckets)
n_pairs = sum((len(b) for b in buckets.values()))
max_delay_ms = list(buckets.keys())[-1]
max_delay_sec_ub = int(ceil(max_delay_ms/1000))
tmp=f"""
{"-"*30}
Slow Multiplier: {SLOW_MULTIPLIER}
Number of nodes: {len(randomizedNodes)}
Number of qdisc: {n_qdisc}
Max delay: {max_delay_ms} ms
Number of pairs (unordered): {n_pairs}
Avg number of pairs per qdisc: {n_pairs // n_qdisc}
{"-"*30}
"""

print(tmp)

bootStatsInfo+=tmp

Path(BOOTSTATS_PATH).unlink(missing_ok=True)

with open(BOOTSTATS_PATH,"w") as bf:
	bf.write(bootStatsInfo)






Path(TC_BATCH_FILE_PATH).unlink(missing_ok=True)


n_bends = int(ceil(sqrt(n_qdisc+1)))
n_bendsHex = hex(n_bends)[2:]

if n_bends > 16:
	print(f"Too many bends (max 16, needed {n_bends})")
	exit(1)

def queuingdisciplines(machine):
	veth = machine["Veth"]
	run(f"sudo ip link set dev {veth} txqueuelen 5000", shell=True)
	## root qdisc prio n bands 
	s=(f"qdisc add dev {veth} root handle 1: prio bands {n_bends}\n")
	## second layer of prio 
	for firstBends in range(1,n_bends+1):
		hband = hex(firstBends)[2:]
		s+=(f"qdisc add dev {veth} parent 1:{hband} handle 1{hband}: prio bands {n_bends}\n")



	## default class Filter

	s+=(f"filter add dev {veth} protocol all parent 1: prio 20 matchall classid 1:{n_bendsHex}\n")
	s+=(f"filter add dev {veth} protocol all parent 1{n_bendsHex}: prio 20 matchall classid 1{n_bendsHex}:{n_bendsHex}\n")


	## slower classes
	for delay in buckets.keys():
		mark  = delay_to_mark(delay)
		firstBands = ((mark - 1)//n_bends) + 1
		secondBands = ((mark - 1) % n_bends) + 1 

		hband1=hex(firstBands)[2:]
		hband2=hex(secondBands)[2:]


		### First filter
		s+=(f"filter add dev {veth} protocol ip parent 1: prio 10 handle {mark} fw classid 1:{hband1}\n")
		### Second Filter
		s+=(f"filter add dev {veth} protocol ip parent 1{hband1}: prio 10 handle {mark} fw classid 1{hband1}:{hband2}\n")
		
		s+=(f"qdisc add dev {veth} parent 1{hband1}:{hband2} netem delay {delay}ms\n")
	with lock:
		with open(TC_BATCH_FILE_PATH,'a+') as tcf:
			tcf.write(s)
		



l = Lock()

with Pool(processes=os.cpu_count(),initializer=init, initargs=(l,)) as p:
	p.map(queuingdisciplines,detailsList)



print("-- tc")


run(f"sudo tc -batch {TC_BATCH_FILE_PATH}", shell=True, stdout=PIPE,stderr=PIPE, text=True)

if os.path.exists(NFT_FILE_PATH):
	shutil.rmtree(NFT_FILE_PATH)

os.makedirs(NFT_FILE_PATH)



run("sudo nft add table ip latem ; sudo nft add chain latem latem_chain { type filter hook forward priority 0 \; }", shell=True, check=True)

number=0

nftf=open(NFT_FILE_PREFIX+"{}.txt".format(number),"a")
nftf.write("#!/usr/sbin/nft -f\n")

for delay in buckets.keys():
	nodes = set()
	mark = delay_to_mark(delay)
	
	for pair in buckets[delay]:
		ip_one = randomizedNodes[pair[0]]["IP"]
		ip_two = randomizedNodes[pair[1]]["IP"]
		nodes.add(f"{ip_one} . {ip_two}")
		nodes.add(f"{ip_two} . {ip_one}")
		


	nftf.write(f"add set latem nodes_{mark} {{ type ipv4_addr . ipv4_addr ; }}\n")
	iterall = iter(nodes)
	while True:
		some = islice(iterall, 1000)
		set_elements = ', '.join(some)
		if len(set_elements) == 0: break
		nftf.write(f"add element latem nodes_{mark} {{ {set_elements} }}\n")
		nftf.flush()
		if os.fstat(nftf.fileno()).st_size > 100000000:
			nftf.close()
			number+=1
			nftf=open(NFT_FILE_PREFIX+"{}.txt".format(number),"a")
			nftf.write("#!/usr/sbin/nft -f\n")
	nftf.write(f"add rule latem latem_chain ip saddr . ip daddr @nodes_{mark} meta mark set {mark}\n")


nftf.close()

print("-- nft")

for f in sorted(os.listdir(NFT_FILE_PATH)):
	run(f"sudo nft -f {NFT_FILE_PATH+'/'+f}", shell=True, check=True)


######################## SET TCP RTO #######################


print("set TCP RTO")

release=os.uname().release

hz=250

with open(f"/boot/config-{release}",'r') as bootConf:
	for line in bootConf:
		if('CONFIG_HZ=' in line):
			hz = line[10:-1]


with FileInput(TCP_RTO_FILE, inplace=True) as file:
	for line in file:
		if('const int timeout =' in line):
			print(sub(r"^ *const int timeout =.*", f"    const int timeout = {max_delay_sec_ub*2};",line), end='')
		elif('const int hz =' in line):
			print(sub(r"^ *const int hz =.*", f"    const int hz = {hz};",line), end='')
		else:
			print(line, end='')

run(f"./bin/unload.sh", shell=True, check=False)
run(f"./bin/load.sh", shell=True, check=True)



tf = time.time()



print(f'time Slow Info start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time Slow Info fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')


######################## SET config ETH Files#######################

def ip2Node(ipString):
	sp = ipString.split(".")
	return str(int(sp[-2])*100 + int(sp[-1]))

print("set ETH1")

ts = time.time()


ethConf=f"""
[Eth]
NetworkId = 2292
SyncMode = "full"

[Node]
IPCPath = "geth.ipc"
DataDir = "./"
HTTPHost = ""
HTTPPort = 8545
HTTPVirtualHosts = ["localhost"]
HTTPModules = ["net", "web3", "eth"]
AuthAddr = "localhost"
AuthPort = 8551


[Node.P2P]
MaxPeers = {maxETH1Connection}
NoDiscovery = true
DiscoveryV4 = false
BootstrapNodes = []
BootstrapNodesV5 = []
TrustedNodes = []
ListenAddr = ":{dataConf["network"]["defPort"]}"
"""


for n, neighbors in nodes_mapping_table.items():
	nodeID = ip2Node(n)
	nodesForConnection = ",".join(map(lambda x: f"\"enode://{nodesInfoJS[ip2Node(x)]['enode']}@{x}:{dataConf['network']['defPort']}\"", neighbors ))
	enodes = 'StaticNodes = ['
	enodes +=  nodesForConnection
	enodes += "]"
	with open(f"./run/node_{nodeID}/config.toml", "w") as ethConfToml:
		ethConfToml.write(ethConf+enodes)

tf = time.time()



print(f'time Config ETH1 start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time Config ETH1 fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')