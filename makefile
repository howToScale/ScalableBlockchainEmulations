# -- DEFINITIONS --


node_count:=$(shell awk '$$1 ~ /node_count/ {print $$2}' data/config.yml)
validators:=$(shell awk '$$1 ~ /validators/ {print $$2}' data/config.yml)


docker_image_name  := lite-full-ethereum-image



vnetname	:= lite-full_net
subnet8		   := 10

# functions and macros

net_exists		= test -n "$$(docker network ls --format '{{.Name}}' -f 'name=$(1)')"
machine_exists	= test -n "$$(docker ps -a --format '{{.Names}}' -f 'name=$(1)')"
all_machines_nms   = docker ps -a --format="{{.Names}}"
up_mach           = docker ps --format="{{.Names}}"


define id2ip_addr
	python3 << EOF
	ipAddr =list()
	ipAddr.append("$(subnet8)")
	ipAddr.append("1")
	ipAddr.append(str($(1)//100))
	ipAddr.append(str($(1)%100))
	print(".".join(ipAddr))
	EOF
endef


define help_msg
-- AVAILABLE TARGETS --
buildImage		build docker image 
confNetBuffers	set  sysctl parameters
confSlow{X}		change config.yml and PrysmConfig.yml to perform (delay * X)


createAccounts	create all the accounts with their keys and create the genesis.json file 
initAccounts	generate genesis block files for becon chain and initialize account for each node 
boot			create idle container, waiting for a signal to start the activity, also create docker virtual network 
completeBoot	complite the bootstrap (routing table, delay, inflation, ...)
node{X}logs		start a multitail logging process for node X, showing enode, beacon-node, and validator logs simultaneously
startNodes		send unix singal USR1 to each node (command used 3 times to sequentially start the enode, beacon-node, and validator roles of each node)
transaction		send unix singal USR2 to each node to start the transaction activity

teardown		stop the experiment by removing containers and network



endef


# -- TARGETS --

# die whenever a command exits with non-zero status
.SHELLFLAGS += -e
# suppress make command echoing (we're using -x where needed)
MAKEFLAGS   += -s

.ONESHELL:
.PHONY: buildImage confNetBuffers confSlow% createAccounts initAccounts boot completeBoot node%logs startNodes transaction teardown

createAccounts: run
	bin/createAccounts.py run


initAccounts: run beacon_ssz
	bin/initAccounts.py run


completeBoot: netns 
	if [ -n "$(shell $(all_machines_nms))" ]; then
		sudo python3 bin/completeBoot.py &
	else
		echo "no machines to boot, skipping..."
	fi

EvalBoot: 
	$(eval rate=$(shell echo "scale=6 ; $(node_count) / ($(shell awk '$$1 ~ /block_size/ {print $$2}' data/config.yml) / $(shell awk '$$1 ~ /block_time/ {print $$2}' data/config.yml))" | bc))


NodeBoot: $(foreach i,$(shell seq $(node_count)),up_node$(i)) 
	echo -en '\007'

boot: EvalBoot NodeBoot

confNetBuffers:
	sudo sysctl -w kernel.pty.max=110000
	sudo sysctl -w net.core.rmem_max=2147483647
	sudo sysctl -w net.core.rmem_default=2147483647
	sudo sysctl -w net.core.wmem_max=2147483647
	sudo sysctl -w net.core.wmem_default=2147483647

	sudo sysctl -w net.ipv4.tcp_rmem="10240 87380 16777216"
	sudo sysctl -w net.ipv4.tcp_wmem="10240 87380 16777216"
	sudo sysctl -w net.ipv4.neigh.default.gc_thresh1=200000
	sudo sysctl -w net.ipv4.neigh.default.gc_thresh2=200000
	sudo sysctl -w net.ipv4.neigh.default.gc_thresh3=200000

buildImage: Dockerfile
	set -x
	docker rmi -f $(docker_image_name)
	docker build -t $(docker_image_name) -f $< .




confSlow%:
	bt=$$((5 * $*))
	secSlot=$$((12 * $*))
	slotEp=$$((6 * $*))
	sed -i "s/\(^SLOW_MULTIPLIER:\).*/\1 $*/" data/config.yml
	sed -i "s/^\([[:space:]]*block_time:[[:space:]]*\).*/\1$$bt/" data/config.yml
	sed -i "s/\(^SECONDS_PER_SLOT:\).*/\1 $$secSlot/" data/PrysmConfig.yml
	sed -i "s/\(^SLOTS_PER_EPOCH:\).*/\1 $$slotEp/" data/PrysmConfig.yml


down: kill unslow
	if [ -n "$(shell $(all_machines_nms))" ]; then
		set -x
		docker rm -v -f $(shell $(all_machines_nms))
	else
		echo "no machines to teardown, skipping..."
	fi




help:
	echo "$(help_msg)"

kill:
	if [ -n "$(shell $(up_mach))" ]; then
		set -x
		docker kill --signal=INT $(shell $(up_mach))
	else
		echo "no failed machines found, skipping..."
	fi



network:
	if ! $(call net_exists,$(vnetname)); then
		docker network create $(vnetname) --subnet $(subnet8).0.0.0/8
	else
		echo "network already exists, skipping..."
	fi



run:
	mkdir -p $@

netns:
	sudo mkdir -p /var/run/netns
	sudo chown $(shell whoami): /var/run/netns

startNodes:  
	set -x
	docker kill --signal=USR1 $(shell $(up_mach))

transaction: 
	set -x
	docker kill --signal=USR2 $(shell $(up_mach))





teardown: down
	if $(call net_exists,$(vnetname)); then
		set -x
		docker network rm $(vnetname)
	else
		echo "network does not exist, skipping..."
	fi


unslow:
	sudo nft delete table latem 2> /dev/null && echo "deleted nft table 'latem'" || echo "nft table 'latem' is already deleted"
	sudo rm -f "run/tc_batch_file"
	bin/unload.sh
	

up_node%: network run 
	set -x
	docker container run -dit --name "node_$*" \
		-v "$(CURDIR)/run/node_$*:/home" \
		-v "$(CURDIR)/bin/nodebin:/home/bin" \
		-v "$(CURDIR)/run/nodesInfo.txt:/home/bin/nodesInfo.txt" \
		-v "$(CURDIR)/run/psw.txt:/home/psw.txt" \
		-v "$(CURDIR)/data/PrysmConfig.yml:/home/PrysmConfig.yml" \
		-v "$(CURDIR)/run/genesisPrysm.ssz:/home/genesisPrysm.ssz" \
		--network $(vnetname) \
		--ip $(shell $(call id2ip_addr,$*)) \
		--sysctl net.ipv4.neigh.eth0.base_reachable_time_ms=72000000 \
		--sysctl net.ipv4.neigh.eth0.mcast_solicit=0\
		--sysctl net.ipv4.neigh.eth0.app_solicit=1\
		--cap-add=NET_ADMIN $(docker_image_name) bin/node.py $* $(rate)


beacon_ssz:
	export PATH=$PATH:$(go env GOPATH)/bin
	set -x
	bin/prysmctl testnet generate-genesis  \
	--fork=capella \
	--num-validators=$(validators) \
	--output-ssz=run/genesisPrysm.ssz \
	--chain-config-file=data/PrysmConfig.yml  \
	--geth-genesis-json-in=run/genesis.json  \
	--geth-genesis-json-out=run/genesis.json

node%logs:
	echo '' | sudo tee run/node_$*/node.log > /dev/null
	echo '' | sudo tee run/node_$*/beacon.log > /dev/null
	echo '' | sudo tee run/node_$*/validator.log > /dev/null
	multitail -M 0 -CS litefull run/node_$*/node.log run/node_$*/beacon.log run/node_$*/validator.log






