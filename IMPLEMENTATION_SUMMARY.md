# Python Backend Implementation Complete

## What Has Been Built

A complete, production-ready Python middleware layer for autonomous embedded systems debugging. The backend wraps GDB/MI protocol via `pygdbmi` and exposes 18 GDB commands as high-level Python methods.

## Implementation Summary

### Core Module: `EmbeddedDebugger` class
- **Location**: `debugger_backend/embedded_debugger.py` (600+ lines)
- **Initialization**: `EmbeddedDebugger(gdb_path, timeout)`
- **Connection**: `connect()` - launches arm-none-eabi-gdb with MI3 interpreter

### 18 GDB/MI Commands Implemented

#### Session Setup & Target Connection (3 commands)
1. **`load_symbol_table(elf_path)`** - `-file-exec-and-symbols`
   - Loads debug symbols from compiled ELF file
   
2. **`select_target(host, port)`** - `-target-select remote`
   - Connects to OpenOCD server (default: localhost:3333)
   
3. **`reset_halt()`** - `monitor reset halt`
   - Hardware reset and immediate halt via OpenOCD

Plus: `connect()`, `disconnect()`

#### Breakpoints & Watchpoints (3 commands)
4. **`insert_breakpoint(location, hardware=True)`** - `-break-insert [-h]`
   - Hardware breakpoints for Flash execution (required for ARM)
   - Location format: "main.c:42" or "function_name"
   
5. **`insert_watchpoint(expression)`** - `-break-watch`
   - Data watchpoint on variables/expressions
   
6. **`delete_breakpoint(bp_id)`** - `-break-delete`
   - Remove breakpoints by ID

#### Execution Control (5 commands)
7. **`execute_continue()`** - `-exec-continue` - Resume at full speed
8. **`execute_next()`** - `-exec-next` - Step over line (skip function bodies)
9. **`execute_step()`** - `-exec-step` - Step into functions
10. **`execute_finish()`** - `-exec-finish` - Step out of current function
11. **`execute_interrupt()`** - `-exec-interrupt` - Force halt

#### State Inspection & Variables (5 commands)
12. **`evaluate_expression(expr)`** - `-data-evaluate-expression`
    - Read C variables, struct members, expressions
    
13. **`list_locals()`** - `-stack-list-locals --simple-values`
    - List all local variables in current function scope
    
14. **`list_frames()`** - `-stack-list-frames`
    - Get full stack backtrace of function calls
    
15. **`list_registers(format='x')`** - `-data-list-register-values`
    - Dump CPU registers (R0-R15, PC, LR, PSR, etc.)
    
16. **`read_memory(address, length)`** - `-data-read-memory-bytes`
    - Read raw memory from RAM or peripheral addresses

#### State Management (3 methods)
17. **`get_state()`** - Returns `TargetState` dict with:
    - `stopped`, `reason`, `frame_file`, `frame_line`, `frame_func`, etc.
    
18. **`is_stopped()` / `is_running()`** - State query helpers

### Advanced Features

**Thread Safety**: All GDB communication protected with locks
```python
with self._lock:
    response = self.gdb_controller.write(cmd)
```

**Timeout & Hang Guard**: Prevents infinite loop deadlocks
```python
def _execute_with_timeout(cmd):
    # If execution doesn't return within timeout,
    # automatically sends -exec-interrupt
```

**Automatic State Tracking**: Parses async GDB events
```python
# Automatically updates current_state from:
# *stopped,reason="breakpoint-hit"
# frame={file="main.c",line="42",func="main",...}
```

**Structured Response Parsing**: All methods return clean dicts
```python
{
    "status": "ok|error|running",
    "messages": [],
    "payload": {...},
    "breakpoint_id": "1",  # if applicable
    "timeout_warning": False  # if timeout occurred
}
```

## Data Structures

### TargetState (Dataclass)
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

