/* Hidden Mesh Network Setup - Full C Implementation
 * 
 * Complete implementation matching Python's network_namespace_setup.py
 * Creates hidden mesh infrastructure with veth pairs and bridges
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/ioctl.h>
#include <signal.h>
#include <termios.h>
#include <dirent.h>
#include <time.h>
#include <errno.h>
#include <ctype.h>
#include <arpa/inet.h>
#include "router_facts_loader.h"
#include "shared_registry.h"

#define HIDDEN_NS "hidden-mesh"
#define MAX_BRIDGE_NAME 16
#define PROGRESS_BAR_WIDTH 50

/* Global for signal handling */
static volatile int interrupted = 0;
static int progress_active = 0;
static int terminal_width = 80;

/* Signal handler for Ctrl-C */
void sigint_handler(int sig) {
    (void)sig; /* Suppress unused warning */
    interrupted = 1;
    /* Always print interrupt message */
    fprintf(stderr, "\n*** SIGINT received, setting interrupted flag ***\n");
    fflush(stderr);
    signal(SIGINT, SIG_DFL);  /* Reset to default handler for second Ctrl-C */
}

/* Get terminal width */
int get_terminal_width() {
    struct winsize w;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &w) == 0) {
        return w.ws_col;
    }
    return 80; /* Default */
}

/* Hidden mesh context */
typedef struct {
    facts_context_t *facts;
    
    /* Shared memory registry handle */
    registry_handle_t *registry_handle;
    shm_registry_t *registry;  /* Direct pointer for fast access */
    
    /* Options */
    int verbose;
    int parallel;
    const char *limit_pattern;
    
    /* Statistics */
    int namespaces_created;
    int interfaces_created;
    int bridges_created;
    int routes_added;
    int rules_added;
} mesh_context_t;

/* Create mesh context */
mesh_context_t* create_mesh_context() {
    mesh_context_t *ctx = calloc(1, sizeof(mesh_context_t));
    if (!ctx) return NULL;
    
    /* Open or create shared memory registry */
    ctx->registry_handle = open_shared_registry(0);  /* Don't force create */
    if (ctx->registry_handle) {
        ctx->registry = ctx->registry_handle->registry;
    }
    
    return ctx;
}

/* Free mesh context */
void free_mesh_context(mesh_context_t *ctx) {
    if (!ctx) return;
    
    if (ctx->registry_handle) {
        close_shared_registry(ctx->registry_handle);
    }
    
    free(ctx);
}

/* Initialize shared registry if needed */
int init_shared_registry(mesh_context_t *ctx) {
    if (!ctx->registry_handle) {
        ctx->registry_handle = open_shared_registry(0);
        if (!ctx->registry_handle) {
            fprintf(stderr, "Failed to open shared registry\n");
            return -1;
        }
        ctx->registry = ctx->registry_handle->registry;
    }
    return 0;
}

/* Get or create router code using shared memory */
const char* get_router_code(mesh_context_t *ctx, const char *router_name) {
    if (!ctx->registry) {
        if (init_shared_registry(ctx) != 0) return NULL;
    }
    return get_router_code_shm(ctx->registry, router_name);
}

/* Get next interface code using shared memory */
const char* get_interface_code(mesh_context_t *ctx, const char *router_code, const char *interface_name) {
    if (!ctx->registry) {
        if (init_shared_registry(ctx) != 0) return NULL;
    }
    return get_interface_code_shm(ctx->registry, router_code, interface_name);
}

/* Generate bridge name from subnet */
void generate_bridge_name(const char *subnet, char *bridge_name, size_t size) {
    /* Format: b + 12 octet digits + 2 prefix digits = 15 chars */
    /* e.g., 10.1.1.0/24 -> b010001001000024 */
    
    unsigned int o1, o2, o3, o4, prefix;
    if (sscanf(subnet, "%u.%u.%u.%u/%u", &o1, &o2, &o3, &o4, &prefix) == 5) {
        snprintf(bridge_name, size, "b%03u%03u%03u%03u%02u", 
                 o1, o2, o3, o4, prefix);
    } else {
        /* Fallback */
        snprintf(bridge_name, size, "bridge%lu", (unsigned long)time(NULL) % 10000);
    }
}

/* Forward declaration */
int create_namespace_safe_verbose(const char *ns_name, int verbose);

/* Check if namespace exists */
int namespace_exists(const char *ns_name) {
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ip netns list | grep -w %s > /dev/null 2>&1", ns_name);
    return (system(cmd) == 0);
}

