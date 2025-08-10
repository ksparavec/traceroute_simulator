/* _GNU_SOURCE already defined in Makefile */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <errno.h>
#include <ctype.h>
#include <sys/stat.h>
#include <time.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include "router_facts_loader.h"

/* External environ for execve */
extern char **environ;

/* Dynamic array growth factor */
#define GROWTH_FACTOR 2
#define INITIAL_CAPACITY 16

/* Memory allocation helpers */
static void* realloc_safe(void *ptr, size_t size) {
    void *new_ptr = realloc(ptr, size);
    if (!new_ptr && size > 0) {
        free(ptr);
        return NULL;
    }
    return new_ptr;
}

char* strdup_safe(const char *str) {
    if (!str) return NULL;
    char *copy = strdup(str);
    if (!copy) {
        fprintf(stderr, "Memory allocation failed for string duplication\n");
    }
    return copy;
}

/* Create and initialize facts context */
facts_context_t* create_facts_context(void) {
    facts_context_t *ctx = calloc(1, sizeof(facts_context_t));
    if (!ctx) return NULL;
    
    ctx->router_capacity = INITIAL_CAPACITY;
    ctx->routers = calloc(ctx->router_capacity, sizeof(router_t*));
    if (!ctx->routers) {
        free(ctx);
        return NULL;
    }
    
    return ctx;
}

/* Free facts context and all associated memory */
void free_facts_context(facts_context_t *ctx) {
    if (!ctx) return;
    
    for (size_t i = 0; i < ctx->router_count; i++) {
        free_router(ctx->routers[i]);
    }
    free(ctx->routers);
    free(ctx->facts_dir);
    free(ctx);
}

/* Create and initialize router */
router_t* create_router(const char *name) {
    router_t *router = calloc(1, sizeof(router_t));
    if (!router) return NULL;
    
    router->name = strdup_safe(name);
    if (!router->name) {
        free(router);
        return NULL;
    }
    
    router->interface_capacity = INITIAL_CAPACITY;
    router->interfaces = calloc(router->interface_capacity, sizeof(interface_t));
    
    router->route_capacity = INITIAL_CAPACITY * 4;  // Routes are usually more numerous
    router->routes = calloc(router->route_capacity, sizeof(route_t));
    
    router->rule_capacity = INITIAL_CAPACITY;
    router->rules = calloc(router->rule_capacity, sizeof(rule_t));
    
    /* Initialize empty iptables/ipset blocks */
    router->iptables_save.raw_content = NULL;
    router->iptables_save.content_size = 0;
    router->ipset_save.raw_content = NULL;
    router->ipset_save.content_size = 0;
    
    return router;
}

/* Free router and all associated memory */
void free_router(router_t *router) {
    if (!router) return;
    
    /* Free interfaces */
    for (size_t i = 0; i < router->interface_count; i++) {
        interface_t *iface = &router->interfaces[i];
        free(iface->name);
        free(iface->mac);
        for (size_t j = 0; j < iface->addr_count; j++) {
            free(iface->addresses[j].ip);
            free(iface->addresses[j].broadcast);
            free(iface->addresses[j].scope);
        }
        free(iface->addresses);
    }
    free(router->interfaces);
    
    /* Free routes */
    for (size_t i = 0; i < router->route_count; i++) {
        route_t *route = &router->routes[i];
        free(route->destination);
        free(route->gateway);
        free(route->device);
        free(route->source);
        free(route->table);
        free(route->protocol);
        free(route->scope);
    }
    free(router->routes);
    
    /* Free raw route commands */
    for (size_t i = 0; i < router->raw_route_count; i++) {
        free(router->raw_route_commands[i]);
    }
    free(router->raw_route_commands);
    
    /* Free rules */
    for (size_t i = 0; i < router->rule_count; i++) {
        rule_t *rule = &router->rules[i];
        free(rule->from);
        free(rule->to);
        free(rule->iif);
        free(rule->oif);
        free(rule->table);
        free(rule->protocol);
    }
    free(router->rules);
    
    /* Free raw iptables/ipset blocks */
    free(router->iptables_save.raw_content);
    free(router->ipset_save.raw_content);
    
    free(router->name);
    free(router->raw_facts_path);
    free(router);
}

/* Add interface to router */
interface_t* add_interface(router_t *router) {
    if (router->interface_count >= router->interface_capacity) {
        size_t new_capacity = router->interface_capacity * GROWTH_FACTOR;
        interface_t *new_interfaces = realloc_safe(router->interfaces, 
                                                   new_capacity * sizeof(interface_t));
        if (!new_interfaces) return NULL;
        
        router->interfaces = new_interfaces;
        router->interface_capacity = new_capacity;
        memset(&router->interfaces[router->interface_count], 0, 
               (new_capacity - router->interface_count) * sizeof(interface_t));
    }
    
    interface_t *iface = &router->interfaces[router->interface_count++];
    iface->addr_capacity = INITIAL_CAPACITY;
    iface->addresses = calloc(iface->addr_capacity, sizeof(address_t));
    return iface;
}

/* Add address to interface */
address_t* add_address(interface_t *iface) {
    if (iface->addr_count >= iface->addr_capacity) {
        size_t new_capacity = iface->addr_capacity * GROWTH_FACTOR;
        address_t *new_addresses = realloc_safe(iface->addresses,
                                                new_capacity * sizeof(address_t));
        if (!new_addresses) return NULL;
        
        iface->addresses = new_addresses;
        iface->addr_capacity = new_capacity;
        memset(&iface->addresses[iface->addr_count], 0,
               (new_capacity - iface->addr_count) * sizeof(address_t));
    }
    
    return &iface->addresses[iface->addr_count++];
}

