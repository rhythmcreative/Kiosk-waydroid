#define _GNU_SOURCE
#include <errno.h>
#include <unistd.h>

/*
 * Bypass Cage 0.1.4's drop_permissions() check when running inside a Docker container as root.
 * Cage checks if setuid(0) / setgid(0) succeed; if they do, it refuses to start as root.
 * Returning -1 with EPERM allows Cage to proceed as expected.
 */
int setuid(uid_t uid) {
    if (uid == 0) {
        errno = EPERM;
        return -1;
    }
    return 0;
}

int setgid(gid_t gid) {
    if (gid == 0) {
        errno = EPERM;
        return -1;
    }
    return 0;
}