/* Create namespace if not exists (backward compatibility) */
int create_namespace_safe(const char *ns_name) {
    return create_namespace_safe_verbose(ns_name, 0);
}

/* Create namespace if not exists */
int create_namespace_safe_verbose(const char *ns_name, int verbose) {
    if (namespace_exists(ns_name)) {
        if (strstr(ns_name, "hidden") || strstr(ns_name, "mesh")) {
            /* OK to reuse tsim namespaces */
            return 0;
        }
        if (verbose >= 1) {
            fprintf(stderr, "Warning: namespace %s already exists\n", ns_name);
        }
        return 0;
    }
    
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ip netns add %s", ns_name);
    
    if (system(cmd) != 0) {
        fprintf(stderr, "Failed to create namespace %s\n", ns_name);
        return -1;
    }
    
    /* Enable forwarding and loopback */
    snprintf(cmd, sizeof(cmd), "ip netns exec %s sysctl -w net.ipv4.ip_forward=1 > /dev/null 2>&1", ns_name);
    system(cmd);
    
    snprintf(cmd, sizeof(cmd), "ip netns exec %s sysctl -w net.ipv6.conf.all.forwarding=1 > /dev/null 2>&1", ns_name);
    system(cmd);
    
    snprintf(cmd, sizeof(cmd), "ip netns exec %s ip link set lo up", ns_name);
    system(cmd);
    
    return 0;
}

/* Print progress bar with status message */
void print_progress_with_status(int current, int total, const char *label, const char *status) {
    if (total <= 0) return;
    
    progress_active = 1;
    
    int percent = (current * 100) / total;
    int filled = (current * PROGRESS_BAR_WIDTH) / total;
    
    /* Move cursor to beginning of line */
    printf("\r");
    
    /* Print progress bar */
    printf("%s: [", label ? label : "Progress");
    
    for (int i = 0; i < PROGRESS_BAR_WIDTH; i++) {
        if (i < filled) {
            printf("=");
        } else if (i == filled) {
            printf(">");
        } else {
            printf(" ");
        }
    }
    
    printf("] %3d%% (%d/%d)", percent, current, total);
    
    /* Add status message if provided */
    if (status && strlen(status) > 0) {
        /* Calculate available space for status */
        int progress_len = strlen(label) + PROGRESS_BAR_WIDTH + 20; /* Approximate length */
        int available = terminal_width - progress_len - 2;
        
        if (available > 0) {
            printf(" ");
            if ((int)strlen(status) > available) {
                /* Truncate status if too long */
                printf("%.*s...", available - 3, status);
            } else {
                printf("%s", status);
            }
        }
    }
    
    /* Pad with spaces to clear any remaining characters from previous line */
    static int last_line_length = 0;
    int current_length = strlen(label) + PROGRESS_BAR_WIDTH + 20;
    if (status) current_length += strlen(status) + 1;
    
    for (int i = current_length; i < last_line_length; i++) {
        printf(" ");
    }
    last_line_length = current_length;
    
    if (current >= total) {
        printf("\n");
        progress_active = 0;
        last_line_length = 0;
    } else {
        fflush(stdout);
    }
}

/* Print progress bar (wrapper for compatibility) */
void print_progress(int current, int total, const char *label) {
    print_progress_with_status(current, total, label, NULL);
}