/* Add route to router */
route_t* add_route(router_t *router) {
    if (router->route_count >= router->route_capacity) {
        size_t new_capacity = router->route_capacity * GROWTH_FACTOR;
        route_t *new_routes = realloc_safe(router->routes,
                                           new_capacity * sizeof(route_t));
        if (!new_routes) return NULL;
        
        router->routes = new_routes;
        router->route_capacity = new_capacity;
        memset(&router->routes[router->route_count], 0,
               (new_capacity - router->route_count) * sizeof(route_t));
    }
    
    return &router->routes[router->route_count++];
}

/* Add rule to router */
rule_t* add_rule(router_t *router) {
    if (router->rule_count >= router->rule_capacity) {
        size_t new_capacity = router->rule_capacity * GROWTH_FACTOR;
        rule_t *new_rules = realloc_safe(router->rules,
                                         new_capacity * sizeof(rule_t));
        if (!new_rules) return NULL;
        
        router->rules = new_rules;
        router->rule_capacity = new_capacity;
        memset(&router->rules[router->rule_count], 0,
               (new_capacity - router->rule_count) * sizeof(rule_t));
    }
    
    return &router->rules[router->rule_count++];
}

/* Find section in raw facts content */
char* find_section(const char *content, const char *section_name) {
    char start_marker[256];
    char end_marker[256];
    
    snprintf(start_marker, sizeof(start_marker), "=== TSIM_SECTION_START:%s ===", section_name);
    snprintf(end_marker, sizeof(end_marker), "=== TSIM_SECTION_END:%s ===", section_name);
    
    char *start = strstr(content, start_marker);
    if (!start) return NULL;
    
    /* Move past the marker and find the actual content after "---" */
    start = strstr(start, "---");
    if (!start) return NULL;
    start += 4;  /* Skip "---\n" */
    
    /* Find EXIT_CODE line first, then the end marker */
    char *exit_code = strstr(start, "\nEXIT_CODE:");
    char *end = strstr(start, end_marker);
    
    /* Use EXIT_CODE position if it comes before end marker */
    if (exit_code && (!end || exit_code < end)) {
        end = exit_code;
    } else if (!end) {
        return NULL;
    }
    
    /* Trim trailing whitespace */
    while (end > start && (*(end-1) == '\n' || *(end-1) == '\r' || *(end-1) == ' ' || *(end-1) == '\t')) {
        end--;
    }
    
    /* Allocate and copy the section content */
    size_t len = end - start;
    if (len == 0) {
        /* Empty section - return empty string, not NULL */
        char *section = malloc(1);
        if (section) section[0] = '\0';
        return section;
    }
    
    char *section = malloc(len + 1);
    if (!section) return NULL;
    
    memcpy(section, start, len);
    section[len] = '\0';
    
    return section;
}

