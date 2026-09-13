/*
 * Waydroid container capability and priority shim library.
 * Stubs missing kernel/container capabilities and thread priorities for Android services.
 */

int cap_set_proc(void* cap) {
    return 0;
}

int capset(void* hdrp, const void* datap) {
    return 0;
}

int setpriority(int which, int who, int prio) {
    return 0;
}

int cap_get_flag(void* cap_p, int cap, int flag, int* value_p) {
    if (value_p) {
        *value_p = 1;
    }
    return 0;
}