/* Create hidden mesh infrastructure */
int create_hidden_infrastructure(mesh_context_t *ctx) {
    if (ctx->verbose >= 1) {
        printf("Creating hidden mesh infrastructure...\n");
    }
    
    /* Create hidden namespace */
    if (create_namespace_safe_verbose(HIDDEN_NS, ctx->verbose) != 0) {
        return -1;
    }
    
    /* Extract all subnets from interfaces */
    int subnet_count = 0;
    char subnets[MAX_BRIDGES][32];
    
    for (size_t i = 0; i < ctx->facts->router_count && !interrupted; i++) {
        router_t *router = ctx->facts->routers[i];
        
        for (size_t j = 0; j < router->interface_count && !interrupted; j++) {
            interface_t *iface = &router->interfaces[j];
            
            for (size_t k = 0; k < iface->addr_count; k++) {
                /* Calculate subnet from IP address */
                char subnet[32];
                struct in_addr addr;
                unsigned int prefix = 24;  /* default */
                
                /* Parse IP/prefix */
                char ip_copy[64];
                strncpy(ip_copy, iface->addresses[k].ip, sizeof(ip_copy) - 1);
                char *slash = strchr(ip_copy, '/');
                if (slash) {
                    *slash = '\0';
                    prefix = atoi(slash + 1);
                }
                
                if (inet_pton(AF_INET, ip_copy, &addr) == 1) {
                    /* Calculate network address */
                    unsigned int mask = (0xFFFFFFFF << (32 - prefix));
                    addr.s_addr &= htonl(mask);
                    
                    snprintf(subnet, sizeof(subnet), "%s/%u", 
                            inet_ntoa(addr), prefix);
                    
                    /* Check if subnet already in list */
                    int found = 0;
                    for (int s = 0; s < subnet_count; s++) {
                        if (strcmp(subnets[s], subnet) == 0) {
                            found = 1;
                            break;
                        }
                    }
                    
                    if (!found && subnet_count < MAX_BRIDGES) {
                        strcpy(subnets[subnet_count++], subnet);
                    }
                }
            }
        }
    }
    
    if (ctx->verbose >= 1) {
        printf("  Creating %d subnet bridges\n", subnet_count);
    }
    
    /* Ensure registry is initialized */
    if (!ctx->registry) {
        if (init_shared_registry(ctx) != 0) {
            fprintf(stderr, "Failed to initialize shared registry\n");
            return -1;
        }
    }
    
    /* Create bridges for each subnet */
    for (int i = 0; i < subnet_count && !interrupted; i++) {
        char bridge_name[MAX_BRIDGE_NAME];
        generate_bridge_name(subnets[i], bridge_name, sizeof(bridge_name));
        
        /* Register in shared memory */
        int bridge_idx = register_bridge_shm(ctx->registry, bridge_name, subnets[i]);
        if (bridge_idx >= 0) {
            shm_bridge_entry_t *bridge = &ctx->registry->bridges[bridge_idx];
            
            /* Create bridge in hidden namespace if not already created */
            if (!bridge->created) {
                char cmd[512];
                snprintf(cmd, sizeof(cmd), 
                        "ip netns exec %s ip link add %s type bridge 2>/dev/null", 
                        HIDDEN_NS, bridge_name);
                
                if (system(cmd) == 0) {
                    bridge->created = 1;
                    ctx->bridges_created++;
                    
                    /* Bring bridge up */
                    snprintf(cmd, sizeof(cmd), 
                            "ip netns exec %s ip link set %s up", 
                            HIDDEN_NS, bridge_name);
                    system(cmd);
                    
                    if (ctx->verbose >= 2) {
                        printf("    Created bridge %s for %s\n", bridge_name, subnets[i]);
                    }
                } else if (ctx->verbose >= 2) {
                    printf("    Bridge %s already exists\n", bridge_name);
                }
            }
        }
    }
    
    return 0;
}