/* Parse interfaces section from raw facts */
int parse_interfaces_section(const char *content, router_t *router) {
    char *section = find_section(content, "interfaces");
    if (!section) return -1;
    
    /* Use strtok_r for thread safety and to handle multi-line parsing */
    char *saveptr = NULL;
    char *line = strtok_r(section, "\n", &saveptr);
    interface_t *current_iface = NULL;
    
    while (line) {
        /* Skip empty lines and EXIT_CODE lines */
        if (!*line || strstr(line, "EXIT_CODE:")) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Check if line starts with a number (interface index) */
        /* Format: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP" */
        /* Or with @ for vlan: "3: eth0.100@eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500" */
        if (isdigit(line[0])) {
            /* Find first colon */
            char *first_colon = strchr(line, ':');
            if (first_colon) {
                /* Skip spaces after colon */
                char *name_start = first_colon + 1;
                while (*name_start && isspace(*name_start)) name_start++;
                
                /* Find end of interface name (either : or @) */
                char *name_end = name_start;
                while (*name_end && *name_end != ':' && *name_end != '@') name_end++;
                
                if (*name_end) {
                    /* Extract interface name */
                    size_t name_len = name_end - name_start;
                    char iface_name[MAX_NAME_LEN] = {0};
                    if (name_len < MAX_NAME_LEN) {
                        strncpy(iface_name, name_start, name_len);
                        iface_name[name_len] = '\0';
                        
                        /* Include loopback interface */
                        
                        /* Create new interface */
                        current_iface = add_interface(router);
                        if (current_iface) {
                            current_iface->name = strdup_safe(iface_name);
                            
                            /* Find flags section <...> */
                            char *flags_start = strchr(name_end, '<');
                            char *flags_end = flags_start ? strchr(flags_start, '>') : NULL;
                            
                            if (flags_start && flags_end) {
                                /* Parse flags */
                                char *flags_section = flags_start + 1;
                                *flags_end = '\0';
                                
                                /* Check for UP flag in flags section */
                                if (strstr(flags_section, "UP")) {
                                    current_iface->up = 1;
                                }
                                
                                /* Restore the > character */
                                *flags_end = '>';
                            }
                            
                            /* Parse remaining properties after flags */
                            char *props = flags_end ? flags_end + 1 : name_end + 1;
                            
                            /* Extract MTU */
                            char *mtu_str = strstr(props, "mtu ");
                            if (mtu_str) {
                                current_iface->mtu = atoi(mtu_str + 4);
                            } else {
                                current_iface->mtu = 1500; /* Default MTU */
                            }
                            
                            /* Check state field to override UP flag if interface is DOWN */
                            char *state_str = strstr(props, "state ");
                            if (state_str) {
                                state_str += 6;
                                if (strncmp(state_str, "DOWN", 4) == 0) {
                                    current_iface->up = 0;
                                }
                            }
                        }
                    }
                }
            }
        }
        /* Parse link line - handles various link types */
        else if (current_iface && strstr(line, "link/")) {
            /* Trim leading spaces */
            char *trimmed = line;
            while (*trimmed && isspace(*trimmed)) trimmed++;
            
            /* link/ether for ethernet */
            if (strstr(trimmed, "link/ether")) {
                char *mac = strstr(trimmed, "link/ether");
                if (mac) {
                    mac += 11;  /* Skip "link/ether " */
                    char mac_addr[18] = {0};
                    sscanf(mac, "%17s", mac_addr);
                    current_iface->mac = strdup_safe(mac_addr);
                }
            }
            /* link/loopback for lo */
            else if (strstr(trimmed, "link/loopback")) {
                /* Loopback link type */
            }
            /* link/none for some virtual interfaces */
            else if (strstr(trimmed, "link/none")) {
                /* No MAC address for these interfaces */
            }
        }
        /* Parse inet address lines (IPv4) */
        else if (current_iface && strstr(line, "inet ")) {
            /* Trim leading spaces */
            char *trimmed = line;
            while (*trimmed && isspace(*trimmed)) trimmed++;
            
            char *inet = strstr(trimmed, "inet ");
            if (inet) {
                inet += 5;  /* Skip "inet " */
                
                /* Parse IP address with CIDR */
                char ip_addr[MAX_IP_LEN] = {0};
                if (sscanf(inet, "%s", ip_addr) == 1) {
                    /* Validate it contains a / for CIDR notation */
                    if (strchr(ip_addr, '/')) {
                        address_t *addr = add_address(current_iface);
                        if (addr) {
                            addr->ip = strdup_safe(ip_addr);
                            
                            /* Extract broadcast if present */
                            char *brd = strstr(inet, "brd ");
                            if (brd) {
                                brd += 4;
                                char brd_addr[MAX_IP_LEN] = {0};
                                if (sscanf(brd, "%s", brd_addr) == 1) {
                                    addr->broadcast = strdup_safe(brd_addr);
                                }
                            }
                            
                            /* Extract scope */
                            char *scope = strstr(inet, "scope ");
                            if (scope) {
                                scope += 6;
                                char scope_str[32] = {0};
                                if (sscanf(scope, "%31s", scope_str) == 1) {
                                    addr->scope = strdup_safe(scope_str);
                                } else {
                                    addr->scope = strdup_safe("global");
                                }
                            } else {
                                addr->scope = strdup_safe("global");
                            }
                            
                            /* Check for secondary flag */
                            if (strstr(inet, "secondary")) {
                                addr->secondary = 1;
                            }
                            
                            /* Extract prefix length from CIDR */
                            char *slash = strchr(ip_addr, '/');
                            if (slash) {
                                addr->prefixlen = atoi(slash + 1);
                            }
                        }
                    }
                }
            }
        }
        /* Parse inet6 address lines (IPv6) */
        else if (current_iface && strstr(line, "inet6 ")) {
            /* Trim leading spaces */
            char *trimmed = line;
            while (*trimmed && isspace(*trimmed)) trimmed++;
            
            char *inet6 = strstr(trimmed, "inet6 ");
            if (inet6) {
                inet6 += 6;  /* Skip "inet6 " */
                
                /* Parse IPv6 address with prefix */
                char ip_addr[MAX_IP_LEN] = {0};
                if (sscanf(inet6, "%s", ip_addr) == 1) {
                    /* Skip link-local addresses if needed */
                    if (!strstr(ip_addr, "fe80:")) {
                        address_t *addr = add_address(current_iface);
                        if (addr) {
                            addr->ip = strdup_safe(ip_addr);
                            
                            /* Extract scope for IPv6 */
                            char *scope = strstr(inet6, "scope ");
                            if (scope) {
                                scope += 6;
                                char scope_str[32] = {0};
                                if (sscanf(scope, "%31s", scope_str) == 1) {
                                    addr->scope = strdup_safe(scope_str);
                                } else {
                                    addr->scope = strdup_safe("global");
                                }
                            } else {
                                addr->scope = strdup_safe("global");
                            }
                            
                            /* Extract prefix length from address */
                            char *slash = strchr(ip_addr, '/');
                            if (slash) {
                                addr->prefixlen = atoi(slash + 1);
                            }
                        }
                    }
                }
            }
        }
        
        line = strtok_r(NULL, "\n", &saveptr);
    }
    
    free(section);
    return 0;
}

/* Extract raw routing commands without parsing */
int extract_routing_commands(const char *content, const char *table_name, router_t *router) {
    char section_name[256];
    if (strcmp(table_name, "main") == 0) {
        strcpy(section_name, "routing_table");
    } else {
        snprintf(section_name, sizeof(section_name), "routing_table_%s", table_name);
    }
    
    printf("DEBUG: Looking for section '%s' for router %s\n", section_name, router->name);
    char *section = find_section(content, section_name);
    if (!section) {
        printf("DEBUG: Section '%s' not found\n", section_name);
        return -1;
    }
    printf("DEBUG: Found section '%s', processing lines...\n", section_name);
    
    /* Use strtok_r for thread safety */
    char *saveptr = NULL;
    char *line = strtok_r(section, "\n", &saveptr);
    
    while (line) {
        /* Skip empty lines and EXIT_CODE lines */
        if (!*line || strstr(line, "EXIT_CODE:")) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Trim leading/trailing spaces */
        while (*line && isspace(*line)) line++;
        char *line_end = line + strlen(line) - 1;
        while (line_end > line && isspace(*line_end)) *line_end-- = '\0';
        
        if (!*line) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Grow array if needed */
        if (router->raw_route_count >= router->raw_route_capacity) {
            size_t new_capacity = router->raw_route_capacity ? router->raw_route_capacity * 2 : 16;
            char **new_commands = realloc(router->raw_route_commands, new_capacity * sizeof(char*));
            if (!new_commands) {
                line = strtok_r(NULL, "\n", &saveptr);
                continue;
            }
            router->raw_route_commands = new_commands;
            router->raw_route_capacity = new_capacity;
        }
        
        /* Build ip route add command for this line */
        char cmd[1024];
        snprintf(cmd, sizeof(cmd), "ip route add %s", line);
        
        /* Add table parameter if not main */
        if (strcmp(table_name, "main") != 0) {
            strcat(cmd, " table ");
            strcat(cmd, table_name);
        }
        
        /* Store the command */
        router->raw_route_commands[router->raw_route_count++] = strdup(cmd);
        printf("DEBUG: Added route command [%zu]: %s\n", router->raw_route_count - 1, cmd);
        
        line = strtok_r(NULL, "\n", &saveptr);
    }
    
    printf("DEBUG: Extracted %zu route commands from section '%s'\n", router->raw_route_count, section_name);
    free(section);
    return 0;
}

