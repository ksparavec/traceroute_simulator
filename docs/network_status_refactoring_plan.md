# Network Status Command Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring plan for the `network status` tsimsh command to improve performance, maintainability, and extensibility. The main goals are:

1. **Separation of Concerns**: Split monolithic script into modular components
2. **Parallelization**: Execute namespace queries concurrently for faster data collection
3. **Caching**: Implement JSON cache in `/dev/shm` for subsequent execution speedup
4. **Configuration**: Make cache paths and expiration configurable

## Current State Analysis

### Existing Architecture Issues

1. **Monolithic Design**: Single 1722-line file (`network_namespace_status.py`)
2. **Sequential Execution**: All `ip netns exec` commands run one after another
3. **No Caching**: Every invocation re-queries all namespace data
4. **Mixed Responsibilities**: Data collection, formatting, and display in one class
5. **Repetitive Code**: Similar patterns repeated for each display function

### Performance Bottlenecks

- Sequential namespace queries (N namespaces × M commands = N×M serial operations)
- No result caching between invocations
- Redundant data collection when only specific info needed
- Interface name translation happens on every query

## Proposed Architecture

### Component Separation

```
┌─────────────────────────────────────────────────────┐
│                  Command Handler                     │
│            (network.py - unchanged)                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              NetworkStatusManager                    │
│         (Orchestration & Caching Layer)             │
├──────────────────────────────────────────────────────┤
│ - Cache management                                   │
│ - Parallel execution coordination                    │
│ - High-level API                                     │
└──────────────┬───────────────────────┬──────────────┘
               │                       │
┌──────────────▼──────────┐  ┌────────▼──────────────┐
│   DataCollector         │  │   DataFormatter       │
├─────────────────────────┤  ├───────────────────────┤
│ - Parallel execution    │  │ - JSON formatting     │
│ - Raw data gathering    │  │ - Text formatting     │
│ - Command execution     │  │ - Name translation    │
└─────────────────────────┘  └───────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              NamespaceQueryWorker                    │
│           (Thread Pool Workers)                      │
├──────────────────────────────────────────────────────┤
│ - Individual namespace queries                       │
│ - Command execution in threads                       │
│ - Error handling per namespace                       │
└──────────────────────────────────────────────────────┘
```

### New Class Structure

#### 1. `NetworkStatusManager` (Main Orchestrator)
```python
class NetworkStatusManager:
    """High-level manager for network status operations."""
    
    def __init__(self, facts_dir: str, cache_config: CacheConfig):
        self.collector = DataCollector(facts_dir)
        self.formatter = DataFormatter(facts_dir)
        self.cache = CacheManager(cache_config)
    
    def get_status(self, function: str, namespaces: List[str], 
                   use_cache: bool = True) -> Dict:
        """Get status with caching and parallelization."""
        
    def invalidate_cache(self, namespace: Optional[str] = None):
        """Invalidate cache for namespace or all."""
```

#### 2. `DataCollector` (Parallel Data Collection)
```python
class DataCollector:
    """Handles parallel data collection from namespaces."""
    
    def __init__(self, facts_dir: str, max_workers: int = 20):
        self.facts_dir = facts_dir
        self.executor = ThreadPoolExecutor(max_workers)
    
    def collect_all_data(self, namespaces: List[str]) -> Dict:
        """Collect all data from namespaces in parallel."""
        
    def collect_interfaces(self, namespaces: List[str]) -> Dict:
        """Collect interface data in parallel."""
        
    def collect_routes(self, namespaces: List[str]) -> Dict:
        """Collect routing data in parallel."""
```

#### 3. `NamespaceQueryWorker` (Thread Worker)
```python
class NamespaceQueryWorker:
    """Worker for executing commands in a namespace."""
    
    def query_interfaces(self, namespace: str) -> Dict:
        """Query interfaces for a single namespace."""
        
    def query_routes(self, namespace: str) -> Dict:
        """Query routes for a single namespace."""
        
    def execute_command(self, namespace: str, command: str) -> str:
        """Execute a single command in namespace."""
```