/* Setup router with veth pairs */
int setup_router_with_veth(mesh_context_t *ctx, router_t *router) {
    /* Check for interrupt before starting */
    if (interrupted) {
        return -1;
    }
    
    const char *ns = router->name;
    const char *router_code = get_router_code(ctx, ns);
    
    if (!router_code) {
        fprintf(stderr, "Failed to get router code for %s\n", ns);
        return -1;
    }
    
    if (ctx->verbose >= 1) {
        printf("Setting up router: %s (code: %s)\n", ns, router_code);
    }
    
    /* Create namespace */
    if (create_namespace_safe_verbose(ns, ctx->verbose) != 0) {
        return -1;
    }
    ctx->namespaces_created++;
    
    /* Create batch context */
    batch_context_t *batch = create_batch_context(1024 * 1024);
    if (!batch) {
        fprintf(stderr, "Failed to create batch context for %s\n", ns);
        return -1;
    }
    
    /* Flush existing ipsets before applying new ones */
    batch_add_command(batch, ns, "ipset flush 2>/dev/null || true");
    batch_add_command(batch, ns, "ipset destroy 2>/dev/null || true");
    
    /* Create veth pairs for each interface */
    for (size_t i = 0; i < router->interface_count && !interrupted; i++) {
        interface_t *iface = &router->interfaces[i];
        
        /* Skip loopback */
        if (strcmp(iface->name, "lo") == 0) {
            continue;
        }
        
        /* Generate veth pair names */
        const char *iface_code = get_interface_code(ctx, router_code, iface->name);
        char veth_router[16], veth_hidden[16];
        
        snprintf(veth_router, sizeof(veth_router), "%s%sr", router_code, iface_code);
        snprintf(veth_hidden, sizeof(veth_hidden), "%s%sh", router_code, iface_code);
        
        /* Create veth pair in host namespace */
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s 2>/dev/null", 
                veth_router, veth_hidden);
        
        if (system(cmd) == 0) {
            ctx->interfaces_created++;
            
            /* Move router end to router namespace and rename to actual interface name */
            snprintf(cmd, sizeof(cmd), "ip link set %s netns %s", veth_router, ns);
            system(cmd);
            
            snprintf(cmd, sizeof(cmd), "ip link set %s name %s", veth_router, iface->name);
            batch_add_command(batch, ns, cmd);
            
            /* Move hidden end to hidden namespace */
            snprintf(cmd, sizeof(cmd), "ip link set %s netns %s", veth_hidden, HIDDEN_NS);
            system(cmd);
            
            /* Find appropriate bridge for this interface */
            for (size_t j = 0; j < iface->addr_count; j++) {
                char ip_copy[64];
                strncpy(ip_copy, iface->addresses[j].ip, sizeof(ip_copy) - 1);
                char *slash = strchr(ip_copy, '/');
                unsigned int prefix = 24;
                if (slash) {
                    *slash = '\0';
                    prefix = atoi(slash + 1);
                }
                
                struct in_addr addr;
                if (inet_pton(AF_INET, ip_copy, &addr) == 1) {
                    unsigned int mask = (0xFFFFFFFF << (32 - prefix));
                    addr.s_addr &= htonl(mask);
                    char subnet[32];
                    snprintf(subnet, sizeof(subnet), "%s/%u", inet_ntoa(addr), prefix);
                    
                    /* Find bridge for this subnet in shared memory */
                    shm_bridge_entry_t *bridge = find_bridge_by_subnet(ctx->registry, subnet);
                    if (bridge) {
                        /* Attach veth to bridge */
                        snprintf(cmd, sizeof(cmd), 
                                "ip netns exec %s ip link set %s master %s", 
                                HIDDEN_NS, veth_hidden, bridge->bridge_name);
                        system(cmd);
                        
                        snprintf(cmd, sizeof(cmd), 
                                "ip netns exec %s ip link set %s up", 
                                HIDDEN_NS, veth_hidden);
                        system(cmd);
                    }
                    break;  /* Only need to find bridge once per interface */
                }
            }
            
            /* Configure interface in router namespace */
            
            /* Set MAC if specified */
            if (iface->mac) {
                snprintf(cmd, sizeof(cmd), "ip link set %s address %s", iface->name, iface->mac);
                batch_add_command(batch, ns, cmd);
            }
            
            /* Add IP addresses */
            for (size_t j = 0; j < iface->addr_count; j++) {
                address_t *addr = &iface->addresses[j];
                snprintf(cmd, sizeof(cmd), "ip addr add %s brd %s dev %s", 
                        addr->ip, addr->broadcast ? addr->broadcast : "+", iface->name);
                batch_add_command(batch, ns, cmd);
            }
            
            /* Bring interface up */
            if (iface->up) {
                snprintf(cmd, sizeof(cmd), "ip link set %s up", iface->name);
                batch_add_command(batch, ns, cmd);
            }
            
            /* Set MTU if not default */
            if (iface->mtu && iface->mtu != 1500) {
                snprintf(cmd, sizeof(cmd), "ip link set %s mtu %d", iface->name, iface->mtu);
                batch_add_command(batch, ns, cmd);
            }
        }
    }
    
    /* Execute raw routing commands verbatim */
    for (size_t i = 0; i < router->raw_route_count && !interrupted; i++) {
        char cmd[1024];
        snprintf(cmd, sizeof(cmd), "%s 2>/dev/null || true", router->raw_route_commands[i]);
        batch_add_command(batch, ns, cmd);
        ctx->routes_added++;
    }
    
    /* Add ALL policy rules - NO FILTERING */
    for (size_t i = 0; i < router->rule_count && !interrupted; i++) {
        rule_t *rule = &router->rules[i];
        char cmd[512];
        
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
        
        if (rule->table) {
            strcat(cmd, " lookup ");
            strcat(cmd, rule->table);
        }
        
        strcat(cmd, " 2>/dev/null || true");
        batch_add_command(batch, ns, cmd);
        ctx->rules_added++;
    }
    
    /* Execute batch */
    if (ctx->verbose >= 1) {
        printf("  Executing configuration...\n");
    }
    batch_execute_verbose(batch, ctx->verbose);
    
    /* Apply ipsets */
    if (router->ipset_save.raw_content && router->ipset_save.content_size > 0) {
        if (ctx->verbose >= 1) {
            printf("  Applying ipsets (%zu bytes)...\n", router->ipset_save.content_size);
        }
        apply_ipset_with_shm(ns, &router->ipset_save);
    }
    
    /* Apply iptables */
    if (router->iptables_save.raw_content && router->iptables_save.content_size > 0) {
        if (ctx->verbose >= 1) {
            printf("  Applying iptables (%zu bytes)...\n", router->iptables_save.content_size);
        }
        apply_iptables_with_shm(ns, &router->iptables_save);
    }
    
    free_batch_context(batch);
    if (ctx->verbose >= 1) {
        printf("  Router %s setup complete\n", ns);
    }
    
    return 0;
}