/* Parse routing table section */
int parse_routing_section(const char *content, const char *table_name, router_t *router) {
    char section_name[256];
    if (strcmp(table_name, "main") == 0) {
        strcpy(section_name, "routing_table");
    } else {
        snprintf(section_name, sizeof(section_name), "routing_table_%s", table_name);
    }
    
    char *section = find_section(content, section_name);
    if (!section) return -1;
    
    /* Use strtok_r for thread safety */
    char *saveptr = NULL;
    char *line = strtok_r(section, "\n", &saveptr);
    
    while (line) {
        /* Skip empty lines and EXIT_CODE lines */
        if (!*line || strstr(line, "EXIT_CODE:")) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Trim leading/trailing spaces */
        while (*line && isspace(*line)) line++;
        char *line_end = line + strlen(line) - 1;
        while (line_end > line && isspace(*line_end)) *line_end-- = '\0';
        
        if (!*line) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        route_t *route = add_route(router);
        if (!route) {
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Parse route line */
        char dest[MAX_IP_LEN] = {0};
        char gw[MAX_IP_LEN] = {0};
        char dev[MAX_NAME_LEN] = {0};
        char src[MAX_IP_LEN] = {0};
        char proto[32] = {0};
        char scope[32] = {0};
        int metric = 0;
        
        /* Handle different route formats */
        /* Format 1: "default via 10.1.1.1 dev eth0" */
        /* Format 2: "10.1.1.0/24 dev eth0 proto kernel scope link src 10.1.1.2" */
        /* Format 3: "10.2.0.0/16 via 10.1.1.1 dev eth0 metric 10" */
        /* Format 4: "unreachable 192.168.100.0/24" */
        /* Format 5: "blackhole 192.168.200.0/24" */
        /* Format 6: "prohibit 192.168.300.0/24" */
        
        /* Check for special route types */
        if (strncmp(line, "unreachable ", 12) == 0) {
            sscanf(line + 12, "%s", dest);
            route->destination = strdup_safe(dest);
            route->protocol = strdup_safe("unreachable");
            route->table = strdup_safe(table_name);
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        } else if (strncmp(line, "blackhole ", 10) == 0) {
            sscanf(line + 10, "%s", dest);
            route->destination = strdup_safe(dest);
            route->protocol = strdup_safe("blackhole");
            route->table = strdup_safe(table_name);
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        } else if (strncmp(line, "prohibit ", 9) == 0) {
            sscanf(line + 9, "%s", dest);
            route->destination = strdup_safe(dest);
            route->protocol = strdup_safe("prohibit");
            route->table = strdup_safe(table_name);
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        } else if (strncmp(line, "throw ", 6) == 0) {
            sscanf(line + 6, "%s", dest);
            route->destination = strdup_safe(dest);
            route->protocol = strdup_safe("throw");
            route->table = strdup_safe(table_name);
            line = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        /* Handle default route */
        if (strncmp(line, "default", 7) == 0) {
            strcpy(dest, "0.0.0.0/0");
            
            /* Look for gateway */
            char *via = strstr(line, "via ");
            if (via) {
                via += 4;
                sscanf(via, "%s", gw);
            }
        } else {
            /* Regular route - first token is destination */
            if (sscanf(line, "%s", dest) != 1) {
                line = strtok_r(NULL, "\n", &saveptr);
                continue;
            }
            
            /* Check if destination is valid IP/CIDR */
            if (!strchr(dest, '.') && !strchr(dest, ':')) {
                /* Not a valid IP, skip this line */
                line = strtok_r(NULL, "\n", &saveptr);
                continue;
            }
            
            /* If no CIDR notation, might be a host route */
            if (strchr(dest, '.') && !strchr(dest, '/')) {
                /* IPv4 host route - add /32 */
                strcat(dest, "/32");
            } else if (strchr(dest, ':') && !strchr(dest, '/')) {
                /* IPv6 host route - add /128 */
                strcat(dest, "/128");
            }
        }
        
        /* Extract via (gateway) */
        char *via_str = strstr(line, "via ");
        if (via_str) {
            via_str += 4;
            sscanf(via_str, "%s", gw);
        }
        
        /* Extract device */
        char *dev_str = strstr(line, "dev ");
        if (dev_str) {
            dev_str += 4;
            sscanf(dev_str, "%s", dev);
        }
        
        /* Extract source */
        char *src_str = strstr(line, "src ");
        if (src_str) {
            src_str += 4;
            sscanf(src_str, "%s", src);
        }
        
        /* Extract protocol */
        char *proto_str = strstr(line, "proto ");
        if (proto_str) {
            proto_str += 6;
            sscanf(proto_str, "%s", proto);
        }
        
        /* Extract scope */
        char *scope_str = strstr(line, "scope ");
        if (scope_str) {
            scope_str += 6;
            sscanf(scope_str, "%s", scope);
        }
        
        /* Extract metric (also check for "metric" and "weight") */
        char *metric_str = strstr(line, "metric ");
        if (metric_str) {
            metric_str += 7;
            metric = atoi(metric_str);
        } else {
            /* Some systems use "weight" instead of "metric" */
            metric_str = strstr(line, "weight ");
            if (metric_str) {
                metric_str += 7;
                metric = atoi(metric_str);
            }
        }
        
        /* Populate route structure */
        route->destination = strdup_safe(dest);
        if (*gw) route->gateway = strdup_safe(gw);
        if (*dev) route->device = strdup_safe(dev);
        if (*src) route->source = strdup_safe(src);
        if (*proto) route->protocol = strdup_safe(proto);
        if (*scope) route->scope = strdup_safe(scope);
        route->metric = metric;
        route->table = strdup_safe(table_name);
        
        line = strtok_r(NULL, "\n", &saveptr);
    }
    
    free(section);
    return 0;
}

/* Parse policy rules section */
int parse_rules_section(const char *content, router_t *router) {
    char *section = find_section(content, "policy_rules");
    if (!section) return -1;
    
    char *line = strtok(section, "\n");
    while (line) {
        /* Skip empty lines and EXIT_CODE lines */
        if (!*line || strstr(line, "EXIT_CODE:")) {
            line = strtok(NULL, "\n");
            continue;
        }
        
        /* Parse rule line: "0:	from all lookup local" */
        int priority = 0;
        if (sscanf(line, "%d:", &priority) == 1) {
            rule_t *rule = add_rule(router);
            if (!rule) {
                line = strtok(NULL, "\n");
                continue;
            }
            
            rule->priority = priority;
            
            /* Parse from */
            char *from_str = strstr(line, "from ");
            if (from_str) {
                from_str += 5;
                char from[MAX_IP_LEN] = {0};
                sscanf(from_str, "%s", from);
                if (strcmp(from, "all") != 0) {
                    rule->from = strdup_safe(from);
                }
            }
            
            /* Parse to */
            char *to_str = strstr(line, "to ");
            if (to_str) {
                to_str += 3;
                char to[MAX_IP_LEN] = {0};
                sscanf(to_str, "%s", to);
                rule->to = strdup_safe(to);
            }
            
            /* Parse lookup table */
            char *lookup = strstr(line, "lookup ");
            if (lookup) {
                lookup += 7;
                char table[MAX_NAME_LEN] = {0};
                sscanf(lookup, "%s", table);
                rule->table = strdup_safe(table);
            }
            
            /* Parse fwmark */
            char *fwmark = strstr(line, "fwmark ");
            if (fwmark) {
                fwmark += 7;
                sscanf(fwmark, "0x%x", &rule->fwmark);
            }
            
            /* Parse iif */
            char *iif = strstr(line, "iif ");
            if (iif) {
                iif += 4;
                char iif_name[MAX_NAME_LEN] = {0};
                sscanf(iif, "%s", iif_name);
                rule->iif = strdup_safe(iif_name);
            }
            
            /* Parse oif */
            char *oif = strstr(line, "oif ");
            if (oif) {
                oif += 4;
                char oif_name[MAX_NAME_LEN] = {0};
                sscanf(oif, "%s", oif_name);
                rule->oif = strdup_safe(oif_name);
            }
            
            /* Parse dport */
            char *dport = strstr(line, "dport ");
            if (dport) {
                dport += 6;
                rule->dport = atoi(dport);
            }
            
            /* Parse sport */
            char *sport = strstr(line, "sport ");
            if (sport) {
                sport += 6;
                rule->sport = atoi(sport);
            }
            
            /* Parse tos */
            char *tos = strstr(line, "tos ");
            if (tos) {
                tos += 4;
                sscanf(tos, "0x%x", &rule->tos);
            }
        }
        
        line = strtok(NULL, "\n");
    }
    
    free(section);
    return 0;
}

/* Extract raw iptables block from facts */
int extract_iptables_block(const char *content, router_t *router) {
    char *section = find_section(content, "iptables_save");
    if (section) {
        router->iptables_save.content_size = strlen(section);
        router->iptables_save.raw_content = section; /* Take ownership */
        return 0;
    }
    /* No iptables section found - not an error */
    router->iptables_save.content_size = 0;
    router->iptables_save.raw_content = NULL;
    return 0;
}

/* Extract raw ipset block from facts */
int extract_ipset_block(const char *content, router_t *router) {
    char *section = find_section(content, "ipset_save");
    if (section) {
        router->ipset_save.content_size = strlen(section);
        router->ipset_save.raw_content = section; /* Take ownership */
        return 0;
    }
    /* No ipset section found - not an error */
    router->ipset_save.content_size = 0;
    router->ipset_save.raw_content = NULL;
    return 0;
}

/* Load router facts from file */
int load_router_facts(const char *facts_path, router_t *router) {
    FILE *fp = fopen(facts_path, "r");
    if (!fp) {
        fprintf(stderr, "Cannot open facts file: %s\n", facts_path);
        return -1;
    }
    
    /* Read entire file into memory */
    fseek(fp, 0, SEEK_END);
    long size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    char *content = malloc(size + 1);
    if (!content) {
        fclose(fp);
        return -1;
    }
    
    size_t read_size = fread(content, 1, size, fp);
    content[read_size] = '\0';
    fclose(fp);
    
    router->raw_facts_path = strdup_safe(facts_path);
    
    /* Parse sections */
    parse_interfaces_section(content, router);
    parse_rules_section(content, router);
    
    /* Extract ALL routing tables found in the raw facts - no guessing! */
    /* Look for all sections that match "routing_table_*" */
    const char *search = "=== TSIM_SECTION_START:routing_table_";
    const char *pos = content;
    
    while ((pos = strstr(pos, search)) != NULL) {
        pos += strlen(search);
        
        /* Extract table name until space or === */
        char table_name[256] = {0};
        int i = 0;
        while (pos[i] && pos[i] != ' ' && pos[i] != '=' && i < 255) {
            table_name[i] = pos[i];
            i++;
        }
        table_name[i] = '\0';
        
        if (strlen(table_name) > 0) {
                    
            /* Extract the actual section name for find_section */
            char section_name[256];
            snprintf(section_name, sizeof(section_name), "routing_table_%s", table_name);
            
            /* Extract commands from this routing table */
            char *section = find_section(content, section_name);
            if (section) {
                /* Process each line as a raw route command */
                char *saveptr = NULL;
                char *line = strtok_r(section, "\n", &saveptr);
                
                while (line) {
                    /* Skip empty lines and EXIT_CODE lines */
                    if (!*line || strstr(line, "EXIT_CODE:")) {
                        line = strtok_r(NULL, "\n", &saveptr);
                        continue;
                    }
                    
                    /* Trim leading/trailing spaces */
                    while (*line && isspace(*line)) line++;
                    char *line_end = line + strlen(line) - 1;
                    while (line_end > line && isspace(*line_end)) *line_end-- = '\0';
                    
                    if (!*line) {
                        line = strtok_r(NULL, "\n", &saveptr);
                        continue;
                    }
                    
                    /* Grow array if needed */
                    if (router->raw_route_count >= router->raw_route_capacity) {
                        size_t new_capacity = router->raw_route_capacity ? router->raw_route_capacity * 2 : 16;
                        char **new_commands = realloc(router->raw_route_commands, new_capacity * sizeof(char*));
                        if (!new_commands) {
                            line = strtok_r(NULL, "\n", &saveptr);
                            continue;
                        }
                        router->raw_route_commands = new_commands;
                        router->raw_route_capacity = new_capacity;
                    }
                    
                    /* Build ip route add command for this line */
                    char cmd[1024];
                    
                    /* Add table parameter BEFORE route if not main */
                    if (strcmp(table_name, "main") != 0) {
                        snprintf(cmd, sizeof(cmd), "ip route add table %s %s", table_name, line);
                    } else {
                        snprintf(cmd, sizeof(cmd), "ip route add %s", line);
                    }
                    
                    /* Store the command */
                    router->raw_route_commands[router->raw_route_count++] = strdup(cmd);
                    
                    line = strtok_r(NULL, "\n", &saveptr);
                }
                
                free(section);
            }
        }
        
        pos++;  /* Move past current match */
    }
    
    /* Extract raw iptables and ipset blocks (do NOT free content yet) */
    extract_iptables_block(content, router);
    extract_ipset_block(content, router);
    
    free(content);
    return 0;
}

/* Load facts from environment variable with filter (verbose version) */
int load_facts_from_env_filtered(facts_context_t **ctx_ptr, int verbose, const char *filter_pattern) {
    const char *facts_dir = getenv("TRACEROUTE_SIMULATOR_RAW_FACTS");
    if (!facts_dir) {
        fprintf(stderr, "TRACEROUTE_SIMULATOR_RAW_FACTS environment variable not set\n");
        return -1;
    }
    
    facts_context_t *ctx = create_facts_context();
    if (!ctx) {
        fprintf(stderr, "Failed to create facts context\n");
        return -1;
    }
    
    ctx->facts_dir = strdup_safe(facts_dir);
    
    DIR *dir = opendir(facts_dir);
    if (!dir) {
        fprintf(stderr, "Cannot open facts directory: %s\n", facts_dir);
        free_facts_context(ctx);
        return -1;
    }
    
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        /* Skip non-facts files */
        if (!strstr(entry->d_name, "_facts.txt")) continue;
        
        /* Extract router name from filename */
        char router_name[MAX_NAME_LEN] = {0};
        char *underscore = strstr(entry->d_name, "_facts.txt");
        if (underscore) {
            size_t name_len = underscore - entry->d_name;
            if (name_len < MAX_NAME_LEN) {
                strncpy(router_name, entry->d_name, name_len);
                router_name[name_len] = '\0';
            }
        }
        
        if (!router_name[0]) continue;
        
        /* Apply filter if provided */
        if (filter_pattern && !strstr(router_name, filter_pattern)) {
            continue;
        }
        
        /* Create router and load facts */
        router_t *router = create_router(router_name);
        if (!router) continue;
        
        char facts_path[MAX_PATH_LEN];
        snprintf(facts_path, sizeof(facts_path), "%s/%s", facts_dir, entry->d_name);
        
        if (load_router_facts(facts_path, router) == 0) {
            /* Add router to context */
            if (ctx->router_count >= ctx->router_capacity) {
                size_t new_capacity = ctx->router_capacity * GROWTH_FACTOR;
                router_t **new_routers = realloc_safe(ctx->routers,
                                                      new_capacity * sizeof(router_t*));
                if (!new_routers) {
                    free_router(router);
                    continue;
                }
                ctx->routers = new_routers;
                ctx->router_capacity = new_capacity;
            }
            ctx->routers[ctx->router_count++] = router;
            if (verbose) {
                printf("Loaded facts for router: %s\n", router_name);
            }
        } else {
            free_router(router);
        }
    }
    
    closedir(dir);
    *ctx_ptr = ctx;
    
    /* Summary always printed */
    printf("Loaded %zu routers from %s\n", ctx->router_count, facts_dir);
    return 0;
}

/* Load all facts from environment variable (verbose version) */
int load_facts_from_env_verbose(facts_context_t **ctx_ptr, int verbose) {
    return load_facts_from_env_filtered(ctx_ptr, verbose, NULL);
}

/* Load all facts from environment variable (non-verbose) */
int load_facts_from_env(facts_context_t **ctx_ptr) {
    return load_facts_from_env_filtered(ctx_ptr, 0, NULL);
}

/* Batch command execution using shared memory */
batch_context_t* create_batch_context(size_t initial_size) {
    batch_context_t *ctx = calloc(1, sizeof(batch_context_t));
    if (!ctx) return NULL;
    
    /* Create unique shared memory name */
    char shm_name[256];
    snprintf(shm_name, sizeof(shm_name), "/tsim_batch_%d_%ld", 
             getpid(), (long)time(NULL));
    ctx->shm_path = strdup_safe(shm_name);
    if (!ctx->shm_path) {
        free(ctx);
        return NULL;
    }
    
    /* Create shared memory object */
    ctx->shm_fd = shm_open(shm_name, O_CREAT | O_RDWR, 0600);
    if (ctx->shm_fd == -1) {
        free(ctx->shm_path);
        free(ctx);
        return NULL;
    }
    
    /* Set initial size */
    ctx->buffer_capacity = initial_size ? initial_size : 1024 * 1024; /* 1MB default */
    if (ftruncate(ctx->shm_fd, ctx->buffer_capacity) == -1) {
        shm_unlink(ctx->shm_path);
        close(ctx->shm_fd);
        free(ctx->shm_path);
        free(ctx);
        return NULL;
    }
    
    /* Map the shared memory */
    ctx->script_buffer = mmap(NULL, ctx->buffer_capacity, 
                             PROT_READ | PROT_WRITE, MAP_SHARED, 
                             ctx->shm_fd, 0);
    if (ctx->script_buffer == MAP_FAILED) {
        shm_unlink(ctx->shm_path);
        close(ctx->shm_fd);
        free(ctx->shm_path);
        free(ctx);
        return NULL;
    }
    
    /* Initialize with shebang */
    const char *header = "#!/bin/bash\nset -e\n";
    strcpy(ctx->script_buffer, header);
    ctx->buffer_size = strlen(header);
    
    return ctx;
}

void free_batch_context(batch_context_t *ctx) {
    if (!ctx) return;
    
    if (ctx->script_buffer && ctx->script_buffer != MAP_FAILED) {
        munmap(ctx->script_buffer, ctx->buffer_capacity);
    }
    
    if (ctx->shm_fd != -1) {
        close(ctx->shm_fd);
    }
    
    if (ctx->shm_path) {
        shm_unlink(ctx->shm_path);
        free(ctx->shm_path);
    }
    
    free(ctx);
}

int batch_add_command(batch_context_t *ctx, const char *namespace, const char *command) {
    if (!ctx || !command) return -1;
    
    /* Build the full command */
    char full_cmd[8192];
    if (namespace) {
        snprintf(full_cmd, sizeof(full_cmd), "ip netns exec %s %s\n", namespace, command);
    } else {
        snprintf(full_cmd, sizeof(full_cmd), "%s\n", command);
    }
    
    size_t cmd_len = strlen(full_cmd);
    
    /* Check if we need to resize */
    if (ctx->buffer_size + cmd_len + 1 > ctx->buffer_capacity) {
        /* For shared memory, we'd need to remap - for now just fail */
        fprintf(stderr, "Batch buffer full\n");
        return -1;
    }
    
    /* Append command */
    memcpy(ctx->script_buffer + ctx->buffer_size, full_cmd, cmd_len);
    ctx->buffer_size += cmd_len;
    ctx->script_buffer[ctx->buffer_size] = '\0';
    
    return 0;
}

int batch_execute(batch_context_t *ctx) {
    if (!ctx || !ctx->shm_path) return -1;
    
    /* Execute the script via fork/execve to allow interruption */
    pid_t pid = fork();
    if (pid == -1) {
        return -1;
    }
    
    if (pid == 0) {
        /* Child process */
        char script_path[512];
        snprintf(script_path, sizeof(script_path), "/dev/shm%s", ctx->shm_path);
        
        /* Redirect stderr to /dev/null */
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull != -1) {
            dup2(devnull, STDERR_FILENO);
            close(devnull);
        }
        
        /* Execute bash with the script */
        char *argv[] = {"bash", script_path, NULL};
        execve("/bin/bash", argv, environ);
        
        /* If execve fails */
        _exit(127);
    }
    
    /* Parent process - wait for child */
    int status;
    waitpid(pid, &status, 0);
    
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return -1;
}