#### 4. `DataFormatter` (Formatting Layer)
```python
class DataFormatter:
    """Handles all data formatting operations."""
    
    def __init__(self, facts_dir: str):
        self.name_translator = InterfaceNameTranslator(facts_dir)
    
    def format_json(self, data: Dict, function: str) -> str:
        """Format data as JSON."""
        
    def format_text(self, data: Dict, function: str) -> str:
        """Format data as human-readable text."""
        
    def format_summary(self, data: Dict) -> str:
        """Format summary view."""
```

#### 5. `CacheManager` (Abstract Cache Interface)
```python
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    """Abstract interface for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Dict]:
        """Get cached data if not expired."""
        pass
    
    @abstractmethod
    def set(self, key: str, data: Dict, ttl: Optional[int] = None):
        """Store data in cache with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    def scan(self, pattern: str) -> List[str]:
        """Find keys matching pattern."""
        pass
    
    @abstractmethod
    def clear(self):
        """Clear all cache entries."""
        pass

class SharedMemoryBackend(CacheBackend):
    """Shared memory implementation of cache backend."""
    
    def __init__(self, base_path: str, default_ttl: int):
        self.cache_dir = Path(base_path)
        self.default_ttl = default_ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)

class RedisBackend(CacheBackend):
    """Redis implementation of cache backend."""
    
    def __init__(self, host: str, port: int, db: int, default_ttl: int):
        self.client = redis.Redis(host=host, port=port, db=db)
        self.default_ttl = default_ttl

class CacheManager:
    """High-level cache manager with backend abstraction."""
    
    def __init__(self, config: Dict):
        backend_type = config.get('backend', 'shared_memory')
        
        if backend_type == 'shared_memory':
            self.backend = SharedMemoryBackend(
                config.get('base_path', '/dev/shm/tsim/network_status_cache'),
                config.get('expiration_seconds', 3600)
            )
        elif backend_type == 'redis':
            self.backend = RedisBackend(
                config.get('redis_host', 'localhost'),
                config.get('redis_port', 6379),
                config.get('redis_db', 0),
                config.get('expiration_seconds', 3600)
            )
        else:
            raise ValueError(f"Unknown cache backend: {backend_type}")
    
    def get_namespace_data(self, namespace: str, data_type: str) -> Optional[Dict]:
        """Get cached namespace data."""
        key = f"namespace/{namespace}/{data_type}"
        return self.backend.get(key)
    
    def set_namespace_data(self, namespace: str, data_type: str, data: Dict):
        """Cache namespace data."""
        key = f"namespace/{namespace}/{data_type}"
        self.backend.set(key, data)
    
    def invalidate_namespace(self, namespace: str):
        """Invalidate all cache entries for a namespace."""
        pattern = f"namespace/{namespace}/*"
        for key in self.backend.scan(pattern):
            self.backend.delete(key)
```

### Parallelization Strategy

#### Thread Pool Design
```python
# Example parallel collection
def collect_all_data(self, namespaces: List[str]) -> Dict:
    futures = {}
    results = {}
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        for ns in namespaces:
            futures[ns] = {
                'interfaces': executor.submit(self.worker.query_interfaces, ns),
                'routes': executor.submit(self.worker.query_routes, ns),
                'rules': executor.submit(self.worker.query_rules, ns),
                'iptables': executor.submit(self.worker.query_iptables, ns),
                'ipsets': executor.submit(self.worker.query_ipsets, ns)
            }
        
        # Gather results
        for ns, ns_futures in futures.items():
            results[ns] = {}
            for data_type, future in ns_futures.items():
                try:
                    results[ns][data_type] = future.result(timeout=5)
                except TimeoutError:
                    results[ns][data_type] = {'error': 'Query timeout'}
                except Exception as e:
                    results[ns][data_type] = {'error': str(e)}
    
    return results
```

#### Expected Performance Improvements

- **Current**: N namespaces × 5 query types = 5N sequential operations
- **Proposed**: All operations in parallel, limited by thread pool size
- **Speedup**: ~10-20x for typical 20-50 namespace setups

### Caching Implementation

#### Cache Storage Options Comparison

