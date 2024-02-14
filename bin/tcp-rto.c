#include <linux/bpf.h>

#ifndef __section
# define __section(NAME)                  \
    __attribute__((section(NAME), used))
#endif


__section("sockops")
int set_initial_rto(struct bpf_sock_ops *skops)
{
    const int timeout = 3;
    const int hz = 250;    // grep 'CONFIG_HZ=' /boot/config-$(uname -r), HZ of my machine

    int op = (int) skops->op;
    if (op == BPF_SOCK_OPS_TIMEOUT_INIT) {
        skops->reply = hz * timeout; 
        return 1;
    }

    return 1;
}

char _license[] __section("license") = "GPL";