int batch_execute_verbose(batch_context_t *ctx, int verbose) {
    if (!ctx || !ctx->shm_path) return -1;
    
    /* Execute the script via fork/execve to allow interruption */
    pid_t pid = fork();
    if (pid == -1) {
        return -1;
    }
    
    if (pid == 0) {
        /* Child process */
        char script_path[512];
        snprintf(script_path, sizeof(script_path), "/dev/shm%s", ctx->shm_path);
        
        /* Redirect stderr to /dev/null if not verbose */
        if (!verbose) {
            int devnull = open("/dev/null", O_WRONLY);
            if (devnull != -1) {
                dup2(devnull, STDERR_FILENO);
                close(devnull);
            }
        }
        
        /* Execute bash with the script */
        char *argv[] = {"bash", script_path, NULL};
        execve("/bin/bash", argv, environ);
        
        /* If execve fails */
        _exit(127);
    }
    
    /* Parent process - wait for child */
    int status;
    waitpid(pid, &status, 0);
    
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return -1;
}

/* Apply iptables from raw block using shared memory */
int apply_iptables_with_shm(const char *namespace, const iptables_block_t *block) {
    if (!block || !block->raw_content) {
        return 0;  /* No iptables to apply - not an error */
    }
    
    /* Check if content is empty or just whitespace */
    const char *p = block->raw_content;
    while (*p && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) p++;
    if (!*p || block->content_size == 0) {
        return 0;  /* Empty iptables - not an error */
    }
    
    /* Create shared memory for iptables data */
    char shm_name[256];
    snprintf(shm_name, sizeof(shm_name), "/tsim_iptables_%s_%ld", 
             namespace, (long)time(NULL));
    
    int shm_fd = shm_open(shm_name, O_CREAT | O_RDWR, 0600);
    if (shm_fd == -1) return -1;
    
    /* Set size and write content */
    if (ftruncate(shm_fd, block->content_size) == -1) {
        close(shm_fd);
        shm_unlink(shm_name);
        return -1;
    }
    
    void *shm_ptr = mmap(NULL, block->content_size, PROT_WRITE, MAP_SHARED, shm_fd, 0);
    if (shm_ptr == MAP_FAILED) {
        close(shm_fd);
        shm_unlink(shm_name);
        return -1;
    }
    
    memcpy(shm_ptr, block->raw_content, block->content_size);
    munmap(shm_ptr, block->content_size);
    close(shm_fd);
    
    /* Execute iptables-restore from shared memory */
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ip netns exec %s iptables-restore < /dev/shm%s", 
             namespace, shm_name);
    
    int result = system(cmd);
    
    /* Clean up */
    shm_unlink(shm_name);
    
    return result;
}

