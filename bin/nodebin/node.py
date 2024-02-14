#!/usr/bin/env python3

from signal import signal, pause, SIGUSR1, SIGUSR2
from functools import partial

from subprocess import run, Popen, DEVNULL
import sys
import json

import asyncio 
from numpy import random
from random import choice


run('./bin/autoarpd 02:42:ip1:ip2:ip3:ip4' , shell=True, check=True)


with open("./bin/nodesInfo.txt", "r") as n:
	otherNodes = json.load(n)
	myEntry = otherNodes.pop(sys.argv[1])
	otherNodes = {outer_key: tuple(inner_value for inner_key, inner_value in inner_dict.items() if inner_key in ('pk', 'beaconID')) for outer_key, inner_dict in otherNodes.items() }

#clean LOGS
open("./node.log", "w").close()
open("./beacon.log", "w").close()
open("./validator.log", "w").close()


gethStartCommand = f"geth --nodekey enode.key --unlock 0x{myEntry['pk']} --password psw.txt --log.file ./node.log --config config.toml --cache 2048 --log.rotate { '--miner.gasprice 0 --mine --miner.etherbase=0x'+myEntry['pk'] if myEntry['signer'] else ''}"

beaoconNodeCommand = f'''bin/beacon-chain --accept-terms-of-use \
--no-discovery \
--verbosity=info \
--datadir=./ \
--min-sync-peers=0 \
--force-clear-db \
--bootstrap-node= \
--genesis-state=./genesisPrysm.ssz \
--chain-config-file=./PrysmConfig.yml \
--chain-id=2292 \
--execution-endpoint=./geth.ipc \
--contract-deployment-block=0 \
--minimum-peers-per-subnet=0 \
--p2p-priv-key=./network-keys \
--suggested-fee-recipient=0x{myEntry['pk']} \
--log-file=./beacon.log'''

validatorCommand = f'''bin/validator --datadir=./ --accept-terms-of-use \
--verbosity=info \
--interop-num-validators=1 \
--interop-start-index={myEntry['validator']} \
--force-clear-db \
--chain-config-file=./PrysmConfig.yml \
--suggested-fee-recipient=0x{myEntry['pk']} \
--log-file=./validator.log'''

nodeStarted = False
nodeBeacon = False
nodeValidator = False


def start_node(signum, frame):
	print("SIGNAL")
	global nodeStarted, nodeBeacon, nodeValidator, beaoconNodeCommand
	if not nodeStarted:
		nodeStarted = True
		print("START")
		Popen(gethStartCommand, shell=True, stderr=DEVNULL)
	elif not nodeBeacon:
		print("beacon")
		nodeBeacon = True
		with open("./beaconPeers.txt","r") as bpf:
			for ipPeers in [line.rstrip() for line in bpf]:
				ipSplit = ipPeers.split('.')
				idNode = int(ipSplit[2])*100 + int(ipSplit[3])
				beaoconNodeCommand += f" --peer /ip4/{ipPeers}/tcp/13000/p2p/{otherNodes[str(idNode)][1]}"
		Popen(beaoconNodeCommand, shell=True, stderr=DEVNULL)
	elif myEntry['validator'] != -1  and not nodeValidator:
			print("validator")
			nodeValidator = True
			Popen(validatorCommand, shell=True, stderr=DEVNULL)





async def start_transaction_activity():
	while True:
		t_wait_time = random.exponential(float(sys.argv[2]))
		print(f"send transaction in {t_wait_time} sec")
		transaction = f"eth.sendTransaction({{to: \"0x{choice([v[0] for v in otherNodes.values()])}\", from: eth.accounts[0], value: 250}});"
		await asyncio.sleep(t_wait_time)
		Popen(f"geth --datadir ./ attach --exec '{transaction}' ", shell=True)
		print(f"send transaction")


try:
	loop = asyncio.get_event_loop()


	# register signals
	signal(SIGUSR1, start_node)
	loop.add_signal_handler(SIGUSR2, lambda: asyncio.create_task(start_transaction_activity()))

	loop.run_forever()
except KeyboardInterrupt:
	print("Exit.")
finally:
	loop.stop()
 