| Aspect | Shared Memory (/dev/shm) | Redis (Key-Value) | SQLite (SQL Database) |
|--------|-------------------------|-------------------|----------------------|
| **Performance** | | | |
| Read Speed | ⭐⭐⭐⭐⭐ Fastest (~µs) | ⭐⭐⭐⭐ Very Fast (~ms) | ⭐⭐⭐ Fast (~ms) |
| Write Speed | ⭐⭐⭐⭐⭐ Fastest (~µs) | ⭐⭐⭐⭐ Very Fast (~ms) | ⭐⭐⭐ Fast (~ms) |
| Latency | Minimal (RAM access) | Network overhead (TCP/Unix socket) | Disk I/O (even in WAL mode) |
| Concurrent Access | File locking required | Built-in atomic operations | Built-in ACID transactions |
| **Scalability** | | | |
| Max Size | Limited by RAM | Limited by RAM + disk (with persistence) | Limited by disk |
| Multi-process | ✅ Yes (file-based) | ✅ Yes (client-server) | ✅ Yes (file locking) |
| Multi-server | ❌ No | ✅ Yes (Redis Cluster) | ❌ No (file-based) |
| Horizontal Scaling | ❌ No | ✅ Yes | ❌ No |
| **Reliability** | | | |
| Persistence | ❌ Lost on reboot | ✅ Optional (RDB/AOF) | ✅ Always persistent |
| Crash Recovery | ❌ No recovery | ✅ Automatic recovery | ✅ Automatic recovery |
| Data Integrity | Basic (manual checksums) | Built-in checksums | ACID guarantees |
| Atomic Operations | Manual implementation | ✅ Built-in | ✅ Built-in transactions |
| **Complexity** | | | |
| Setup | ⭐ None required | ⭐⭐⭐ Service installation | ⭐⭐ Library only |
| Dependencies | None | Redis server + client library | SQLite library |
| Maintenance | Manual cleanup | Redis admin (memory, persistence) | Vacuum, analyze |
| Monitoring | Custom implementation | Built-in INFO command | SQL queries |
| **Features** | | | |
| TTL/Expiration | Manual implementation | ✅ Built-in EXPIRE | Manual implementation |
| Pattern Matching | Glob on filesystem | ✅ KEYS, SCAN patterns | ✅ SQL LIKE, GLOB |
| Pub/Sub | ❌ No | ✅ Yes | ❌ No |
| Transactions | ❌ No | ✅ MULTI/EXEC | ✅ BEGIN/COMMIT |
| Data Types | JSON files only | Multiple (strings, lists, sets, etc.) | Tables with typed columns |
| Querying | File path patterns | Key patterns | Full SQL |
| **Resource Usage** | | | |
| Memory Overhead | Minimal | Redis server (~10-50MB base) | SQLite (~1-5MB) |
| CPU Usage | Minimal | Low-moderate | Low-moderate |
| Disk Usage | RAM only (/dev/shm) | Optional persistence | Always on disk |
| **Operational** | | | |
| Backup | Copy files | BGSAVE, replication | Copy DB file |
| Cache Warmup | Read files to memory | Load from disk/AOF | Already persistent |
| Cache Invalidation | Delete files | DEL commands | DELETE queries |
| Partial Updates | Rewrite entire file | ✅ Update specific keys | ✅ UPDATE queries |
| **Development** | | | |
| Learning Curve | ⭐ Simple | ⭐⭐ Moderate | ⭐⭐ Moderate |
| Debugging | View files directly | redis-cli | sqlite3 CLI |
| Testing | Mock filesystem | Mock Redis or use TestContainers | In-memory DB |
| Code Complexity | Medium (handle locks, cleanup) | Low (Redis handles complexity) | Low-Medium (SQL queries) |

#### Detailed Analysis

##### Option 1: Shared Memory (/dev/shm) - Current Plan
**Pros:**
- ✅ Zero latency - Direct RAM access
- ✅ No external dependencies or services
- ✅ Simple deployment - works out of the box
- ✅ Minimal resource overhead
- ✅ Easy to inspect (just JSON files)
- ✅ Natural fit for read-heavy workload

**Cons:**
- ❌ Lost on system reboot
- ❌ No built-in expiration mechanism
- ❌ Manual implementation of locking for concurrent writes
- ❌ No query capabilities beyond file patterns
- ❌ Limited to single server
- ❌ Manual cleanup required

**Best for:** High-performance, single-server deployments with simple caching needs

##### Option 2: Redis (Key-Value Store)
**Pros:**
- ✅ Built-in expiration (TTL)
- ✅ Atomic operations and transactions
- ✅ Rich data structures (not just JSON)
- ✅ Pub/Sub for cache invalidation events
- ✅ Clustering and replication support
- ✅ Battle-tested in production
- ✅ Excellent monitoring and admin tools
- ✅ Can persist to disk if needed