/* Apply ipset from raw block using shared memory */
int apply_ipset_with_shm(const char *namespace, const ipset_block_t *block) {
    if (!block || !block->raw_content) {
        return 0;  /* No ipset to apply - not an error */
    }
    
    /* Check if content is empty or just whitespace */
    const char *p = block->raw_content;
    while (*p && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) p++;
    if (!*p || block->content_size == 0) {
        return 0;  /* Empty ipset - not an error */
    }
    
    /* Create shared memory for ipset data */
    char shm_name[256];
    snprintf(shm_name, sizeof(shm_name), "/tsim_ipset_%s_%ld", 
             namespace, (long)time(NULL));
    
    int shm_fd = shm_open(shm_name, O_CREAT | O_RDWR, 0600);
    if (shm_fd == -1) return -1;
    
    /* Set size and write content */
    if (ftruncate(shm_fd, block->content_size) == -1) {
        close(shm_fd);
        shm_unlink(shm_name);
        return -1;
    }
    
    void *shm_ptr = mmap(NULL, block->content_size, PROT_WRITE, MAP_SHARED, shm_fd, 0);
    if (shm_ptr == MAP_FAILED) {
        close(shm_fd);
        shm_unlink(shm_name);
        return -1;
    }
    
    memcpy(shm_ptr, block->raw_content, block->content_size);
    munmap(shm_ptr, block->content_size);
    close(shm_fd);
    
    /* Execute ipset restore from shared memory */
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ip netns exec %s ipset restore < /dev/shm%s", 
             namespace, shm_name);
    
    int result = system(cmd);
    
    /* Clean up */
    shm_unlink(shm_name);
    
    return result;
}

