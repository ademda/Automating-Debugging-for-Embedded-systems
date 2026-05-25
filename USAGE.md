# EmbeddedDebugger - Python Backend Usage Guide

## Overview

`EmbeddedDebugger` is a Python wrapper around `pygdbmi.GdbController` that provides a high-level API for autonomous debugging of STM32 MCUs via arm-none-eabi-gdb and OpenOCD.

## Installation

### Prerequisites

1. **arm-none-eabi-gdb** - ARM GCC toolchain debugger
   ```bash
   # Ubuntu/Debian
   sudo apt-get install gcc-arm-none-eabi gdb-multiarch
   
   # macOS
   brew install arm-none-eabi-binutils
   ```

2. **OpenOCD** - On-chip debugger bridge
   ```bash
   # Ubuntu/Debian
   sudo apt-get install openocd
   
   # macOS
   brew install openocd
   ```

3. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Verify Installation

```bash
# Check GDB is installed
arm-none-eabi-gdb --version

# Check OpenOCD is available
openocd --version
```

## Quick Start

### 1. Launch OpenOCD Server

In a terminal, run:
```bash
openocd -f interface/stlink-v2.cfg -f target/stm32f4x.cfg
# Or for STM32F1:
openocd -f interface/stlink-v2.cfg -f target/stm32f1x.cfg
```

You should see:
```
Open On-Chip Debugger 0.10.0
...
Info : listening on port 3333
```

### 2. Use the Debugger

```python
from debugger_backend import EmbeddedDebugger

# Create and connect debugger
debugger = EmbeddedDebugger(timeout=5)
debugger.connect()

# Load your compiled ELF file
response = debugger.load_symbol_table("/path/to/firmware.elf")
print(response)

# Connect to target via OpenOCD
response = debugger.select_target("localhost", 3333)
print(response)

# Reset and halt the target
response = debugger.reset_halt()
print(response)

# Set a hardware breakpoint
response = debugger.insert_breakpoint("main.c:42", hardware=True)
bp_id = response.get("breakpoint_id")
print(f"Breakpoint ID: {bp_id}")

# Read a variable
response = debugger.evaluate_expression("temperature")
print(f"temperature = {response}")

# Get stack trace
response = debugger.list_frames()
print(response)

# Get local variables
response = debugger.list_locals()
print(response)

# Get CPU registers
response = debugger.list_registers(format="x")  # hex format
print(response)

# Continue execution
response = debugger.execute_continue()
print(f"Execution state: {debugger.get_state()}")

# Clean up
debugger.disconnect()
```

## API Reference

### Session Setup & Target Connection

#### `connect() -> bool`
Initialize GDB controller and launch arm-none-eabi-gdb
```python
if debugger.connect():
    print("Connected to GDB")
```

#### `load_symbol_table(elf_path: str) -> Dict[str, Any]`
Load executable file and debug symbols (-file-exec-and-symbols)
```python
response = debugger.load_symbol_table("./firmware.elf")
```

#### `select_target(host: str = "localhost", port: int = 3333) -> Dict[str, Any]`
Connect to OpenOCD server (-target-select remote)
```python
response = debugger.select_target("localhost", 3333)
```

#### `reset_halt() -> Dict[str, Any]`
Force hardware reset and halt (monitor reset halt)
```python
response = debugger.reset_halt()
```

#### `disconnect() -> Dict[str, Any]`
Cleanly terminate GDB (-gdb-exit)
```python
response = debugger.disconnect()
```

### Breakpoints & Watchpoints

#### `insert_breakpoint(location: str, hardware: bool = True) -> Dict[str, Any]`
Insert breakpoint at location (-break-insert)

**Parameters:**
- `location`: "main.c:42" or "function_name"
- `hardware`: Use hardware breakpoint (required for Flash code)

```python
response = debugger.insert_breakpoint("main.c:42", hardware=True)
bp_id = response.get("breakpoint_id")
```

#### `insert_watchpoint(expression: str) -> Dict[str, Any]`
Set data watchpoint (-break-watch)
```python
response = debugger.insert_watchpoint("my_variable")
```

#### `delete_breakpoint(breakpoint_id: int) -> Dict[str, Any]`
Remove breakpoint by ID (-break-delete)
```python
response = debugger.delete_breakpoint(1)
```

### Execution Control

#### `execute_continue() -> Dict[str, Any]`
Resume execution at full speed (-exec-continue)
```python
response = debugger.execute_continue()
# Target runs until breakpoint/fault
state = debugger.get_state()
print(f"Stopped at: {state['frame_file']}:{state['frame_line']}")
```

#### `execute_next() -> Dict[str, Any]`
Step over current line (-exec-next)
```python
response = debugger.execute_next()
```

#### `execute_step() -> Dict[str, Any]`
Step into function call (-exec-step)
```python
response = debugger.execute_step()
```

#### `execute_finish() -> Dict[str, Any]`
Execute until function returns (-exec-finish)
```python
response = debugger.execute_finish()
```

#### `execute_interrupt() -> Dict[str, Any]`
Force halt immediately (-exec-interrupt)
```python
response = debugger.execute_interrupt()
```

### State Inspection & Variables

#### `evaluate_expression(expression: str) -> Dict[str, Any]`
Evaluate C expression (-data-evaluate-expression)
```python
response = debugger.evaluate_expression("temperature")
value = response.get("payload", {}).get("value")

response = debugger.evaluate_expression("sensor.raw_adc & 0xFF")
```

