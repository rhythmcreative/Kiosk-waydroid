#define _GNU_SOURCE
#include <unistd.h>
#include <sys/syscall.h>

/*
 * Waydroid container capability and priority shim library.
 * Stubs missing kernel/container capabilities and thread priorities for Android services.
 */

int cap_set_proc(void* cap) {
    return 0;
}

int capset(void* hdrp, const void* datap) {
    long ret = syscall(SYS_capset, hdrp, datap);
    if (ret < 0) {
        return 0;
    }
    return (int)ret;
}

int setpriority(int which, int who, int prio) {
    long ret = syscall(SYS_setpriority, which, who, prio);
    if (ret < 0) {
        return 0;
    }
    return (int)ret;
}

int cap_get_flag(void* cap_p, int cap, int flag, int* value_p) {
    if (value_p) {
        *value_p = 1;
    }
    return 0;
}