/* Debug print functions */
void print_interface(const interface_t *iface) {
    printf("  Interface: %s (UP=%d, MTU=%d", iface->name, iface->up, iface->mtu);
    if (iface->mac) printf(", MAC=%s", iface->mac);
    printf(")\n");
    
    for (size_t i = 0; i < iface->addr_count; i++) {
        printf("    Address: %s", iface->addresses[i].ip);
        if (iface->addresses[i].broadcast) 
            printf(" brd %s", iface->addresses[i].broadcast);
        if (iface->addresses[i].scope)
            printf(" scope %s", iface->addresses[i].scope);
        if (iface->addresses[i].secondary)
            printf(" secondary");
        printf("\n");
    }
}

void print_route(const route_t *route) {
    printf("  Route: %s", route->destination);
    if (route->gateway) printf(" via %s", route->gateway);
    if (route->device) printf(" dev %s", route->device);
    if (route->source) printf(" src %s", route->source);
    if (route->metric) printf(" metric %d", route->metric);
    if (route->table) printf(" table %s", route->table);
    printf("\n");
}

void print_rule(const rule_t *rule) {
    printf("  Rule %d:", rule->priority);
    if (rule->from) printf(" from %s", rule->from);
    if (rule->to) printf(" to %s", rule->to);
    if (rule->fwmark) printf(" fwmark 0x%x", rule->fwmark);
    if (rule->iif) printf(" iif %s", rule->iif);
    if (rule->oif) printf(" oif %s", rule->oif);
    if (rule->dport) printf(" dport %d", rule->dport);
    if (rule->sport) printf(" sport %d", rule->sport);
    if (rule->table) printf(" lookup %s", rule->table);
    printf("\n");
}

void print_router_facts(const router_t *router) {
    printf("\nRouter: %s\n", router->name);
    printf("Facts file: %s\n", router->raw_facts_path);
    
    printf("\nInterfaces (%zu):\n", router->interface_count);
    for (size_t i = 0; i < router->interface_count; i++) {
        print_interface(&router->interfaces[i]);
    }
    
    printf("\nRoutes (%zu):\n", router->route_count);
    for (size_t i = 0; i < router->route_count && i < 10; i++) {
        print_route(&router->routes[i]);
    }
    if (router->route_count > 10) {
        printf("  ... and %zu more routes\n", router->route_count - 10);
    }
    
    printf("\nRules (%zu):\n", router->rule_count);
    for (size_t i = 0; i < router->rule_count; i++) {
        print_rule(&router->rules[i]);
    }
    
    printf("\nIPTables: %s (%zu bytes)\n", 
           router->iptables_save.raw_content ? "Present" : "Not available",
           router->iptables_save.content_size);
    
    printf("\nIPSet: %s (%zu bytes)\n", 
           router->ipset_save.raw_content ? "Present" : "Not available",
           router->ipset_save.content_size);
}