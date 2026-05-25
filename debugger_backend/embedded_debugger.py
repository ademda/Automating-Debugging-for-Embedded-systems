import logging
import shutil
import time
from typing import Dict, List, Optional, Any
from pygdbmi.gdbcontroller import GdbController

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmbeddedDebugger:
    
    def __init__(self, gdb_path: str = "arm-none-eabi-gdb", timeout: int = 5):
        self.gdb_path = gdb_path
        self.timeout = timeout
        self.gdb_controller: Optional[GdbController] = None
        self.is_connected = False
        logger.info(f"EmbeddedDebugger initialized with gdb_path={gdb_path}, timeout={timeout}s")
    
    def connect(self) -> bool:
        try:
            resolved_gdb = shutil.which(self.gdb_path) or self.gdb_path
            logger.info(f"Using GDB at: {resolved_gdb}")
            
            self.gdb_controller = GdbController(command=[resolved_gdb, '--interpreter=mi3'])
            self.is_connected = True
            logger.info("GDB controller initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GDB controller: {e}")
            self.is_connected = False
            return False
    
    def _check_connected(self):
        if not self.is_connected:
            raise RuntimeError("Not connected to GDB")
    
    def _execute_gdb(self, cmd: str, timeout: int = None) -> Dict[str, Any]:
        timeout = timeout or self.timeout
        try:
            response = self.gdb_controller.write(cmd, timeout_sec=timeout)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"GDB command failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def _parse_response(self, response: List) -> Dict[str, Any]:
        result = {"status": "unknown", "messages": [], "payload": {}}
        
        if not response:
            result["status"] = "error"
            result["messages"].append("Empty response")
            return result
        
        for resp in response:
            msg_type = resp.get('type', 'unknown')
            msg = resp.get('message', '')
            payload = resp.get('payload', {})
            
            if msg_type == 'result':
                if msg in ['done', 'connected']:
                    result["status"] = "ok"
                elif msg == 'running':
                    result["status"] = "running"
                elif msg == 'error':
                    result["status"] = "error"
                    if payload and isinstance(payload, dict):
                        result["messages"].append(payload.get('msg', 'Unknown error'))
            
            # Catch *stopped bundled inside the same write() response
            if msg_type == 'notify' and msg == 'stopped':
                result["status"] = "ok"
                result["stopped"] = True
                if isinstance(payload, dict):
                    result["reason"] = payload.get("reason", "unknown")
                    result["payload"] = payload
                logger.info(f"Stop notification caught in response: reason={result.get('reason')}")
                return result  # return immediately, we have everything
            
            if payload:
                if isinstance(payload, dict) and isinstance(result["payload"], dict):
                    result["payload"].update(payload)
                else:
                    result["payload"] = payload
        
        return result
    
    def wait_for_stop(self, timeout: int = 10) -> Dict[str, Any]:
        """Poll GDB responses until we get a *stopped notification."""
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                responses = self.gdb_controller.get_gdb_response(
                    timeout_sec=1, 
                    raise_error_on_timeout=False
                )
                if not responses:
                    continue
                    
                for resp in responses:
                    msg_type = resp.get('type', '')
                    message = resp.get('message', '')
                    
                    # Async notify: *stopped
                    if msg_type == 'notify' and message == 'stopped':
                        payload = resp.get('payload', {})
                        reason = payload.get('reason', 'unknown') if isinstance(payload, dict) else 'unknown'
                        logger.info(f"Target stopped: reason={reason}")
                        return {"status": "ok", "reason": reason, "payload": payload}
                        
            except Exception as e:
                logger.debug(f"Polling: {e}")
                continue
        
        return {"status": "error", "message": f"Target did not stop within {timeout}s"}

    def get_target_state(self) -> str:
        """Returns 'halted', 'running', or 'unknown'."""
        try:
            responses = self.gdb_controller.get_gdb_response(
                timeout_sec=0.5,
                raise_error_on_timeout=False
            )
            # Check for any pending async notifications first
            if responses:
                for resp in responses:
                    if resp.get('type') == 'notify':
                        msg = resp.get('message', '')
                        if msg == 'stopped':
                            return 'halted'
                        elif msg == 'running':
                            return 'running'
        except Exception:
            pass

        # Ask GDB directly via monitor
        result = self._execute_gdb('monitor reg pc', timeout=2)
        if result["status"] == "error":
            return 'unknown'
        return 'halted'  # if monitor responded, target is halted

    def load_symbol_table(self, elf_path: str) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb(f'-file-exec-and-symbols "{elf_path}"')
        if result["status"] == "ok":
            logger.info(f"Loaded symbol table from {elf_path}")
        return result
    
    def select_target(self, host: str = "localhost", port: int = 3333) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb(f'-target-select extended-remote {host}:{port}', timeout=5)
        if result["status"] == "ok":
            logger.info(f"Connected to target at {host}:{port}")
        return result
    
    def reset_halt(self) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb('monitor reset halt', timeout=10)
        # Give OpenOCD time to actually halt the core
        time.sleep(1.0)
        # Drain any pending async notifications
        try:
            self.gdb_controller.get_gdb_response(timeout_sec=1, raise_error_on_timeout=False)
        except Exception:
            pass
        return result
    
    def insert_breakpoint(self, location: str, hardware: bool = True) -> Dict[str, Any]:
        self._check_connected()
        hw_flag = "-h " if hardware else ""
        result = self._execute_gdb(f'-break-insert {hw_flag}"{location}"')
        
        if result["status"] == "ok" and isinstance(result.get("payload"), dict):
            bkpt = result["payload"].get("bkpt", {})
            if isinstance(bkpt, dict) and "number" in bkpt:
                result["breakpoint_id"] = bkpt["number"]
                logger.info(f"Breakpoint {bkpt['number']} inserted at {location}")
        return result
    
    def delete_breakpoint(self, breakpoint_id: int) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb(f'-break-delete {breakpoint_id}')
    
    def insert_watchpoint(self, expression: str) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb(f'-break-watch "{expression}"')
    
    def evaluate_expression(self, expression: str) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb(f'-data-evaluate-expression "{expression}"')
    
    def list_locals(self) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb('-stack-list-locals --simple-values')
    
    def list_frames(self) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb('-stack-list-frames')
    
    def list_registers(self, format: str = "x") -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb(f'-data-list-register-values {format}')
    
    def read_memory(self, address: str, length: int) -> Dict[str, Any]:
        self._check_connected()
        return self._execute_gdb(f'-data-read-memory-bytes {address} {length}')
    
    def execute_continue(self) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb('-exec-continue', timeout=5)
        # If stop notification already bundled in response, don't wait again
        if result.get("stopped"):
            logger.info("Stop already received in continue response")
            return result
        return result
    
    def execute_next(self) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb('-exec-next', timeout=10)
        if result.get("stopped"):
            return result
        # Not bundled — wait for async notification
        return self.wait_for_stop(timeout=10)

    def execute_step(self) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb('-exec-step', timeout=10)
        if result.get("stopped"):
            return result
        return self.wait_for_stop(timeout=10)

    def execute_finish(self) -> Dict[str, Any]:
        self._check_connected()
        result = self._execute_gdb('-exec-finish', timeout=10)
        if result.get("stopped"):
            return result
        return self.wait_for_stop(timeout=10)
    
    def execute_interrupt(self) -> Dict[str, Any]:
        self._check_connected()
        
        state = self.get_target_state()
        logger.info(f"Target state before interrupt: {state}")
        
        if state == 'halted':
            # Already halted, nothing to do
            logger.info("Target already halted, skipping interrupt")
            return {"status": "ok", "reason": "already-halted"}
        
        result = self._execute_gdb('-exec-interrupt')
        if result["status"] in ("ok", "running", "unknown"):
            stop_result = self.wait_for_stop(timeout=5)
            return stop_result
        return result
    
    def disconnect(self) -> Dict[str, Any]:
        try:
            if self.gdb_controller:
                result = self._execute_gdb('-gdb-exit')
                self.is_connected = False
                self.gdb_controller = None
                logger.info("GDB disconnected cleanly")
                return result
            return {"status": "ok", "message": "Already disconnected"}
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            self.is_connected = False
            return {"status": "error", "message": str(e)}


def create_debugger(gdb_path: str = "arm-none-eabi-gdb") -> EmbeddedDebugger:
    debugger = EmbeddedDebugger(gdb_path=gdb_path)
    if debugger.connect():
        return debugger
    return None
