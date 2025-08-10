/* _GNU_SOURCE already defined in Makefile */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "router_facts_loader.h"

/* Create network namespace for router */
int create_namespace(const char *namespace) {
    char cmd[512];
    
    /* Check if namespace already exists */
    snprintf(cmd, sizeof(cmd), "ip netns list | grep -w %s > /dev/null 2>&1", namespace);
    if (system(cmd) == 0) {
        printf("  Namespace %s already exists, continuing...\n", namespace);
        return 0;
    }
    
    /* Create namespace */
    snprintf(cmd, sizeof(cmd), "ip netns add %s", namespace);
    return system(cmd);
}

/* Setup router from facts */
int setup_router(router_t *router) {
    const char *ns = router->name;
    
    printf("Setting up router: %s\n", ns);
    
    /* Create namespace */
    if (create_namespace(ns) != 0) {
        fprintf(stderr, "Failed to create namespace %s\n", ns);
        return -1;
    }
    
    /* Set up sysctl for IP forwarding */
    char sysctl_cmd[256];
    snprintf(sysctl_cmd, sizeof(sysctl_cmd), "ip netns exec %s sysctl -w net.ipv4.ip_forward=1 > /dev/null 2>&1", ns);
    system(sysctl_cmd);
    snprintf(sysctl_cmd, sizeof(sysctl_cmd), "ip netns exec %s sysctl -w net.ipv6.conf.all.forwarding=1 > /dev/null 2>&1", ns);
    system(sysctl_cmd);
    
    /* Create batch context for this router */
    batch_context_t *batch = create_batch_context(1024 * 1024);
    if (!batch) {
        fprintf(stderr, "Failed to create batch context for %s\n", ns);
        return -1;
    }
    
    /* Enable loopback */
    batch_add_command(batch, ns, "ip link set lo up");
    
    /* Set up interfaces */
    for (size_t i = 0; i < router->interface_count; i++) {
        interface_t *iface = &router->interfaces[i];
        
        /* Skip loopback */
        if (strcmp(iface->name, "lo") == 0) {
            continue;
        }
        
        /* For real namespaces, interfaces need to be created as veth pairs */
        /* This is complex and requires coordination with hidden mesh infrastructure */
        /* For now, we'll just try to configure addresses on existing interfaces */
        
        /* First check if interface exists in namespace */
        char check_cmd[256];
        snprintf(check_cmd, sizeof(check_cmd), "ip netns exec %s ip link show %s > /dev/null 2>&1", ns, iface->name);
        if (system(check_cmd) != 0) {
            /* Interface doesn't exist - this is expected for real hardware interfaces */
            /* NOTE: The Python implementation creates veth pairs with a hidden mesh */
            /* infrastructure. This C implementation creates dummy interfaces as a */
            /* simplified alternative. For full functionality, use the Python version. */
            
            /* Create dummy interface as placeholder */
            char create_cmd[256];
            snprintf(create_cmd, sizeof(create_cmd), "ip link add %s type dummy", iface->name);
            batch_add_command(batch, ns, create_cmd);
            
            /* Set MAC address if specified */
            if (iface->mac) {
                char mac_cmd[256];
                snprintf(mac_cmd, sizeof(mac_cmd), "ip link set %s address %s", iface->name, iface->mac);
                batch_add_command(batch, ns, mac_cmd);
            }
        }
        
        /* Configure addresses */
        for (size_t j = 0; j < iface->addr_count; j++) {
            address_t *addr = &iface->addresses[j];
            char cmd[512];
            
            if (addr->secondary) {
                snprintf(cmd, sizeof(cmd), "ip addr add %s brd %s dev %s", 
                         addr->ip, addr->broadcast ? addr->broadcast : "+", iface->name);
            } else {
                snprintf(cmd, sizeof(cmd), "ip addr add %s brd %s dev %s", 
                         addr->ip, addr->broadcast ? addr->broadcast : "+", iface->name);
            }
            batch_add_command(batch, ns, cmd);
        }
        
        /* Set interface state */
        if (iface->up) {
            char cmd[256];
            snprintf(cmd, sizeof(cmd), "ip link set %s up", iface->name);
            batch_add_command(batch, ns, cmd);
        }
        
        /* Set MTU if not default */
        if (iface->mtu && iface->mtu != 1500) {
            char cmd[256];
            snprintf(cmd, sizeof(cmd), "ip link set %s mtu %d", iface->name, iface->mtu);
            batch_add_command(batch, ns, cmd);
        }
    }
    
    /* Add routes */
    for (size_t i = 0; i < router->route_count; i++) {
        route_t *route = &router->routes[i];
        char cmd[512];
        
        /* Skip local routes (proto kernel) - they're auto-created */
        if (route->protocol && strcmp(route->protocol, "kernel") == 0) {
            continue;
        }
        
        /* Build route command */
        strcpy(cmd, "ip route add ");
        strcat(cmd, route->destination);
        
        if (route->gateway) {
            strcat(cmd, " via ");
            strcat(cmd, route->gateway);
        }
        
        if (route->device) {
            strcat(cmd, " dev ");
            strcat(cmd, route->device);
        }
        
        if (route->source) {
            strcat(cmd, " src ");
            strcat(cmd, route->source);
        }
        
        if (route->metric > 0) {
            char metric_str[32];
            snprintf(metric_str, sizeof(metric_str), " metric %d", route->metric);
            strcat(cmd, metric_str);
        }
        
        if (route->table && strcmp(route->table, "main") != 0) {
            strcat(cmd, " table ");
            strcat(cmd, route->table);
        }
        
        batch_add_command(batch, ns, cmd);
    }
    
    /* Add policy rules */
    for (size_t i = 0; i < router->rule_count; i++) {
        rule_t *rule = &router->rules[i];
        char cmd[512];
        
        /* Skip default rules that are auto-created */
        if (rule->priority == 0 || rule->priority == 32766 || rule->priority == 32767) {
            continue;
        }
        
        /* Skip rules for non-existent tables (will fail anyway) */
        if (rule->table && atoi(rule->table) == 0 && 
            strcmp(rule->table, "main") != 0 && 
            strcmp(rule->table, "local") != 0 && 
            strcmp(rule->table, "default") != 0) {
            /* Custom table name that might not exist */
            continue;
        }
        
        snprintf(cmd, sizeof(cmd), "ip rule add priority %d", rule->priority);
        
        if (rule->from) {
            strcat(cmd, " from ");
            strcat(cmd, rule->from);
        }
        
        if (rule->to) {
            strcat(cmd, " to ");
            strcat(cmd, rule->to);
        }
        
        if (rule->iif) {
            strcat(cmd, " iif ");
            strcat(cmd, rule->iif);
        }
        
        if (rule->oif) {
            strcat(cmd, " oif ");
            strcat(cmd, rule->oif);
        }
        
        if (rule->fwmark) {
            char fwmark_str[32];
            snprintf(fwmark_str, sizeof(fwmark_str), " fwmark 0x%x", rule->fwmark);
            strcat(cmd, fwmark_str);
        }
        
        if (rule->dport) {
            char dport_str[32];
            snprintf(dport_str, sizeof(dport_str), " dport %d", rule->dport);
            strcat(cmd, dport_str);
        }
        
        if (rule->sport) {
            char sport_str[32];
            snprintf(sport_str, sizeof(sport_str), " sport %d", rule->sport);
            strcat(cmd, sport_str);
        }
        
        if (rule->table) {
            strcat(cmd, " lookup ");
            strcat(cmd, rule->table);
        }
        
        batch_add_command(batch, ns, cmd);
    }
    
    /* Enable IP forwarding (already done after namespace creation) */
    batch_add_command(batch, ns, "sysctl -w net.ipv4.ip_forward=1 > /dev/null 2>&1");
    batch_add_command(batch, ns, "sysctl -w net.ipv6.conf.all.forwarding=1 > /dev/null 2>&1");
    
    /* Execute all basic setup commands */
    printf("  Executing interface/route/rule setup...\n");
    if (batch_execute(batch) != 0) {
        fprintf(stderr, "  WARNING: Some commands failed for %s\n", ns);
    }
    
    /* Apply ipsets first (iptables rules may reference them) */
    if (router->ipset_save.raw_content && router->ipset_save.content_size > 0) {
        printf("  Applying ipsets (%zu bytes)...\n", router->ipset_save.content_size);
        if (apply_ipset_with_shm(ns, &router->ipset_save) != 0) {
            fprintf(stderr, "  WARNING: Failed to apply ipsets for %s\n", ns);
        }
    } else {
        printf("  No ipset configuration to apply\n");
    }
    
    /* Apply iptables */
    if (router->iptables_save.raw_content && router->iptables_save.content_size > 0) {
        printf("  Applying iptables (%zu bytes)...\n", router->iptables_save.content_size);
        if (apply_iptables_with_shm(ns, &router->iptables_save) != 0) {
            fprintf(stderr, "  WARNING: Failed to apply iptables for %s\n", ns);
        }
    } else {
        printf("  No iptables configuration to apply\n");
    }
    
    free_batch_context(batch);
    printf("  Router %s setup complete\n", ns);
    
    return 0;
}

