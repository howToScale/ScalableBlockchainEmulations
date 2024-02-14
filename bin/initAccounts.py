#!/usr/bin/env python3

import sys
import os
import yaml
from subprocess import run
import concurrent.futures
import code
import time

if len(sys.argv) != 2:
	print("missing run dir")
	sys.exit()

ts = time.time()
with open("data/config.yml", "r") as yamlfile:
    dataConf = yaml.load(yamlfile, Loader=yaml.FullLoader)

nodes = dataConf["nodes"]
nodesCount = nodes["node_count"]

NODESDIRPREFIX = f"{sys.argv[1]}/node_"

nodeDirs = [f for f in os.listdir(sys.argv[1]) if (os.path.isdir(os.path.join(sys.argv[1], f)) and "node_" in f)]
nodesCountF = len(nodeDirs)
if nodesCountF != nodesCount:
	print("node count mismatch")
	exit(-1)
for d in nodeDirs:
	run(f"sudo rm -rf {sys.argv[1]}/{d}/geth {sys.argv[1]}/{d}/beaconchaindata", shell=True, check=True)
	run(f"sudo rm -f {sys.argv[1]}/{d}/validator.db", shell=True, check=True)

def init_geth(n):
	command = f"geth --datadir {NODESDIRPREFIX}{n} init {sys.argv[1]}/genesis.json"
	run(command, shell=True, check=True)

with concurrent.futures.ThreadPoolExecutor() as executor:
	futures = [executor.submit(init_geth,n ) for n in range(1, nodesCount + 1)]
	# Wait for all tasks to complete
	concurrent.futures.wait(futures)


tf = time.time()
print(f'time Init Account start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
print(f'time Init Account fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')