**Cons:**
- ❌ Requires Redis server installation and management
- ❌ Additional service to monitor and maintain
- ❌ Network overhead (even with Unix sockets)
- ❌ More complex deployment
- ❌ Memory overhead of Redis server process
- ❌ Potential version compatibility issues

**Best for:** Multi-server deployments, complex caching patterns, when Redis is already available

##### Option 3: SQLite (SQL Database)
**Pros:**
- ✅ ACID compliance
- ✅ Rich query capabilities with SQL
- ✅ Persistent by default
- ✅ Built-in indexing for fast lookups
- ✅ Transactions for atomic updates
- ✅ Can store structured relationships
- ✅ Good tooling (sqlite3 CLI, DB browsers)
- ✅ Can analyze cache usage patterns with SQL

**Cons:**
- ❌ Slower than pure memory solutions
- ❌ Disk I/O overhead (even with WAL mode)
- ❌ No built-in TTL/expiration
- ❌ File locking can cause contention
- ❌ VACUUM needed periodically
- ❌ Single-writer limitation (even with WAL)
- ❌ Overkill for simple key-value caching

**Best for:** When persistence is required, complex queries needed, audit trail important

#### Hybrid Approach Consideration

A hybrid approach could leverage multiple tiers:

```
Level 1 (Hot): /dev/shm for most recent/frequent data
Level 2 (Warm): Redis for shared cache across processes  
Level 3 (Cold): SQLite for persistent historical data
```

#### Recommendation for This Project

Given the requirements and context of the network status command:

1. **Start with Shared Memory (/dev/shm)**
   - Simplest to implement and deploy
   - Meets performance requirements (10-20x speedup)
   - No additional services to manage
   - Natural fit for read-heavy, ephemeral cache

2. **Design for Future Redis Migration**
   - Abstract cache interface to allow backend swap
   - Keep Redis as an option for future scaling
   - Useful if/when multi-server deployment needed

3. **Avoid SQLite for this use case**
   - Overhead not justified for ephemeral cache
   - Performance inferior to memory-based solutions
   - Persistence not required for status data

### Caching Implementation (Continued)

#### Cache Structure
```
/dev/shm/tsim/network_status_cache/
├── namespace/
│   ├── hq-gw/
│   │   ├── interfaces.json
│   │   ├── routes.json
│   │   ├── rules.json
│   │   ├── iptables.json
│   │   ├── ipsets.json
│   │   └── metadata.json  # timestamp, expiration, version
│   └── br-core/
│       └── ...
├── summary/
│   ├── all_namespaces.json
│   └── metadata.json
└── cache_info.json  # Global cache statistics
```

#### Cache Key Design
```python
def get_cache_key(namespace: str, data_type: str) -> str:
    """Generate cache key for namespace data."""
    return f"namespace/{namespace}/{data_type}.json"
```

#### Cache Invalidation Strategy

1. **Time-based**: Default 3600 seconds (1 hour)
2. **Event-based**: Invalidate on network setup/clean operations
3. **Manual**: Provide `--no-cache` flag to bypass cache
4. **Selective**: Invalidate specific namespace or data type

### Configuration Updates

#### 1. Traceroute Simulator Configuration (`traceroute_simulator.yaml`)
Add new `network_status` section to the tsimsh configuration:

```yaml
# Network status command configuration
network_status:
  # Cache configuration for performance
  cache:
    enabled: true
    backend: shared_memory  # Options: shared_memory, redis, sqlite
    base_path: /dev/shm/tsim/network_status_cache  # For shared_memory backend
    expiration_seconds: 3600  # 1 hour default
    max_size_mb: 100
    compression: false
    cleanup_interval: 7200  # Clean old entries every 2 hours
    
    # Redis backend configuration (if backend: redis)
    redis:
      host: localhost
      port: 6379
      db: 0
      password: null
      socket: /var/run/redis/redis.sock  # Use Unix socket if available
      use_socket: false
      
    # SQLite backend configuration (if backend: sqlite)  
    sqlite:
      path: /var/lib/tsim/cache.db
      wal_mode: true
      journal_mode: WAL
      synchronous: NORMAL
    
  # Parallel execution settings
  parallelization:
    enabled: true
    max_workers: 20  # Thread pool size
    timeout_per_namespace: 5  # Seconds per namespace query
    batch_size: 50  # Max namespaces per batch
    
  # Data collection control
  collection:
    interfaces: true
    routes: true
    rules: true
    iptables: true
    ipsets: true
    
  # Output formatting options
  formatting:
    translate_interface_names: true  # Convert v001 to original names
    show_original_names: true  # Display both short and original names
    json_indent: 2
    
  # Performance tuning
  performance:
    use_json_commands: true  # Use ip -j for JSON output where available
    cache_warmup: false  # Pre-populate cache on startup
    stale_cache_timeout: 300  # Return stale data if refresh takes too long
```