/* Main network setup */
int main(int argc, char *argv[]) {
    int verbose = 0;
    (void)verbose;  /* Mark as intentionally unused */
    int parallel = 0;
    const char *limit_pattern = NULL;
    
    /* Parse arguments */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--verbose") == 0) {
            verbose = 1;
        } else if (strcmp(argv[i], "-p") == 0 || strcmp(argv[i], "--parallel") == 0) {
            parallel = 1;
        } else if (strcmp(argv[i], "--limit") == 0 && i + 1 < argc) {
            limit_pattern = argv[++i];
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            printf("Usage: %s [options]\n", argv[0]);
            printf("Options:\n");
            printf("  -v, --verbose     Verbose output\n");
            printf("  -p, --parallel    Setup routers in parallel\n");
            printf("  --limit PATTERN   Only setup routers matching pattern\n");
            printf("  -h, --help        Show this help\n");
            return 0;
        }
    }
    
    /* Check if running as root */
    if (geteuid() != 0) {
        fprintf(stderr, "This program must be run as root\n");
        return 1;
    }
    
    /* Load facts from environment */
    facts_context_t *ctx = NULL;
    printf("Loading router facts from TRACEROUTE_SIMULATOR_RAW_FACTS...\n");
    if (load_facts_from_env(&ctx) != 0) {
        fprintf(stderr, "Failed to load facts\n");
        return 1;
    }
    
    printf("Loaded %zu routers\n", ctx->router_count);
    
    /* Setup routers */
    if (parallel) {
        printf("Setting up routers in parallel...\n");
        
        /* Fork processes for parallel setup */
        size_t batch_size = 10;  /* Process 10 routers per batch */
        for (size_t i = 0; i < ctx->router_count; i += batch_size) {
            size_t end = i + batch_size;
            if (end > ctx->router_count) end = ctx->router_count;
            
            /* Fork for this batch */
            pid_t pid = fork();
            if (pid == 0) {
                /* Child process - setup routers in this batch */
                for (size_t j = i; j < end; j++) {
                    router_t *router = ctx->routers[j];
                    
                    /* Apply limit pattern if specified */
                    if (limit_pattern) {
                        if (!strstr(router->name, limit_pattern)) {
                            continue;
                        }
                    }
                    
                    setup_router(router);
                }
                exit(0);
            } else if (pid < 0) {
                fprintf(stderr, "Fork failed\n");
            }
        }
        
        /* Wait for all children */
        while (wait(NULL) > 0);
        
    } else {
        printf("Setting up routers sequentially...\n");
        
        for (size_t i = 0; i < ctx->router_count; i++) {
            router_t *router = ctx->routers[i];
            
            /* Apply limit pattern if specified */
            if (limit_pattern) {
                if (!strstr(router->name, limit_pattern)) {
                    continue;
                }
            }
            
            setup_router(router);
        }
    }
    
    printf("\nNetwork setup complete\n");
    
    /* Show summary */
    printf("\nNamespaces created:\n");
    if (system("ip netns list | wc -l") == 0) {
        system("ip netns list | head -20");
    }
    
    free_facts_context(ctx);
    return 0;
}