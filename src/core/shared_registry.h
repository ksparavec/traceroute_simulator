/* Shared Memory Registry for Network Setup
 * 
 * Binary structures stored directly in shared memory
 * No serialization/parsing needed - direct memory access
 */

#ifndef SHARED_REGISTRY_H
#define SHARED_REGISTRY_H

#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>

#define REGISTRY_SHM_NAME "/tsim_registry"
#define MAX_ROUTERS 1024
#define MAX_INTERFACES_PER_ROUTER 64
#define MAX_BRIDGES 2048
#ifndef MAX_NAME_LEN
#define MAX_NAME_LEN 256
#endif
#define MAX_CODE_LEN 8

/* Router registry entry in shared memory */
typedef struct {
    char router_name[MAX_NAME_LEN];
    char router_code[MAX_CODE_LEN];  /* r000 to r999 */
    int active;                       /* 1 if entry is valid */
} shm_router_entry_t;

/* Interface registry entry */
typedef struct {
    char router_code[MAX_CODE_LEN];
    char interface_name[MAX_NAME_LEN];
    char interface_code[MAX_CODE_LEN];  /* i000 to i999 */
    int active;
} shm_interface_entry_t;

/* Bridge registry entry */
typedef struct {
    char bridge_name[32];
    char subnet[32];
    int created;
    int active;
} shm_bridge_entry_t;

/* Complete registry in shared memory */
typedef struct {
    /* Header */
    int version;
    int router_count;
    int interface_count;
    int bridge_count;
    
    /* Fixed-size arrays for O(1) access */
    shm_router_entry_t routers[MAX_ROUTERS];
    shm_interface_entry_t interfaces[MAX_ROUTERS * MAX_INTERFACES_PER_ROUTER];
    shm_bridge_entry_t bridges[MAX_BRIDGES];
    
    /* Next available codes */
    int next_router_code;
    int next_interface_codes[MAX_ROUTERS];  /* Per router interface counter */
} shm_registry_t;

/* Registry handle */
typedef struct {
    int shm_fd;
    shm_registry_t *registry;
    size_t size;
    int created;  /* 1 if we created it, 0 if attached to existing */
} registry_handle_t;

/* Open or create shared memory registry */
static inline registry_handle_t* open_shared_registry(int create) {
    registry_handle_t *handle = calloc(1, sizeof(registry_handle_t));
    if (!handle) return NULL;
    
    handle->size = sizeof(shm_registry_t);
    
    /* Try to create new or open existing */
    if (create) {
        /* Unlink any existing registry first */
        shm_unlink(REGISTRY_SHM_NAME);
        
        handle->shm_fd = shm_open(REGISTRY_SHM_NAME, O_CREAT | O_RDWR | O_EXCL, 0666);
        if (handle->shm_fd == -1) {
            /* Try without O_EXCL if it exists */
            handle->shm_fd = shm_open(REGISTRY_SHM_NAME, O_RDWR, 0666);
            if (handle->shm_fd == -1) {
                free(handle);
                return NULL;
            }
            handle->created = 0;
        } else {
            handle->created = 1;
        }
    } else {
        /* Open existing */
        handle->shm_fd = shm_open(REGISTRY_SHM_NAME, O_RDWR, 0666);
        if (handle->shm_fd == -1) {
            /* Doesn't exist, create it */
            handle->shm_fd = shm_open(REGISTRY_SHM_NAME, O_CREAT | O_RDWR, 0666);
            if (handle->shm_fd == -1) {
                free(handle);
                return NULL;
            }
            handle->created = 1;
        } else {
            handle->created = 0;
        }
    }
    
    /* Set size */
    if (ftruncate(handle->shm_fd, handle->size) == -1) {
        close(handle->shm_fd);
        if (handle->created) shm_unlink(REGISTRY_SHM_NAME);
        free(handle);
        return NULL;
    }
    
    /* Map into memory */
    handle->registry = mmap(NULL, handle->size, PROT_READ | PROT_WRITE, 
                            MAP_SHARED, handle->shm_fd, 0);
    if (handle->registry == MAP_FAILED) {
        close(handle->shm_fd);
        if (handle->created) shm_unlink(REGISTRY_SHM_NAME);
        free(handle);
        return NULL;
    }
    
    /* Initialize if we created it */
    if (handle->created) {
        memset(handle->registry, 0, handle->size);
        handle->registry->version = 1;
    }
    
    return handle;
}

/* Close registry handle */
static inline void close_shared_registry(registry_handle_t *handle) {
    if (!handle) return;
    
    if (handle->registry && handle->registry != MAP_FAILED) {
        munmap(handle->registry, handle->size);
    }
    
    if (handle->shm_fd >= 0) {
        close(handle->shm_fd);
    }
    
    free(handle);
}