### StopReason (Enum)
- `BREAKPOINT_HIT` - Hit user breakpoint
- `END_STEPPING_RANGE` - Completed step command
- `SIGNAL` - Caught signal (e.g., SIGSEGV)
- `EXITED` - Program exited
- `EXITED_NORMALLY` - Clean exit
- `FUNCTION_FINISHED` - Completed finish command
- `UNKNOWN` - Unknown reason

## Usage Example

```python
from debugger_backend import EmbeddedDebugger

# Initialize
debugger = EmbeddedDebugger(timeout=10)
debugger.connect()

# Setup
debugger.load_symbol_table("firmware.elf")
debugger.select_target("localhost", 3333)
debugger.reset_halt()

# Debug workflow
bp = debugger.insert_breakpoint("main.c:42", hardware=True)
bp_id = bp.get("breakpoint_id")

debugger.execute_continue()
state = debugger.get_state()
print(f"Halted at {state['frame_file']}:{state['frame_line']}")

locals_vars = debugger.list_locals()
registers = debugger.list_registers(format="x")
stack_trace = debugger.list_frames()

var_value = debugger.evaluate_expression("counter")
print(f"counter = {var_value}")

debugger.execute_step()
debugger.delete_breakpoint(bp_id)
debugger.disconnect()
```

## File Structure

```
c:\Users\dalya\Desktop\embedded systems projects\IA Autonumus debugger\

├── debugger_backend/
│   ├── __init__.py               # Package exports
│   ├── embedded_debugger.py      # Main EmbeddedDebugger class (600+ lines)
│   └── README.md                 # Architecture documentation
│
├── tests/
│   └── test_debugger.py          # Comprehensive test suite
│
├── examples/
│   └── real_world_debugging.py   # Real-world usage scenarios
│
├── demo_api.py                   # API interface demo
├── USAGE.md                      # Detailed API documentation
├── QUICK_REFERENCE.md            # Command reference
├── requirements.txt              # Python dependencies (pygdbmi)
└── Readme.md                     # Project overview
```

## Testing

### Run Full Test Suite
```bash
python tests/test_debugger.py
```

### Run with ELF file
```bash
python tests/test_debugger.py --elf firmware.elf
```

### Show API Demo
```bash
python demo_api.py
```

### Real-world Scenarios
```bash
# Debug UART timeout
python examples/real_world_debugging.py --scenario uart

# Debug memory corruption
python examples/real_world_debugging.py --scenario memory

# Debug HardFault crash
python examples/real_world_debugging.py --scenario hardfault
```

## Dependencies

```bash
pip install -r requirements.txt
# Installs: pygdbmi==0.10.0.post1
```

System requirements:
- `arm-none-eabi-gdb` - ARM GCC toolchain debugger
- `OpenOCD` - On-chip debugger bridge
- Python 3.7+

## Key Design Decisions

1. **pygdbmi wrapper**: Uses GDB's MI protocol for reliable machine-parseable output
2. **Hardware breakpoints only**: STM32 executes from Flash; software BPs won't work
3. **Timeout protection**: Prevents debugger from hanging on infinite loops
4. **Structured responses**: All methods return JSON-compatible dicts for LLM integration
5. **State tracking**: Automatically parses async events for real-time state awareness
6. **Thread safety**: Lock-protected GDB communication

## LLM Integration Ready

This Python layer is designed for seamless LLM integration:
- Clean, structured responses (no parsing needed)
- Comprehensive state information available via `get_state()`
- Error handling and recovery built-in
- All commands timeout-protected
- Ready for agent decision-making tools

## Next Steps (Not Implemented)

For full autonomous debugging system:
1. LLM agent layer - Invoke debugger tools
2. Problem analysis engine - Correlate variable states with failures
3. Knowledge base - Store debugging patterns and solutions
4. Persistent logging - Track debugging sessions
5. Remote support - Extend to other MCU architectures

---

**Status**: Python backend fully implemented and tested.
**Ready for**: LLM agent layer development.
