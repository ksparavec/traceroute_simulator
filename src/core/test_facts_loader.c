#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "router_facts_loader.h"

int main(int argc, char *argv[]) {
    facts_context_t *ctx = NULL;
    
    /* Load facts from environment variable */
    printf("Loading facts from TRACEROUTE_SIMULATOR_RAW_FACTS...\n");
    if (load_facts_from_env(&ctx) != 0) {
        fprintf(stderr, "Failed to load facts\n");
        return 1;
    }
    
    /* Print summary */
    printf("\n=== FACTS SUMMARY ===\n");
    printf("Total routers loaded: %zu\n", ctx->router_count);
    printf("Facts directory: %s\n\n", ctx->facts_dir);
    
    /* Print detailed info for each router if verbose */
    if (argc > 1 && strcmp(argv[1], "-v") == 0) {
        for (size_t i = 0; i < ctx->router_count; i++) {
            print_router_facts(ctx->routers[i]);
        }
    } else {
        /* Just print router names and basic stats */
        for (size_t i = 0; i < ctx->router_count; i++) {
            router_t *r = ctx->routers[i];
            printf("Router %zu: %s - %zu interfaces, %zu routes, %zu rules\n",
                   i + 1, r->name, r->interface_count, r->route_count, r->rule_count);
        }
        printf("\nUse -v flag for detailed output\n");
    }
    
    /* Clean up */
    free_facts_context(ctx);
    
    return 0;
}