/* Cleanup all namespaces */
void cleanup_namespaces(mesh_context_t *ctx) {
    if (ctx->verbose >= 1) {
        printf("Cleaning up namespaces...\n");
    }
    
    /* Clear and remove shared registry */
    if (ctx->registry) {
        clear_shared_registry(ctx->registry);
    }
    if (ctx->registry_handle) {
        close_shared_registry(ctx->registry_handle);
        ctx->registry_handle = NULL;
        ctx->registry = NULL;
        /* Remove the shared memory file */
        shm_unlink(REGISTRY_SHM_NAME);
    }
    
    /* Delete all router namespaces */
    for (size_t i = 0; i < ctx->facts->router_count; i++) {
        router_t *router = ctx->facts->routers[i];
        char cmd[512];
        
        /* Flush ipsets first */
        snprintf(cmd, sizeof(cmd), "ip netns exec %s ipset flush 2>/dev/null || true", router->name);
        system(cmd);
        
        snprintf(cmd, sizeof(cmd), "ip netns exec %s ipset destroy 2>/dev/null || true", router->name);
        system(cmd);
        
        /* Delete namespace */
        snprintf(cmd, sizeof(cmd), "ip netns del %s 2>/dev/null", router->name);
        system(cmd);
    }
    
    /* Delete hidden namespace */
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ip netns del %s 2>/dev/null", HIDDEN_NS);
    system(cmd);
}

