import json
import threading
import time
import logging
import shutil
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
from pygdbmi.gdbcontroller import GdbController

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StopReason(Enum):
    BREAKPOINT_HIT = "breakpoint-hit"
    END_STEPPING_RANGE = "end-stepping-range"
    SIGNAL = "signal"
    EXITED = "exited"
    EXITED_NORMALLY = "exited-normally"
    FUNCTION_FINISHED = "function-finished"
    UNKNOWN = "unknown"


@dataclass
class TargetState:
    stopped: bool
    reason: StopReason
    thread_id: Optional[int] = None
    frame_line: Optional[int] = None
    frame_file: Optional[str] = None
    frame_func: Optional[str] = None
    frame_addr: Optional[str] = None
    signal_name: Optional[str] = None
    signal_meaning: Optional[str] = None
    raw_response: Optional[Dict] = None

    def to_dict(self):
        result = asdict(self)
        result['reason'] = self.reason.value
        return result


class EmbeddedDebugger:
    
    def __init__(self, gdb_path: str = "arm-none-eabi-gdb", timeout: int = 5):
        self.gdb_path = gdb_path
        self.timeout = timeout
        self.gdb_controller: Optional[GdbController] = None
        self.current_state = TargetState(
            stopped=False, 
            reason=StopReason.UNKNOWN
        )
        self.breakpoint_map: Dict[int, Dict] = {}
        self.is_connected = False
        self._lock = threading.Lock()
        logger.info(f"EmbeddedDebugger initialized with gdb_path={gdb_path}, timeout={timeout}s")
    
    def connect(self) -> bool:
        try:
            with self._lock:
                if self.gdb_controller is not None:
                    logger.warning("GDB controller already initialized")
                    return True
                
                resolved_gdb = shutil.which(self.gdb_path)
                if not resolved_gdb:
                    resolved_gdb = self.gdb_path
                
                logger.info(f"Using GDB at: {resolved_gdb}")
                
                gdb_cmd = [resolved_gdb, '--interpreter=mi3']
                self.gdb_controller = GdbController(command=gdb_cmd)
                self.is_connected = True
                logger.info("GDB controller initialized successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to initialize GDB controller: {e}")
            self.is_connected = False
            return False
    
    def load_symbol_table(self, elf_path: str) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write(f'-file-exec-and-symbols "{elf_path}"')
            result = self._parse_response(response)
            logger.info(f"Loaded symbol table from {elf_path}")
            return result
        except Exception as e:
            logger.error(f"Failed to load symbol table: {e}")
            return {"status": "error", "message": str(e)}
    
    def select_target(self, host: str = "localhost", port: int = 3333) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write(f'-target-select remote {host}:{port}', timeout_sec=5)
            result = self._parse_response(response)
            logger.info(f"Connected to target at {host}:{port}")
            return result
        except Exception as e:
            logger.error(f"Failed to select target: {e}")
            return {"status": "error", "message": str(e)}
    
    def reset_halt(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write('monitor reset halt')
            result = self._parse_response(response)
            self.current_state.stopped = True
            logger.info("Target reset and halted")
            return result
        except Exception as e:
            logger.error(f"Failed to reset target: {e}")
            return {"status": "error", "message": str(e)}
    
    def disconnect(self) -> Dict[str, Any]:
        try:
            if self.gdb_controller:
                response = self.gdb_controller.write('-gdb-exit')
                result = self._parse_response(response)
                self.is_connected = False
                self.gdb_controller = None
                logger.info("GDB disconnected cleanly")
                return result
            return {"status": "ok", "message": "Already disconnected"}
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            self.is_connected = False
            return {"status": "error", "message": str(e)}
    
    def insert_breakpoint(self, location: str, hardware: bool = True) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            hw_flag = "-h " if hardware else ""
            cmd = f'-break-insert {hw_flag}"{location}"'
            response = self.gdb_controller.write(cmd)
            result = self._parse_response(response)
            if 'bkpt' in str(response):
                for resp in response:
                    if resp.get('payload') and 'bkpt' in resp['payload']:
                        bp_id = resp['payload']['bkpt'].get('number')
                        if bp_id:
                            self.breakpoint_map[int(bp_id)] = {
                                'location': location,
                                'hardware': hardware
                            }
                            result['breakpoint_id'] = bp_id
                            logger.info(f"Breakpoint {bp_id} inserted at {location}")
            
            return result
        except Exception as e:
            logger.error(f"Failed to insert breakpoint: {e}")
            return {"status": "error", "message": str(e)}
    
    def insert_watchpoint(self, expression: str) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            cmd = f'-break-watch "{expression}"'
            response = self.gdb_controller.write(cmd)
            result = self._parse_response(response)
            logger.info(f"Watchpoint set on {expression}")
            return result
        except Exception as e:
            logger.error(f"Failed to set watchpoint: {e}")
            return {"status": "error", "message": str(e)}
    
    def delete_breakpoint(self, breakpoint_id: int) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write(f'-break-delete {breakpoint_id}')
            result = self._parse_response(response)
            
            if breakpoint_id in self.breakpoint_map:
                del self.breakpoint_map[breakpoint_id]
                logger.info(f"Breakpoint {breakpoint_id} deleted")
            
            return result
        except Exception as e:
            logger.error(f"Failed to delete breakpoint: {e}")
            return {"status": "error", "message": str(e)}
    
    def _execute_with_timeout(self, cmd: str) -> Tuple[List, bool]:
        response = [None]
        timed_out = [False]
        
        def execute():
            response[0] = self.gdb_controller.write(cmd, timeout_sec=self.timeout)
        
        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout + 1)
        
        if thread.is_alive():
            timed_out[0] = True
            logger.warning(f"Command timed out: {cmd}")
            try:
                self.gdb_controller.write('-exec-interrupt')
                logger.info("Interrupt sent to recover from timeout")
            except:
                pass
        
        return response[0] or [], timed_out[0]
    
    def execute_continue(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response, timed_out = self._execute_with_timeout('-exec-continue')
            result = self._parse_response(response)
            
            if timed_out:
                result['timeout_warning'] = True
                logger.warning("Continue command timed out")
            
            self._update_state_from_response(response)
            logger.info(f"Execution continued, state: {self.current_state.reason.value}")
            return result
        except Exception as e:
            logger.error(f"Failed to continue execution: {e}")
            return {"status": "error", "message": str(e)}
    
    def execute_next(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response, timed_out = self._execute_with_timeout('-exec-next')
            result = self._parse_response(response)
            self._update_state_from_response(response)
            logger.info(f"Stepped next, state: {self.current_state.reason.value}")
            return result
        except Exception as e:
            logger.error(f"Failed to step next: {e}")
            return {"status": "error", "message": str(e)}
    
    def execute_step(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response, timed_out = self._execute_with_timeout('-exec-step')
            result = self._parse_response(response)
            self._update_state_from_response(response)
            logger.info(f"Stepped into function, state: {self.current_state.reason.value}")
            return result
        except Exception as e:
            logger.error(f"Failed to step: {e}")
            return {"status": "error", "message": str(e)}
    
    def execute_finish(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response, timed_out = self._execute_with_timeout('-exec-finish')
            result = self._parse_response(response)
            self._update_state_from_response(response)
            logger.info(f"Executed to function return, state: {self.current_state.reason.value}")
            return result
        except Exception as e:
            logger.error(f"Failed to finish execution: {e}")
            return {"status": "error", "message": str(e)}
    
    def execute_interrupt(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write('-exec-interrupt')
            result = self._parse_response(response)
            self._update_state_from_response(response)
            self.current_state.stopped = True
            logger.info("Target interrupted and halted")
            return result
        except Exception as e:
            logger.error(f"Failed to interrupt execution: {e}")
            return {"status": "error", "message": str(e)}
    
    def evaluate_expression(self, expression: str) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            cmd = f'-data-evaluate-expression "{expression}"'
            response = self.gdb_controller.write(cmd)
            result = self._parse_response(response)
            logger.debug(f"Evaluated expression: {expression} = {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to evaluate expression: {e}")
            return {"status": "error", "message": str(e)}
    
    def list_locals(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write('-stack-list-locals --simple-values')
            result = self._parse_response(response)
            logger.debug(f"Listed local variables")
            return result
        except Exception as e:
            logger.error(f"Failed to list locals: {e}")
            return {"status": "error", "message": str(e)}
    
    def list_frames(self) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write('-stack-list-frames')
            result = self._parse_response(response)
            logger.debug(f"Retrieved stack frames")
            return result
        except Exception as e:
            logger.error(f"Failed to list frames: {e}")
            return {"status": "error", "message": str(e)}
    
    def list_registers(self, format: str = "x") -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            response = self.gdb_controller.write(f'-data-list-register-values {format}')
            result = self._parse_response(response)
            logger.debug(f"Retrieved register values in format: {format}")
            return result
        except Exception as e:
            logger.error(f"Failed to list registers: {e}")
            return {"status": "error", "message": str(e)}
    
    def read_memory(self, address: str, length: int) -> Dict[str, Any]:
        if not self.is_connected:
            logger.error("Not connected to GDB")
            return {"status": "error", "message": "Not connected"}
        
        try:
            cmd = f'-data-read-memory-bytes {address} {length}'
            response = self.gdb_controller.write(cmd)
            result = self._parse_response(response)
            logger.debug(f"Read memory from {address}, length {length}")
            return result
        except Exception as e:
            logger.error(f"Failed to read memory: {e}")
            return {"status": "error", "message": str(e)}
    
    def _parse_response(self, response: List) -> Dict[str, Any]:
        result = {
            "status": "unknown",
            "messages": [],
            "payload": {}
        }
        
        if not response:
            result["status"] = "error"
            result["messages"].append("Empty response")
            return result
        
        for resp in response:
            msg_type = resp.get('type', 'unknown')
            msg = resp.get('message', '')
            payload = resp.get('payload', {})
            if msg_type == 'result':
                if msg == 'done' or msg == 'connected':
                    result["status"] = "ok"
                elif msg == 'running':
                    result["status"] = "running"
                elif msg == 'error':
                    result["status"] = "error"
                    if payload:
                        result["messages"].append(payload.get('msg', 'Unknown error'))
            if payload:
                if isinstance(payload, dict):
                    if isinstance(result["payload"], dict):
                        result["payload"].update(payload)
                    else:
                        result["payload"] = payload
                else:
                    result["payload"] = payload
            if msg_type in ['exec-async-output', 'notify-async-output']:
                result["async_event"] = msg
        
        return result
    
    def _update_state_from_response(self, response: List) -> None:
        for resp in response:
            payload = resp.get('payload', {})
            if resp.get('type') == 'exec-async-output' and resp.get('message') == 'stopped':
                self.current_state.stopped = True
                self.current_state.raw_response = resp
                reason_str = payload.get('reason', 'unknown')
                try:
                    self.current_state.reason = StopReason(reason_str)
                except ValueError:
                    self.current_state.reason = StopReason.UNKNOWN
                if 'frame' in payload:
                    frame = payload['frame']
                    self.current_state.frame_line = int(frame.get('line', 0))
                    self.current_state.frame_file = frame.get('file', None)
                    self.current_state.frame_func = frame.get('func', None)
                    self.current_state.frame_addr = frame.get('addr', None)
                if 'thread-id' in payload:
                    self.current_state.thread_id = int(payload['thread-id'])
                if 'signal-name' in payload:
                    self.current_state.signal_name = payload['signal-name']
                    self.current_state.signal_meaning = payload.get('signal-meaning', None)
    
    def get_state(self) -> Dict[str, Any]:
        return self.current_state.to_dict()
    
    def is_running(self) -> bool:
        return not self.current_state.stopped
    
    def is_stopped(self) -> bool:
        return self.current_state.stopped


def create_debugger(gdb_path: str = "arm-none-eabi-gdb") -> EmbeddedDebugger:
    debugger = EmbeddedDebugger(gdb_path=gdb_path)
    if debugger.connect():
        return debugger
    return None