#### 2. Configuration File Precedence
Following the existing traceroute simulator configuration precedence:

1. Environment variable `TRACEROUTE_SIMULATOR_CONF` (if set)
2. `~/traceroute_simulator.yaml` (user's home directory)  
3. `./traceroute_simulator.yaml` (repository directory)
4. `/opt/tsim/wsgi/conf/traceroute_simulator.yaml` (installed location)

#### 3. Environment Variables (Runtime Override)
```bash
# Cache configuration
export TSIM_NETWORK_STATUS_CACHE_PATH="/dev/shm/tsim/network_status_cache"
export TSIM_NETWORK_STATUS_CACHE_EXPIRATION=3600
export TSIM_NETWORK_STATUS_CACHE_ENABLED=true

# Parallelization configuration  
export TSIM_NETWORK_STATUS_MAX_WORKERS=20
export TSIM_NETWORK_STATUS_TIMEOUT=5

# Feature flags
export TSIM_NETWORK_STATUS_PARALLEL_ENABLED=true
export TSIM_NETWORK_STATUS_CACHE_COMPRESSION=false
```

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. Create new module structure:
   - `src/simulators/network_status/` directory
   - `__init__.py`, `manager.py`, `collector.py`, `formatter.py`, `cache.py`, `worker.py`
2. Implement `CacheManager` class with basic get/set operations
3. Update configuration files with cache parameters
4. Create unit tests for cache manager

### Phase 2: Data Collection Refactoring (Week 1-2)
1. Extract data collection logic into `DataCollector` class
2. Implement `NamespaceQueryWorker` for individual namespace queries
3. Add thread pool execution with configurable worker count
4. Implement timeout and error handling per namespace
5. Create integration tests for parallel collection

### Phase 3: Formatting Separation (Week 2)
1. Extract formatting logic into `DataFormatter` class
2. Separate JSON and text formatting methods
3. Move interface name translation to dedicated class
4. Implement format-specific optimizations
5. Add unit tests for formatters

### Phase 4: Cache Integration (Week 2-3)
1. Integrate `CacheManager` with `NetworkStatusManager`
2. Implement cache key generation strategy
3. Add cache hit/miss metrics and logging
4. Implement cache invalidation triggers
5. Add cache warmup functionality

### Phase 5: Command Integration (Week 3)
1. Update `network_namespace_status.py` to use new architecture
2. Maintain backward compatibility with existing command interface
3. Add new command flags:
   - `--no-cache`: Bypass cache
   - `--cache-info`: Show cache statistics
   - `--invalidate-cache`: Clear cache
4. Update shell command handler if needed

### Phase 6: Testing & Optimization (Week 3-4)
1. Performance benchmarking:
   - Measure speedup with parallelization
   - Validate cache hit rates
   - Profile memory usage
2. Load testing with many namespaces
3. Edge case testing:
   - Namespace creation/deletion during query
   - Cache corruption recovery
   - Thread pool exhaustion
4. Documentation updates

## Migration Strategy

### Backward Compatibility
- Keep existing command interface unchanged
- Maintain same output format
- Support all existing flags and options
- Gradual migration with feature flags

### Rollout Plan
1. **Alpha**: Deploy alongside existing implementation with opt-in flag
2. **Beta**: Enable by default with opt-out flag
3. **GA**: Remove old implementation after stability period

### Rollback Plan
- Keep old implementation for 2 release cycles
- Feature flag to switch implementations
- Cache can be disabled via configuration

## Success Metrics

### Performance Targets
- **Data Collection**: 10-20x speedup for 20+ namespaces
- **Cache Hit Rate**: >80% for repeated queries within 1 hour
- **Memory Usage**: <100MB cache size for typical setup
- **Response Time**: <500ms for cached summary of 50 namespaces

### Quality Metrics
- **Code Coverage**: >90% unit test coverage
- **Maintainability**: Reduce lines of code by 30%
- **Extensibility**: New data types addable without core changes
- **Error Handling**: Graceful degradation on partial failures

## Risk Assessment

### Technical Risks
1. **Thread Safety**: Ensure subprocess calls are thread-safe
2. **Cache Corruption**: Implement atomic writes and validation
3. **Memory Pressure**: Monitor `/dev/shm` usage
4. **Namespace Race Conditions**: Handle namespace changes during query

### Mitigation Strategies
1. Use thread-local storage for subprocess operations
2. Implement cache versioning and checksums
3. Add cache size limits and eviction policies
4. Implement retry logic with exponential backoff

## Appendix

### A. File Structure After Refactoring
```
src/simulators/
├── network_namespace_status.py  # Thin wrapper for compatibility
└── network_status/
    ├── __init__.py
    ├── manager.py         # NetworkStatusManager
    ├── collector.py       # DataCollector
    ├── worker.py         # NamespaceQueryWorker
    ├── formatter.py      # DataFormatter
    ├── cache.py          # CacheManager
    ├── config.py         # Configuration handling
    ├── exceptions.py     # Custom exceptions
    └── utils.py          # Utility functions
```

### B. Example Usage After Refactoring
```python
# Command line usage remains the same
tsimsh> network status summary --limit "hq-*"

# Internal API usage with configuration loading
import yaml
from tsim.simulators.network_status import NetworkStatusManager
from tsim.core.config_loader import load_traceroute_config

# Load configuration from traceroute_simulator.yaml
config = load_traceroute_config()
network_status_config = config.get('network_status', {})

# Initialize manager with configuration
manager = NetworkStatusManager(
    facts_dir="/path/to/facts",
    config=network_status_config
)

# Get status with caching
status = manager.get_status(
    function="summary",
    namespaces=["hq-gw", "hq-core"],
    use_cache=True
)

# Direct cache control
manager.invalidate_cache("hq-gw")  # Invalidate specific namespace
manager.warm_cache(["hq-*"])  # Pre-populate cache for namespaces
```

### C. Configuration Schema (YAML)
```yaml
# Schema for network_status configuration section
network_status:
  type: object
  properties:
    cache:
      type: object
      properties:
        enabled: 
          type: boolean
          default: true
        base_path: 
          type: string
          default: "/dev/shm/tsim/network_status_cache"
        expiration_seconds: 
          type: integer
          minimum: 0
          default: 3600
        max_size_mb: 
          type: integer
          minimum: 1
          default: 100
        compression: 
          type: boolean
          default: false
        cleanup_interval:
          type: integer
          minimum: 0
          default: 7200
    parallelization:
      type: object
      properties:
        enabled:
          type: boolean
          default: true
        max_workers: 
          type: integer
          minimum: 1
          maximum: 100
          default: 20
        timeout_per_namespace: 
          type: integer
          minimum: 1
          default: 5
        batch_size:
          type: integer
          minimum: 1
          default: 50
    collection:
      type: object
      properties:
        interfaces:
          type: boolean
          default: true
        routes:
          type: boolean
          default: true
        rules:
          type: boolean
          default: true
        iptables:
          type: boolean
          default: true
        ipsets:
          type: boolean
          default: true
    formatting:
      type: object
      properties:
        translate_interface_names:
          type: boolean
          default: true
        show_original_names:
          type: boolean
          default: true
        json_indent:
          type: integer
          minimum: 0
          maximum: 8
          default: 2
    performance:
      type: object
      properties:
        use_json_commands:
          type: boolean
          default: true
        cache_warmup:
          type: boolean
          default: false
        stale_cache_timeout:
          type: integer
          minimum: 0
          default: 300
```

## Timeline Summary

- **Week 1**: Foundation + Start Data Collection
- **Week 2**: Complete Data Collection + Formatting
- **Week 3**: Cache Integration + Command Updates
- **Week 4**: Testing + Optimization + Documentation

Total estimated effort: 4 weeks for complete implementation