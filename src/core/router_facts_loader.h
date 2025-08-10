#ifndef ROUTER_FACTS_LOADER_H
#define ROUTER_FACTS_LOADER_H

#include <stdint.h>
#include <stddef.h>

#define MAX_NAME_LEN 64
#define MAX_IP_LEN 46
#define MAX_LINE_LEN 8192
#define MAX_PATH_LEN 4096

typedef struct {
    char *ip;
    char *broadcast;
    char *scope;
    int prefixlen;
    int secondary;
} address_t;

typedef struct {
    char *name;
    char *mac;
    int mtu;
    int up;
    address_t *addresses;
    size_t addr_count;
    size_t addr_capacity;
} interface_t;

typedef struct {
    char *destination;
    char *gateway;
    char *device;
    char *source;
    char *table;
    int metric;
    char *protocol;
    char *scope;
} route_t;

typedef struct {
    int priority;
    char *from;
    char *to;
    int fwmark;
    int tos;
    char *iif;
    char *oif;
    char *table;
    int sport;
    int dport;
    char *protocol;
} rule_t;

typedef struct {
    char *raw_content;  /* Verbatim content for iptables-restore */
    size_t content_size;
} iptables_block_t;

typedef struct {
    char *raw_content;  /* Verbatim content for ipset restore */
    size_t content_size;
} ipset_block_t;

typedef struct {
    char *name;
    interface_t *interfaces;
    size_t interface_count;
    size_t interface_capacity;
    
    route_t *routes;
    size_t route_count;
    size_t route_capacity;
    
    rule_t *rules;
    size_t rule_count;
    size_t rule_capacity;
    
    iptables_block_t iptables_save;  /* Raw iptables-save content */
    ipset_block_t ipset_save;         /* Raw ipset save content */
    
    /* Raw routing commands to execute verbatim */
    char **raw_route_commands;
    size_t raw_route_count;
    size_t raw_route_capacity;
    
    char *raw_facts_path;
} router_t;

typedef struct {
    router_t **routers;
    size_t router_count;
    size_t router_capacity;
    char *facts_dir;
} facts_context_t;

/* Memory management */
facts_context_t* create_facts_context(void);
void free_facts_context(facts_context_t *ctx);
router_t* create_router(const char *name);
void free_router(router_t *router);
interface_t* add_interface(router_t *router);
address_t* add_address(interface_t *iface);
route_t* add_route(router_t *router);
rule_t* add_rule(router_t *router);
/* Batch command execution */
typedef struct {
    int shm_fd;              /* Shared memory file descriptor */
    char *shm_path;          /* Shared memory path (/dev/shm/tsim_XXXXXX) */
    char *script_buffer;     /* Mmap'd script buffer */
    size_t buffer_size;      /* Current buffer size */
    size_t buffer_capacity;  /* Total capacity */
} batch_context_t;

batch_context_t* create_batch_context(size_t initial_size);
void free_batch_context(batch_context_t *ctx);
int batch_add_command(batch_context_t *ctx, const char *namespace, const char *command);
int batch_execute(batch_context_t *ctx);
int batch_execute_verbose(batch_context_t *ctx, int verbose);
int batch_execute_parallel(batch_context_t **contexts, size_t count);

/* Load all router facts from TRACEROUTE_SIMULATOR_FACTS environment variable */
int load_facts_from_env(facts_context_t **ctx);
int load_facts_from_env_verbose(facts_context_t **ctx, int verbose);
int load_facts_from_env_filtered(facts_context_t **ctx, int verbose, const char *filter_pattern);

/* Load a single router's facts from raw facts file */
int load_router_facts(const char *facts_path, router_t *router);

/* Parse specific sections from raw facts */
int parse_interfaces_section(const char *content, router_t *router);
int parse_routing_section(const char *content, const char *table_name, router_t *router);
int parse_rules_section(const char *content, router_t *router);
int extract_iptables_block(const char *content, router_t *router);
int extract_ipset_block(const char *content, router_t *router);

/* Apply configurations using shared memory */
int apply_iptables_with_shm(const char *namespace, const iptables_block_t *block);
int apply_ipset_with_shm(const char *namespace, const ipset_block_t *block);

/* Utility functions */
char* find_section(const char *content, const char *section_name);
char* strdup_safe(const char *str);

/* Debug and display functions */
void print_router_facts(const router_t *router);
void print_interface(const interface_t *iface);
void print_route(const route_t *route);
void print_rule(const rule_t *rule);

#endif /* ROUTER_FACTS_LOADER_H */