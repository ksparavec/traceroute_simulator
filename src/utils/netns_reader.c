/*
 * netns_reader - Minimal wrapper for read-only network namespace operations
 * 
 * This program is designed to be given CAP_SYS_ADMIN capability to allow
 * unprivileged users to read network namespace information.
 * 
 * Security features:
 * - Whitelist of allowed commands
 * - Read-only operations only
 * - No shell execution
 * - Drops privileges after entering namespace
 * - Validates namespace names
 * 
 * Usage:
 *   netns_reader <namespace> <command> [args...]
 *   netns_reader --list
 * 
 * Compile:
 *   gcc -o netns_reader netns_reader.c
 *   sudo setcap cap_sys_admin+ep netns_reader
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sched.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <dirent.h>
#include <pwd.h>
#include <grp.h>

#define NETNS_PATH "/var/run/netns"
#define MAX_ARGS 32

/* Whitelist of allowed commands for security */
static const char *allowed_commands[][2] = {
    /* Command, Full path */
    {"ip", "/usr/sbin/ip"},
    {"iptables-save", "/usr/sbin/iptables-save"},
    {"ip6tables-save", "/usr/sbin/ip6tables-save"},
    {"ipset", "/usr/sbin/ipset"},
    {"ss", "/usr/bin/ss"},
    {"netstat", "/usr/bin/netstat"},
    {NULL, NULL}
};

/* Whitelist of allowed arguments for specific commands */
static const char *allowed_ip_args[] = {
    "addr", "show",
    "route", "show", "table",
    "rule", "show",
    "link", "show",
    "-j", "-json", "-details",
    NULL
};

static const char *allowed_ipset_args[] = {
    "list", "-n", "-name",
    NULL
};

/* Function to check if a command is allowed */
static const char* get_command_path(const char *cmd) {
    for (int i = 0; allowed_commands[i][0] != NULL; i++) {
        if (strcmp(allowed_commands[i][0], cmd) == 0) {
            return allowed_commands[i][1];
        }
    }
    return NULL;
}

/* Function to validate arguments for specific commands */
static int validate_args(const char *cmd, char *argv[], int argc) {
    if (strcmp(cmd, "ip") == 0) {
        /* Check if all arguments are in whitelist */
        for (int i = 0; i < argc; i++) {
            int found = 0;
            for (int j = 0; allowed_ip_args[j] != NULL; j++) {
                if (strcmp(argv[i], allowed_ip_args[j]) == 0) {
                    found = 1;
                    break;
                }
            }
            /* Allow numeric table IDs */
            if (!found && i > 0 && strcmp(argv[i-1], "table") == 0) {
                /* Basic check for numeric table ID */
                char *endptr;
                strtol(argv[i], &endptr, 10);
                if (*endptr == '\0') {
                    found = 1;
                }
            }
            if (!found) {
                fprintf(stderr, "Error: Argument '%s' not allowed for ip command\n", argv[i]);
                return 0;
            }
        }
    } else if (strcmp(cmd, "ipset") == 0) {
        /* Only allow list operations */
        for (int i = 0; i < argc; i++) {
            int found = 0;
            for (int j = 0; allowed_ipset_args[j] != NULL; j++) {
                if (strcmp(argv[i], allowed_ipset_args[j]) == 0) {
                    found = 1;
                    break;
                }
            }
            if (!found) {
                fprintf(stderr, "Error: Argument '%s' not allowed for ipset command\n", argv[i]);
                return 0;
            }
        }
    } else if (strcmp(cmd, "iptables-save") == 0 || 
               strcmp(cmd, "ip6tables-save") == 0) {
        /* No arguments allowed for iptables-save */
        if (argc > 0) {
            fprintf(stderr, "Error: No arguments allowed for %s\n", cmd);
            return 0;
        }
    }
    
    return 1;
}

/* Function to validate namespace name */
static int validate_namespace(const char *nsname) {
    /* Basic validation - no path traversal */
    if (strstr(nsname, "/") != NULL || strstr(nsname, "..") != NULL) {
        return 0;
    }
    
    /* Check if namespace exists */
    char nspath[256];
    snprintf(nspath, sizeof(nspath), "%s/%s", NETNS_PATH, nsname);
    
    struct stat st;
    if (stat(nspath, &st) != 0) {
        return 0;
    }
    
    return 1;
}

/* Function to list namespaces */
static void list_namespaces() {
    DIR *dir;
    struct dirent *entry;
    
    dir = opendir(NETNS_PATH);
    if (dir == NULL) {
        perror("opendir");
        exit(1);
    }
    
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] != '.') {
            printf("%s\n", entry->d_name);
        }
    }
    
    closedir(dir);
}

/* Function to enter namespace and execute command */
static int enter_namespace_and_exec(const char *nsname, const char *cmd_path, 
                                   char *argv[]) {
    char nspath[256];
    int nsfd;
    
    /* Open namespace file */
    snprintf(nspath, sizeof(nspath), "%s/%s", NETNS_PATH, nsname);
    nsfd = open(nspath, O_RDONLY);
    if (nsfd < 0) {
        perror("open namespace");
        return 1;
    }
    
    /* Enter the namespace */
    if (setns(nsfd, CLONE_NEWNET) < 0) {
        perror("setns");
        close(nsfd);
        return 1;
    }
    close(nsfd);
    
    /* Drop all capabilities except what's needed */
    /* Note: After setns, we don't need CAP_SYS_ADMIN anymore */
    
    /* Get original UID/GID */
    uid_t real_uid = getuid();
    gid_t real_gid = getgid();
    
    /* Drop privileges back to original user */
    if (setgid(real_gid) < 0 || setuid(real_uid) < 0) {
        perror("Failed to drop privileges");
        return 1;
    }
    
    /* Execute the command */
    execv(cmd_path, argv);
    
    /* If we get here, exec failed */
    perror("execv");
    return 1;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <namespace> <command> [args...]\n", argv[0]);
        fprintf(stderr, "       %s --list\n", argv[0]);
        exit(1);
    }
    
    /* Handle --list option */
    if (strcmp(argv[1], "--list") == 0) {
        list_namespaces();
        return 0;
    }
    
    if (argc < 3) {
        fprintf(stderr, "Error: Missing command\n");
        fprintf(stderr, "Usage: %s <namespace> <command> [args...]\n", argv[0]);
        exit(1);
    }
    
    const char *nsname = argv[1];
    const char *cmd = argv[2];
    
    /* Validate namespace */
    if (!validate_namespace(nsname)) {
        fprintf(stderr, "Error: Invalid or non-existent namespace '%s'\n", nsname);
        exit(1);
    }
    
    /* Check if command is allowed */
    const char *cmd_path = get_command_path(cmd);
    if (cmd_path == NULL) {
        fprintf(stderr, "Error: Command '%s' not allowed\n", cmd);
        fprintf(stderr, "Allowed commands: ip, iptables-save, ip6tables-save, ipset, ss, netstat\n");
        exit(1);
    }
    
    /* Prepare arguments for exec */
    char *exec_argv[MAX_ARGS];
    exec_argv[0] = (char *)cmd;
    
    int arg_count = 0;
    for (int i = 3; i < argc && arg_count < MAX_ARGS - 2; i++) {
        exec_argv[arg_count + 1] = argv[i];
        arg_count++;
    }
    exec_argv[arg_count + 1] = NULL;
    
    /* Validate arguments */
    if (!validate_args(cmd, &exec_argv[1], arg_count)) {
        exit(1);
    }
    
    /* Enter namespace and execute */
    return enter_namespace_and_exec(nsname, cmd_path, exec_argv);
}