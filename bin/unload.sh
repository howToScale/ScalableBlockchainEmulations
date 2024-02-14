#!/bin/bash
set -x

# UnLoad the bpf_redir program
sudo rm /sys/fs/bpf/tcp-rto


PROG_ID="${PROG_ID:-$(sudo bpftool prog show | grep 'set_initial_rto' | egrep -o '^[^:]*')}"
if [[ "$PROG_ID" ]]; then
	sudo bpftool cgroup detach /sys/fs/cgroup sock_ops id $PROG_ID
fi