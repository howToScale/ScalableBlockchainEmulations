#!/bin/bash
set -x
set -e


# Compile the bpf_sockops program
clang -O2 -target bpf -c bin/tcp-rto.c -o bin/tcp-rto.o


# Load the bpf_sockops program
sudo bpftool prog load bin/tcp-rto.o /sys/fs/bpf/tcp-rto
PROG_ID=$(sudo bpftool prog show | grep 'set_initial_rto' | egrep -o '^[^:]*')
#echo $PROG_ID
sudo bpftool cgroup attach /sys/fs/cgroup sock_ops id $PROG_ID