/* Get or create router code - O(1) lookup */
static inline const char* get_router_code_shm(shm_registry_t *reg, const char *router_name) {
    /* Linear search through active entries (still fast for ~100 routers) */
    for (int i = 0; i < MAX_ROUTERS && i < reg->router_count + 10; i++) {
        if (reg->routers[i].active && 
            strcmp(reg->routers[i].router_name, router_name) == 0) {
            return reg->routers[i].router_code;
        }
    }
    
    /* Not found - create new entry */
    if (reg->router_count >= MAX_ROUTERS) {
        return NULL;
    }
    
    /* Find first free slot */
    for (int i = 0; i < MAX_ROUTERS; i++) {
        if (!reg->routers[i].active) {
            /* Use this slot */
            strncpy(reg->routers[i].router_name, router_name, MAX_NAME_LEN - 1);
            snprintf(reg->routers[i].router_code, MAX_CODE_LEN, "r%03d", reg->next_router_code++);
            reg->routers[i].active = 1;
            reg->router_count++;
            return reg->routers[i].router_code;
        }
    }
    
    return NULL;
}

/* Get next interface code for router */
static inline const char* get_interface_code_shm(shm_registry_t *reg, const char *router_code, 
                                                 const char *interface_name) {
    static char code_buf[MAX_CODE_LEN];
    
    /* Find router index from code */
    int router_idx = -1;
    if (router_code[0] == 'r') {
        router_idx = atoi(&router_code[1]);
        if (router_idx >= MAX_ROUTERS) return NULL;
    }
    
    if (router_idx == -1) return NULL;
    
    /* Check if interface already registered */
    int base = router_idx * MAX_INTERFACES_PER_ROUTER;
    for (int i = 0; i < MAX_INTERFACES_PER_ROUTER; i++) {
        int idx = base + i;
        if (reg->interfaces[idx].active &&
            strcmp(reg->interfaces[idx].router_code, router_code) == 0 &&
            strcmp(reg->interfaces[idx].interface_name, interface_name) == 0) {
            return reg->interfaces[idx].interface_code;
        }
    }
    
    /* Create new interface entry */
    for (int i = 0; i < MAX_INTERFACES_PER_ROUTER; i++) {
        int idx = base + i;
        if (!reg->interfaces[idx].active) {
            strncpy(reg->interfaces[idx].router_code, router_code, MAX_CODE_LEN - 1);
            strncpy(reg->interfaces[idx].interface_name, interface_name, MAX_NAME_LEN - 1);
            snprintf(reg->interfaces[idx].interface_code, MAX_CODE_LEN, "i%03d", 
                    reg->next_interface_codes[router_idx]++);
            reg->interfaces[idx].active = 1;
            reg->interface_count++;
            
            strcpy(code_buf, reg->interfaces[idx].interface_code);
            return code_buf;
        }
    }
    
    return NULL;
}

/* Register bridge in shared memory */
static inline int register_bridge_shm(shm_registry_t *reg, const char *bridge_name, 
                                      const char *subnet) {
    /* Check if already exists */
    for (int i = 0; i < MAX_BRIDGES && i < reg->bridge_count + 10; i++) {
        if (reg->bridges[i].active &&
            strcmp(reg->bridges[i].bridge_name, bridge_name) == 0) {
            return i;  /* Already registered */
        }
    }
    
    /* Find free slot */
    for (int i = 0; i < MAX_BRIDGES; i++) {
        if (!reg->bridges[i].active) {
            /* Safe string copy with guaranteed null termination */
            size_t bridge_len = strlen(bridge_name);
            size_t subnet_len = strlen(subnet);
            
            if (bridge_len > 31) bridge_len = 31;
            if (subnet_len > 31) subnet_len = 31;
            
            memcpy(reg->bridges[i].bridge_name, bridge_name, bridge_len);
            reg->bridges[i].bridge_name[bridge_len] = '\0';
            
            memcpy(reg->bridges[i].subnet, subnet, subnet_len);
            reg->bridges[i].subnet[subnet_len] = '\0';
            
            reg->bridges[i].created = 0;
            reg->bridges[i].active = 1;
            reg->bridge_count++;
            return i;
        }
    }
    
    return -1;  /* No space */
}

/* Find bridge by subnet */
static inline shm_bridge_entry_t* find_bridge_by_subnet(shm_registry_t *reg, const char *subnet) {
    for (int i = 0; i < MAX_BRIDGES; i++) {
        if (reg->bridges[i].active &&
            strcmp(reg->bridges[i].subnet, subnet) == 0) {
            return &reg->bridges[i];
        }
    }
    return NULL;
}

/* Clear all registries */
static inline void clear_shared_registry(shm_registry_t *reg) {
    memset(reg, 0, sizeof(shm_registry_t));
    reg->version = 1;
}

#endif /* SHARED_REGISTRY_H */