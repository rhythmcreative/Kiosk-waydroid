#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <poll.h>

#define SOCKET_PATH "/dev/socket/lmkd"
#define ANDROID_SOCKET_ENV "ANDROID_SOCKET_lmkd"

enum lmk_cmd {
    LMK_TARGET = 0,
    LMK_PROCPRIO = 1,
    LMK_PROCREMOVE = 2,
    LMK_PROCPURGE = 3,
    LMK_GETKILLCNT = 4,
    LMK_SUBSCRIBE = 5,
    LMK_PROCKILL = 6,
};

static void set_oom_adj(int pid, int adj) {
    char path[128];
    snprintf(path, sizeof(path), "/proc/%d/oom_score_adj", pid);
    int fd = open(path, O_WRONLY);
    if (fd >= 0) {
        char buf[32];
        int len = snprintf(buf, sizeof(buf), "%d\n", adj);
        write(fd, buf, len);
        close(fd);
    }
}

int main(int argc, char *argv[]) {
    int listen_fd = -1;
    char *env = getenv(ANDROID_SOCKET_ENV);

    if (env) {
        listen_fd = atoi(env);
    }

    if (listen_fd < 0) {
        unlink(SOCKET_PATH);
        listen_fd = socket(AF_UNIX, SOCK_SEQPACKET, 0);
        if (listen_fd < 0) {
            perror("socket");
            return 1;
        }

        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);

        if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
            perror("bind");
            return 1;
        }

        chmod(SOCKET_PATH, 0666);
    }

    if (listen(listen_fd, 16) < 0) {
        perror("listen");
        return 1;
    }

    printf("dummy_lmkd: listening on socket\n");
    fflush(stdout);

    struct pollfd fds[16];
    int nfds = 1;
    fds[0].fd = listen_fd;
    fds[0].events = POLLIN;

    for (int i = 1; i < 16; i++) {
        fds[i].fd = -1;
    }

    while (1) {
        int ret = poll(fds, nfds, -1);
        if (ret < 0) {
            if (errno == EINTR) continue;
            break;
        }

        if (fds[0].revents & POLLIN) {
            int client_fd = accept(listen_fd, NULL, NULL);
            if (client_fd >= 0) {
                if (nfds < 16) {
                    fds[nfds].fd = client_fd;
                    fds[nfds].events = POLLIN;
                    nfds++;
                } else {
                    close(client_fd);
                }
            }
        }

        for (int i = 1; i < nfds; i++) {
            if (fds[i].fd >= 0 && (fds[i].revents & (POLLIN | POLLERR | POLLHUP))) {
                int buf[64];
                ssize_t n = read(fds[i].fd, buf, sizeof(buf));
                if (n <= 0) {
                    close(fds[i].fd);
                    fds[i] = fds[nfds - 1];
                    nfds--;
                    i--;
                } else if (n >= 4) {
                    int cmd = buf[0];
                    if (cmd == LMK_PROCPRIO && n >= 16) {
                        int pid = buf[1];
                        int uid = buf[2];
                        int oom_adj = buf[3];
                        set_oom_adj(pid, oom_adj);
                    } else if (cmd == LMK_GETKILLCNT) {
                        int reply[2] = { LMK_GETKILLCNT, 0 };
                        write(fds[i].fd, reply, sizeof(reply));
                    }
                }
            }
        }
    }
    return 0;
}