/* Main setup function */
int main(int argc, char *argv[]) {
    /* Install signal handler */
    signal(SIGINT, sigint_handler);
    
    /* Get terminal width */
    terminal_width = get_terminal_width();
    
    mesh_context_t *ctx = create_mesh_context();
    if (!ctx) {
        fprintf(stderr, "Failed to create mesh context\n");
        return 1;
    }
    
    /* Parse arguments */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--verbose") == 0) {
            ctx->verbose++;
        } else if (strcmp(argv[i], "-p") == 0 || strcmp(argv[i], "--parallel") == 0) {
            ctx->parallel = 1;
        } else if (strcmp(argv[i], "--limit") == 0 && i + 1 < argc) {
            ctx->limit_pattern = argv[++i];
        } else if (strcmp(argv[i], "--cleanup") == 0) {
            /* Load facts first to know what to clean - respect limit if provided */
            if (load_facts_from_env_filtered(&ctx->facts, ctx->verbose, ctx->limit_pattern) == 0) {
                cleanup_namespaces(ctx);
            }
            free_mesh_context(ctx);
            return 0;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            printf("Usage: %s [options]\n", argv[0]);
            printf("Options:\n");
            printf("  -v, --verbose     Increase verbosity\n");
            printf("  -p, --parallel    Setup routers in parallel\n");
            printf("  --limit PATTERN   Only setup routers matching pattern\n");
            printf("  --cleanup         Clean up existing setup\n");
            printf("  -h, --help        Show this help\n");
            free_mesh_context(ctx);
            return 0;
        }
    }
    
    /* Check if running as root */
    if (geteuid() != 0) {
        fprintf(stderr, "This program must be run as root\n");
        free_mesh_context(ctx);
        return 1;
    }
    
    /* Load facts - filtered if limit pattern provided */
    if (ctx->verbose >= 1) {
        if (ctx->limit_pattern) {
            printf("Loading router facts (filtered by '%s')...\n", ctx->limit_pattern);
        } else {
            printf("Loading router facts...\n");
        }
    }
    if (load_facts_from_env_filtered(&ctx->facts, ctx->verbose, ctx->limit_pattern) != 0) {
        fprintf(stderr, "Failed to load facts\n");
        free_mesh_context(ctx);
        return 1;
    }
    
    if (ctx->verbose >= 1) {
        printf("Loaded %zu routers\n", ctx->facts->router_count);
    }
    
    /* Initialize shared registry */
    if (init_shared_registry(ctx) != 0) {
        fprintf(stderr, "Warning: Could not initialize shared registry\n");
    }
    
    /* Create hidden infrastructure first */
    if (create_hidden_infrastructure(ctx) != 0) {
        if (interrupted) {
            fprintf(stderr, "\nSetup interrupted by user\n");
        } else {
            fprintf(stderr, "Failed to create hidden infrastructure\n");
        }
        free_mesh_context(ctx);
        return 1;
    }
    
    /* Check for early interrupt */
    if (interrupted) {
        fprintf(stderr, "\nSetup interrupted by user\n");
        free_facts_context(ctx->facts);
        free_mesh_context(ctx);
        return 130;  /* Standard exit code for SIGINT */
    }
    
    /* Count routers to setup - all facts are already filtered */
    size_t routers_to_setup = ctx->facts->router_count;
    
    /* Setup routers */
    if (ctx->parallel) {
        /* Parallel setup using fork */
        if (ctx->verbose >= 1) {
            printf("Setting up routers in parallel...\n");
        } else if (routers_to_setup > 0) {
            printf("Setting up %zu routers...\n", routers_to_setup);
        }
        
        size_t batch_size = 10;
        for (size_t i = 0; i < ctx->facts->router_count; i += batch_size) {
            /* Check for interrupt BEFORE starting next batch */
            if (interrupted) {
                fprintf(stderr, "\nSetup interrupted by user\n");
                break;
            }
            
            size_t end = i + batch_size;
            if (end > ctx->facts->router_count) end = ctx->facts->router_count;
            
            pid_t pid = fork();
            if (pid == 0) {
                /* Child process - install signal handler in child too */
                signal(SIGINT, sigint_handler);
                for (size_t j = i; j < end; j++) {
                    if (interrupted) break;
                    router_t *router = ctx->facts->routers[j];
                    setup_router_with_veth(ctx, router);
                }
                exit(0);
            }
        }
        
        /* Wait for all children */
        int status;
        while (wait(&status) > 0) {
            if (interrupted) {
                /* Kill remaining children */
                kill(0, SIGTERM);
                break;
            }
        }
        
    } else {
        /* Sequential setup */
        if (ctx->verbose >= 1) {
            printf("Setting up routers sequentially...\n");
        } else if (routers_to_setup > 0) {
            printf("Setting up %zu routers...\n", routers_to_setup);
        }
        
        size_t routers_done = 0;
        for (size_t i = 0; i < ctx->facts->router_count; i++) {
            /* Check for interrupt BEFORE starting next router */
            if (interrupted) {
                if (ctx->verbose == 0) printf("\n");
                fprintf(stderr, "\nSetup interrupted by user\n");
                break;
            }
            
            router_t *router = ctx->facts->routers[i];
            
            setup_router_with_veth(ctx, router);
            routers_done++;
            
            /* Update progress bar */
            if (ctx->verbose == 0 && routers_to_setup > 0) {
                char status[256];
                snprintf(status, sizeof(status), "[%s]", router->name);
                print_progress_with_status(routers_done, routers_to_setup, "Routers", status);
            }
        }
    }
    
    /* Registry is automatically persistent in shared memory */
    
    /* Print summary */
    printf("\n=== Setup Summary ===\n");
    printf("Namespaces created: %d\n", ctx->namespaces_created);
    printf("Interfaces created: %d\n", ctx->interfaces_created);
    printf("Bridges created: %d\n", ctx->bridges_created);
    printf("Routes added: %d\n", ctx->routes_added);
    printf("Rules added: %d\n", ctx->rules_added);
    
    int exit_code = 0;
    if (interrupted) {
        printf("\n*** Setup was interrupted by user ***\n");
        exit_code = 130;  /* Standard exit code for SIGINT */
    } else {
        printf("\nNetwork setup complete!\n");
    }
    
    free_facts_context(ctx->facts);
    free_mesh_context(ctx);
    
    return exit_code;
}