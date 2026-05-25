# Embedded Debugger Backend

Python middleware for autonomous debugging of STM32 MCUs via GDB/MI protocol.

## Architecture

```
[ LLM Agent (Future Layer) ]
           ↓
[ EmbeddedDebugger (Python Backend) ] ← YOU ARE HERE
           ↓
[ pygdbmi.GdbController ]
           ↓
[ arm-none-eabi-gdb --interpreter=mi3 ]
           ↓
[ OpenOCD Server (TCP:3333) ]
           ↓
[ ST-LINK Hardware Probe ]
           ↓
[ STM32 Microcontroller ]
```

## Files

- **embedded_debugger.py**: Main `EmbeddedDebugger` class
  - 200+ lines of core functionality
  - Thread-safe GDB communication
  - Automatic timeout guards
  - State tracking for target halts
  
- **__init__.py**: Package exports
  - Easy imports: `from debugger_backend import EmbeddedDebugger`

## Core Classes

### EmbeddedDebugger

Main interface for all debugging operations. Features:

- **Session Management**: Connect, load symbols, select target, reset
- **Breakpoints**: Hardware breakpoints, software breakpoints, watchpoints
- **Execution Control**: Continue, step, next, finish, interrupt
- **State Inspection**: Locals, frames, registers, memory read, expression eval
- **State Tracking**: Automatic parsing of GDB async responses
- **Timeout Guards**: Prevents hangs from infinite loops
- **Thread Safety**: Lock-protected GDB communication

### TargetState

Dataclass representing current MCU state:
```python
@dataclass
class TargetState:
    stopped: bool
    reason: StopReason
    thread_id: Optional[int]
    frame_line: Optional[int]
    frame_file: Optional[str]
    frame_func: Optional[str]
    frame_addr: Optional[str]
    signal_name: Optional[str]
    signal_meaning: Optional[str]
    raw_response: Optional[Dict]
```

### StopReason

Enum of target halt reasons:
- `BREAKPOINT_HIT`
- `END_STEPPING_RANGE`
- `SIGNAL`
- `EXITED`
- `EXITED_NORMALLY`
- `FUNCTION_FINISHED`
- `UNKNOWN`

## Usage Patterns

### Minimal Example

```python
from debugger_backend import EmbeddedDebugger

debugger = EmbeddedDebugger()
debugger.connect()
debugger.load_symbol_table("firmware.elf")
debugger.select_target("localhost", 3333)
debugger.reset_halt()

# Set breakpoint and run
debugger.insert_breakpoint("main.c:42", hardware=True)
debugger.execute_continue()

# Inspect state
state = debugger.get_state()
print(f"Halted at {state['frame_file']}:{state['frame_line']}")

debugger.disconnect()
```

### With Error Handling

```python
debugger = EmbeddedDebugger(timeout=5)

if not debugger.connect():
    print("Failed to connect GDB")
    exit(1)

try:
    response = debugger.load_symbol_table("firmware.elf")
    if response["status"] != "ok":
        print(f"Error: {response['messages']}")
        return
    
    # ... rest of debugging
    
except Exception as e:
    print(f"Error: {e}")
finally:
    debugger.disconnect()
```

## Response Format

All methods return structured responses:

```python
{
    "status": "ok" | "error" | "running",
    "messages": ["list", "of", "errors"],
    "payload": {
        # GDB/MI specific data
    },
    "breakpoint_id": 1,  # when applicable
    "timeout_warning": False  # if timeout occurred
}
```

## Key Implementation Details

### 1. GDB/MI Parsing

The debugger uses pygdbmi to parse GDB's machine interface output:
- Result Records: Direct command responses (`^done`, `^error`, etc.)
- Async Exec Records: Target stops (`*stopped,reason="breakpoint-hit"`)
- Stream Output: Console messages

### 2. State Tracking

Automatic parsing of async stop records to extract:
- Breakpoint reason
- Current file, line, function
- Stack frame information
- Signal/crash information

### 3. Timeout Protection

Built-in guard against infinite loops:
```python
# If execution doesn't return within timeout, 
# automatically sends -exec-interrupt
response, timed_out = self._execute_with_timeout('-exec-continue')
if timed_out:
    # Target was interrupted from infinite loop
    print("Timeout detected, sent interrupt")
```

### 4. Thread Safety

All GDB writes are lock-protected:
```python
with self._lock:
    response = self.gdb_controller.write(cmd)
```

## GDB/MI Commands Supported

### Session Setup
- `-file-exec-and-symbols` - Load symbols
- `-target-select remote` - Connect to OpenOCD
- `-gdb-exit` - Disconnect
- `monitor reset halt` - Hardware reset

### Breakpoints
- `-break-insert [-h]` - Insert breakpoint/hardware breakpoint
- `-break-watch` - Set data watchpoint
- `-break-delete` - Remove breakpoint

### Execution
- `-exec-continue` - Run at full speed
- `-exec-next` - Step over
- `-exec-step` - Step into
- `-exec-finish` - Step out
- `-exec-interrupt` - Halt

### Inspection
- `-data-evaluate-expression` - Evaluate variable/expression
- `-stack-list-locals` - List local variables
- `-stack-list-frames` - Stack backtrace
- `-data-list-register-values` - Dump registers
- `-data-read-memory-bytes` - Read memory

## Logging

Comprehensive logging enabled:

```python
import logging
from debugger_backend import logger

# Enable debug logging
logger.setLevel(logging.DEBUG)

# Add handler
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)
```

Log levels:
- **DEBUG**: Detailed GDB communication
- **INFO**: Session events (connect, breakpoint set, etc.)
- **ERROR**: Operation failures

## Integration Points

This layer is designed to interface with:

1. **LLM Agent Layer** (future)
   - Accepts tool invocations
   - Returns JSON responses
   - Provides async event callbacks

2. **Persistent State Store**
   - Current target state
   - Breakpoint map
   - Variable snapshots

3. **Analysis Engine** (future)
   - Parse patterns in execution
   - Correlate variables with failures
   - Suggest next debugging steps

## Known Limitations

- Single connection only (no multi-target debugging)
- Limited to local OpenOCD instances
- ARM Cortex-M MCUs only (extensible to others)
- GDB/MI protocol specific

## Future Enhancements

- [ ] Multi-target debugging
- [ ] Remote OpenOCD support
- [ ] Other MCU architectures (RISC-V, MSP430)
- [ ] Streaming breakpoint conditions
- [ ] Advanced register aliases
- [ ] Peripheral aware inspection
- [ ] Event subscription system
- [ ] Automatic crash log parsing
