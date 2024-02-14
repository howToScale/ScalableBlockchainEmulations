#!/usr/bin/env python3

import sys
import os
import yaml
import random
import re
import code
import json
from subprocess import run, PIPE
import base58
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
import time
import concurrent.futures


if len(sys.argv) != 2:
	print("missing run dir")
	sys.exit()

with open("data/config.yml", "r") as yamlfile:
	dataConf = yaml.load(yamlfile, Loader=yaml.FullLoader)

nodes = dataConf["nodes"]
random.seed(dataConf["seed"])
nodesCount = nodes["node_count"]

NODESDIRPREFIX = f"{sys.argv[1]}/node_"


def staticBeaconKEY_ID():
	pemkey = run(f"openssl ecparam -genkey -name secp256k1 -noout", shell=True, check=True, stdout=PIPE).stdout
	private_key_bytes = run("openssl ec -inform PEM -outform DER ", input=pemkey, shell=True, check=True, stdout=PIPE).stdout[7:39]

	private_key = ec.derive_private_key(int.from_bytes(private_key_bytes, byteorder='big'), ec.SECP256K1(), default_backend())

	# Obtain the public key
	public_key = private_key.public_key()
	public_key_bytes = public_key.public_bytes(
				encoding=serialization.Encoding.X962,
				format=serialization.PublicFormat.CompressedPoint
			)
	id_hex = "002508021221"+public_key_bytes.hex()
	idNetwork = base58.b58encode(bytes.fromhex(id_hex)).decode()
	return private_key_bytes.hex(), idNetwork


def create_node(n):
	d = NODESDIRPREFIX+str(n)
	#creation of the directory for the node
	os.makedirs(d, exist_ok=True)
		
	#Creating the new account and saving the public key
	accDesc = run(f"geth --datadir {d} --password {sys.argv[1]}/psw.txt account new", shell=True, check=True, stdout=PIPE, text=True).stdout
	accountPK = re.search(r"Public address of the key:[^\n]+",accDesc).group()[-40:]
	Nodes2Desc[n] = {"pk": accountPK}
		
	#creation of the secret key file to determine the enode identifier before actually starting the node and retrieving it
	enode=run(f"bootnode -genkey {d}/enode.key -writeaddress", shell=True, check=True, stdout=PIPE, text=True).stdout[:-1]
	Nodes2Desc[n]["enode"] = enode
		
	#signers
	Nodes2Desc[n]["signer"] = True if n in listSigners else False

	#beacon
	k_net_hex, id_net = staticBeaconKEY_ID()
	with open(f"{d}/network-keys", 'w') as file: 
		file.write(k_net_hex)
	Nodes2Desc[n]["beaconID"] = id_net
		
	#validators
	Nodes2Desc[n]["validator"] = listValidators.index(n) if n in listValidators else -1
		
	#ether allocation for the node 
	gtj["alloc"][accountPK] = {"balance" : hex(nodes["balance"])}



if len(os.listdir(sys.argv[1])) != 0:
	new = input(f"Non-empty directory create new accounts? [y/N]?\n")
else:
	new = "y"
if new == "y":
	ts = time.time()
	run(f"sudo rm -rf {sys.argv[1]}", shell=True, check=True)
	os.makedirs(sys.argv[1])
	
	with open(f"{sys.argv[1]}/psw.txt", "w") as p:
		p.write("nodePassword")
		
	listSigners = random.sample( range(1,nodes["node_count"]+1), nodes["signers"])

	listValidators = random.sample( range(1,nodes["node_count"]+1), nodes["validators"])
	

	Nodes2Desc = {}
	gtj = {}

	with open("data/genesis-template.json", "r") as gf:
		gtj = json.load(gf)
	

	
	with concurrent.futures.ThreadPoolExecutor() as executor:
		futures = [executor.submit(create_node,n ) for n in range(1, nodesCount + 1)]
		# Wait for all tasks to complete
		concurrent.futures.wait(futures)
	
		
	#creation of the concatenation of all signers to be inserted into the new genesis block
	signers = "".join(map(lambda e: e['pk'],filter(lambda v: v["signer"], Nodes2Desc.values()))) if "clique" in gtj["config"] else ""
	gtj["extraData"] = gtj["extraData"].replace("<ListOfSigners>", signers)
		
	with open(f"{sys.argv[1]}/genesis.json", "w") as gf:
		json.dump(gtj,gf)
		
		
	with open(f"{sys.argv[1]}/nodesInfo.txt", "w") as ni:
		json.dump(Nodes2Desc,ni)
	
	print(f'''
Siner/miner Nodes: {listSigners},
Validatos Nodes: {listValidators}
''')
	tf = time.time()
	print(f'time Creation start {time.strftime("%H:%M:%S.{}".format(str(ts %1)[2:6]), time.gmtime(ts))}')
	print(f'time Creation fin {time.strftime("%H:%M:%S.{}".format(str(tf %1)[2:6]), time.gmtime(tf))}')
	print(f'duration {time.strftime("%H:%M:%S.{}".format(str((tf-ts) %1)[2:6]), time.gmtime((tf-ts)))}')
