# ScalableBlockchainEmulations

This repository is intended to assist in the replication of the development experiments describe in [[1]](#1) (see bibliography). 


## System setup

In this Section we show all the steps to configure a Debian (12) machine.
At the end of these steps it will be possible to run the tests.



1. Install Debian, in the way that is deemed most appropriate. [Getting Debian](https://www.debian.org/distrib/index.en.html).
2. Install all the required packages.
	```bash
	sudo apt-get install golang clang bpftool build-essential libncurses-dev bison flex libssl-dev libelf-dev fakeroot dwarves python3-base58  python3-networkx  python3-docker gcc-multilib multitail ca-certificates curl gnupg
	```
3. Install Docker Engine using the [official documentation](https://docs.docker.com/engine/install/debian/).
4. Download this repository.
5. Move the executable *geth* and *bootnode* from the repository root to /usr/local/bin, an updated version can be downloaded at [go-ethereum](https://geth.ethereum.org/downloads). Both executable can be found in the Ghet & Tools archive throughout the website. 
	```bash
	cd ScalableBlockchainEmulations
	sudo mv geth bootnode /usr/local/bin 
	```
6. Download and unpack the source code of the desired kernel, version 6.1.70 in our case.
	```bash
	wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.1.70.tar.xz
	tar xf linux-6.1.70.tar.xz 
	```
7. Configure the kernel if we need to run more than 1000 containers, otherwise skip this step :
	1. Change directory
	```bash
	cd linux-6.1.70 
	```
	2. For clarity change the name of the kernel so that it is more identifiable. This command add *compiledVersion* as *extraversion* value
	```bash
	sed -i "s/\(^EXTRAVERSION =\).*/\1 compiledVersion/" Makefile
	```
	3. The configuration of the Linux kernel can be specified in a .config file. A good starting point is to copy the config file of your currently installed Debian: 
	```bash
	cp -v /boot/config-$(uname -r) .config
	```
	4. However, this config file includes tons of unnecessary drivers and kernel modules which dramatically increases the build time. To mitigate this, we can use the **localmodconfig** command. This command looks at the loaded kernel modules of your system and modifies the *.config* file such that only these modules are included in the build. This should work perfectly fine as long as you do not plan to use the generated build on another machine than the one you compile the source on. If, while running the following command, any requests are prompted to you, just hit enter each time (without typing an answer).
	```bash
	make localmodconfig
	```
	5. Next, you need to make four modifications to the configuration. Otherwise the build will fail. To do this, you can either directly modify the *.config* file or simply run the following commands:
	```bash
	scripts/config --disable SYSTEM_TRUSTED_KEYS
	scripts/config --disable SYSTEM_REVOCATION_KEYS
	scripts/config --set-str CONFIG_SYSTEM_TRUSTED_KEYS ""
	scripts/config --set-str CONFIG_SYSTEM_REVOCATION_KEYS ""
	```
	6. Modify the **BR_PORT_BITS** in the file *net/bridge/br_private.h* to handle 2^*BR_PORT_BITS* containers. To do this, you can either directly modify the file or simply run the following commands (The command is defined to increase the parameter from 10 to 14):
	```bash
	sed -i "s/\(^#define BR_PORT_BITS	\).*/\1 14/" Makefile
	```
 	7. Compile the kernel.
 	```bash
 	fakeroot make -j
 	```
 	8. After the build finishes, you can check whether it is successful. The following command outputs the return code of the previous command. If it returns *0*, the build was successful. For any other value than *0* the build was not successful.
 	```bash
 	echo $?
 	```
 	9. Now we can install the new kernel. The installation is split into two parts: Installing the kernel modules and installing the kernel itself.
 	```bash
 	sudo make modules_install
 	sudo make install
 	```
 	10. After that, reboot your machine:
 	```bash
 	sudo reboot
 	```
 	11. Check the version of the installed kernel by running
 	```bash
	uname -rs
 	```
8. Change *ulimit* parameters: (1) the number of open files and (2) the maximum number of processes. To do this, you can either directly modify the */etc/security/limits.conf* file or simply run the following commands:
```bash
echo "
root	hard	nofile	1048576
root 	soft	nofile	1048576
root    hard    nproc   1574415
root 	soft	nproc	1574415" | sudo tee -a /etc/security/limits.conf
```

9. Move the file *multitail.conf* from the repository to the root. This is useful for defining a color scheme that will be used for node logging.
```bash
mv multitail.conf /
```


10. Download the current version of prysm from [Prysm-github-releases](https://github.com/prysmaticlabs/prysm/releases) with all executable needed for the experiment and move them to the correct project directory.It is assumed to be in the root of the repository
```bash
wget https://github.com/prysmaticlabs/prysm/releases/download/v4.2.1/prysmctl-v4.2.1-linux-amd64
mv prysmctl-v4.2.1-linux-amd64 ./bin/prysmctl

wget https://github.com/prysmaticlabs/prysm/releases/download/v4.2.1/beacon-chain-v4.2.1-linux-amd64
mv beacon-chain-v4.2.1-linux-amd64 ./bin/nodebin/beacon-chain

wget https://github.com/prysmaticlabs/prysm/releases/download/v4.2.1/validator-v4.2.1-linux-amd64
mv validator-v4.2.1-linux-amd64 ./bin/nodebin/validator
```

11. Now the system is set up correctly. And you can proceed with the execution of the experiments.

## Experiments execution

In this Section we show all the steps to run an experiment. To configure the number of total nodes and number of nodes per single role, edit the parameters in the *data/config.yml* file

1. Create the image that will be used by each node. Step required only once.
```bash
make buildImage
```
2.  Set all sysctl parameters described in the *makefile*. This step must be repeated each time the Debian machine is rebooted.
```bash
make confNetBuffers
```
3. Configure the time inflation of a factor *X*.
```bash
make confSlow<X>
```
for example to configure a time inflation of a factor 3, run the following command:
```bash
make confSlow3
```
4. Create all account directories with the required files (e.g, secret key, genesis file for ETH1). Step to be repeated only when changing the number of nodes.
```bash
make createAccounts
```
5. Initialize an account for each node and generate a genesis block file for the beacon chain. Step that can be repeated if you want to return to an initial state after the end of an experiment.
```bash
make initAccounts
```
6. Create idle container, waiting for a signal to start the activity.
```bash
make boot
```
7. Perform al the bootstrap activity (e.g. routing table, compute delay, apply inflation, etc...) 
```bash
make completeBoot
```
9. (Optional) Start a multitail logging process for node *X*, showing enode, beacon-node, and validator logs simultaneously
```bash
make node<X>logs
```
for example to log the node 3, run the following command:
```bash
make node3logs
```

10. Start the *execution-node* role of each node
```bash
make startNodes
```
11. Start the *beacon* role of each node
```bash
make startNodes
```
12. Start the *validator* role of each node
```bash
make startNodes
```
13. Start the *transaction* activity.
```bash
make transaction
```

14. Stop the execution and remove each container.
```bash
make teardown
```


## Bibliography

<a name="1">[1]</a>  Diego Pennino, Maurizio Pizzonia. [Toward Scalable ...... ]() (under review).