#### `list_locals() -> Dict[str, Any]`
List all local variables in current scope (-stack-list-locals)
```python
response = debugger.list_locals()
# Returns all locals with types and values
```

#### `list_frames() -> Dict[str, Any]`
Get complete stack backtrace (-stack-list-frames)
```python
response = debugger.list_frames()
# Useful for tracking crash paths
```

#### `list_registers(format: str = "x") -> Dict[str, Any]`
Dump CPU register values (-data-list-register-values)

**Parameters:**
- `format`: "x" (hex), "d" (decimal), "t" (binary), "o" (octal), "r" (raw)

```python
response = debugger.list_registers(format="x")
# Returns R0-R15, PC, LR, PSR, etc.
```

#### `read_memory(address: str, length: int) -> Dict[str, Any]`
Read raw memory bytes (-data-read-memory-bytes)
```python
response = debugger.read_memory("0x20000000", 32)  # Read 32 bytes from RAM
```

### State Management

#### `get_state() -> Dict[str, Any]`
Get current target state
```python
state = debugger.get_state()
print(state)
# {
#   "stopped": true,
#   "reason": "breakpoint-hit",
#   "frame_file": "main.c",
#   "frame_line": 42,
#   "frame_func": "main",
#   "thread_id": 1,
#   ...
# }
```

#### `is_stopped() -> bool`
Check if target is halted
```python
if debugger.is_stopped():
    print("Target halted")
```

#### `is_running() -> bool`
Check if target is executing
```python
if debugger.is_running():
    print("Target running")
```

## Example: Complete Debugging Session

```python
from debugger_backend import EmbeddedDebugger

debugger = EmbeddedDebugger(timeout=10)
debugger.connect()

try:
    # Setup
    debugger.load_symbol_table("./firmware.elf")
    debugger.select_target("localhost", 3333)
    debugger.reset_halt()
    
    # Set breakpoint
    bp_response = debugger.insert_breakpoint("main.c:42", hardware=True)
    bp_id = bp_response.get("breakpoint_id")
    print(f"Set breakpoint: {bp_id}")
    
    # Run until breakpoint
    debugger.execute_continue()
    state = debugger.get_state()
    print(f"Halted at: {state['frame_file']}:{state['frame_line']}")
    
    # Inspect variables
    locals_resp = debugger.list_locals()
    print("Local variables:", locals_resp)
    
    # Read specific variable
    var_value = debugger.evaluate_expression("counter")
    print(f"counter = {var_value}")
    
    # Check registers
    regs = debugger.list_registers(format="x")
    print("CPU Registers:", regs)
    
    # Step through code
    for i in range(5):
        debugger.execute_step()
        print(f"Step {i+1}: {debugger.get_state()}")
    
    # Cleanup
    debugger.delete_breakpoint(bp_id)
    
finally:
    debugger.disconnect()
```

## Response Format

All methods return a dictionary with the following structure:

```python
{
    "status": "ok" | "error" | "running",
    "messages": ["list of messages"],
    "payload": {
        # GDB/MI response data
        # Contents vary by command
    },
    "async_event": "optional async event name"
}
```

### Example Response

```python
response = debugger.evaluate_expression("counter")
# {
#   "status": "ok",
#   "messages": [],
#   "payload": {
#       "value": "42",
#       "type": "int"
#   }
# }
```

## Error Handling

```python
try:
    response = debugger.load_symbol_table("firmware.elf")
    if response["status"] == "error":
        print(f"Error: {response['messages']}")
except Exception as e:
    print(f"Exception: {e}")
```

## Timeout & Hang Guard

The debugger has built-in timeout protection for execution commands:

```python
debugger = EmbeddedDebugger(timeout=5)  # 5 second timeout

# If execution doesn't return within 5s,
# an interrupt is automatically sent
response = debugger.execute_continue()
if response.get("timeout_warning"):
    print("Execution timed out - interrupt sent")
```

## Logging

Enable detailed logging:

```python
import logging
from debugger_backend import logger

logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)
```

## Testing

Run the test suite:

```bash
# Basic tests
python tests/test_debugger.py

# With ELF file
python tests/test_debugger.py --elf ./firmware.elf

# Verbose output
python tests/test_debugger.py --verbose
```

## Troubleshooting

### "arm-none-eabi-gdb: command not found"
Install the ARM toolchain:
```bash
sudo apt-get install gcc-arm-none-eabi
```

### "Connection refused on localhost:3333"
OpenOCD isn't running. Start it:
```bash
openocd -f interface/stlink-v2.cfg -f target/stm32f4x.cfg
```

### "Timeout on -exec-continue"
Target is stuck in infinite loop. The debugger automatically sends interrupt.
Check your code for loops without breakpoints.

### GDB returns error responses
Check:
1. ELF file exists and is valid
2. Symbol table was loaded
3. Target is connected and halted
4. OpenOCD is running and detects the board

## Next Steps

This is the pure Python layer. The LLM agent layer will:
1. Parse `get_state()` responses
2. Determine debugging strategy
3. Invoke tool methods to gather more information
4. Make decisions (set breakpoint, step, read variables, etc.)
5. Analyze patterns to isolate bugs
