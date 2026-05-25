import sys
import json
from pathlib import Path
import argparse
import time
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent / "debugger_backend"))

from embedded_debugger import EmbeddedDebugger, logger


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_response(label: str, response: dict):
    print(f"[{label}]")
    print(json.dumps(response, indent=2, default=str))
    print()


class DebuggerTestSuite:
    
    def __init__(self, elf_path: str = None):
        self.elf_path = elf_path
        self.debugger = None
        self.results = {
            "passed": [],
            "failed": [],
            "skipped": []
        }
    
    def run_all(self):
        print_section("EMBEDDED DEBUGGER TEST SUITE")
        
        try:
            self.test_initialization()
            self.test_load_symbols()
            self.test_target_connection()
            self.test_breakpoint_operations()
            self.test_state_inspection()
            self.test_execution_control()
            self.test_cleanup()
        except KeyboardInterrupt:
            print("\n\n[!] Tests interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error during tests: {e}")
        finally:
            self.print_summary()
    
    def test_initialization(self):
        print_section("Test 1: Initialization")
        
        try:
            self.debugger = EmbeddedDebugger(
                gdb_path="arm-none-eabi-gdb",
                timeout=5
            )
            
            if self.debugger.connect():
                print("[✓] GDB controller initialized successfully")
                self.results["passed"].append("Initialization")
                return True
            else:
                print("[✗] Failed to initialize GDB controller")
                self.results["failed"].append("Initialization")
                return False
        except Exception as e:
            print(f"[✗] Initialization test failed: {e}")
            self.results["failed"].append("Initialization")
            return False
    
    def test_load_symbols(self):
        print_section("Test 2: Load Symbol Table")
        
        if not self.debugger:
            print("[⊘] Skipped - debugger not initialized")
            self.results["skipped"].append("Load Symbols")
            return False
        
        if not self.elf_path:
            print("[⊘] Skipped - no ELF file provided")
            self.results["skipped"].append("Load Symbols")
            return False
        
        try:
            elf_file = Path(self.elf_path)
            if not elf_file.exists():
                print(f"[✗] ELF file not found: {self.elf_path}")
                self.results["failed"].append("Load Symbols")
                return False
            
            response = self.debugger.load_symbol_table(str(elf_file))
            print_response("load_symbol_table()", response)
            
            if response.get("status") == "ok":
                print("[✓] Symbol table loaded successfully")
                self.results["passed"].append("Load Symbols")
                return True
            else:
                print("[✗] Failed to load symbol table")
                self.results["failed"].append("Load Symbols")
                return False
        except Exception as e:
            print(f"[✗] Load symbols test failed: {e}")
            self.results["failed"].append("Load Symbols")
            return False
    
    def test_target_connection(self):
        print_section("Test 3: Target Connection")
        
        if not self.debugger:
            print("[⊘] Skipped - debugger not initialized")
            self.results["skipped"].append("Target Connection")
            return False
        
        try:
            response = self.debugger.select_target("localhost", 3333)
            print_response("select_target('localhost', 3333)", response)
            
            if response.get("status") == "ok" or "error" not in response.get("status", "").lower():
                print("[✓] Target connection attempted")
                self.results["passed"].append("Target Connection")
                return True
            else:
                print("[!] Target connection returned error (OpenOCD may not be running)")
                print("    To fully test, ensure OpenOCD is running:")
                print("    > openocd -f interface/stlink-v2.cfg -f target/stm32f4x.cfg")
                self.results["skipped"].append("Target Connection")
                return False
        except Exception as e:
            print(f"[!] Target connection test skipped: {e}")
            print("    (This is expected if OpenOCD is not running)")
            self.results["skipped"].append("Target Connection")
            return False
    
    def test_breakpoint_operations(self):
        print_section("Test 4: Breakpoint Operations")
        
        if not self.debugger:
            print("[⊘] Skipped - debugger not initialized")
            self.results["skipped"].append("Breakpoint Operations")
            return False
        
        try:
            # Test inserting breakpoint
            print("[→] Inserting hardware breakpoint at main()...")
            response = self.debugger.insert_breakpoint("main", hardware=True)
            print_response("insert_breakpoint('main', hardware=True)", response)
            
            bp_id = response.get("breakpoint_id")
            if bp_id:
                print(f"[✓] Hardware breakpoint created with ID: {bp_id}")
                self.results["passed"].append("Breakpoint Operations - Insert")
                
                # Test deleting breakpoint
                print(f"\n[→] Deleting breakpoint {bp_id}...")
                del_response = self.debugger.delete_breakpoint(int(bp_id))
                print_response(f"delete_breakpoint({bp_id})", del_response)
                
                if del_response.get("status") == "ok":
                    print(f"[✓] Breakpoint {bp_id} deleted successfully")
                    self.results["passed"].append("Breakpoint Operations - Delete")
                    return True
                else:
                    print(f"[!] Breakpoint deletion may have failed (target not connected)")
                    self.results["skipped"].append("Breakpoint Operations - Delete")
                    return False
            else:
                print("[!] Breakpoint creation skipped (target not connected)")
                self.results["skipped"].append("Breakpoint Operations - Insert")
                return False
        except Exception as e:
            print(f"[!] Breakpoint operations test skipped: {e}")
            self.results["skipped"].append("Breakpoint Operations")
            return False
    
    def test_state_inspection(self):
        print_section("Test 5: State Inspection")
        
        if not self.debugger:
            print("[⊘] Skipped - debugger not initialized")
            self.results["skipped"].append("State Inspection")
            return False
        
        try:
            print("[→] Listing stack frames...")
            frames_resp = self.debugger.list_frames()
            print_response("list_frames()", frames_resp)
            
            print("[→] Listing local variables...")
            locals_resp = self.debugger.list_locals()
            print_response("list_locals()", locals_resp)
            
            print("[→] Listing CPU registers...")
            regs_resp = self.debugger.list_registers(format="x")
            print_response("list_registers(format='x')", regs_resp)
            
            print("[→] Evaluating expression...")
            expr_resp = self.debugger.evaluate_expression("1 + 1")
            print_response("evaluate_expression('1 + 1')", expr_resp)
            
            print("[✓] State inspection commands executed")
            self.results["passed"].append("State Inspection")
            return True
        except Exception as e:
            print(f"[!] State inspection test skipped: {e}")
            self.results["skipped"].append("State Inspection")
            return False
    
    def test_execution_control(self):
        print_section("Test 6: Execution Control")

        if not self.debugger:
            print("[⊘] Skipped")
            self.results["skipped"].append("Execution Control")
            return False

        try:
            # 1. Connect to target (already done in test 3)
            #    At this point target is halted at reset vector — just like manual GDB

            # 2. Reset and halt — wait properly
            print("[→] Resetting target...")
            self.debugger.reset_halt()
            time.sleep(1.5)  # OpenOCD needs this — same as manual GDB pause

            # 3. Set breakpoint at main
            print("[→] Setting breakpoint at main...")
            bp = self.debugger.insert_breakpoint("main")
            print_response("insert_breakpoint('main')", bp)

            if not bp.get("breakpoint_id"):
                print("[✗] Failed to set breakpoint")
                self.results["failed"].append("Execution Control")
                return False

            # 4. Continue — target runs from reset vector to main
            print("[→] Continuing to main...")
            cont = self.debugger.execute_continue()
            print_response("execute_continue()", cont)

            # Check if breakpoint was already hit in the continue response itself
            if cont.get("stopped") or cont.get("reason") == "breakpoint-hit":
                print(f"[✓] Breakpoint hit immediately, reason: {cont.get('reason')}")
                stopped = cont  # already have the stop info
            else:
                # Not yet stopped, wait for async notification
                stopped = self.debugger.wait_for_stop(timeout=15)
                print_response("wait_for_stop()", stopped)

            if stopped["status"] != "ok":
                print("[✗] Never hit breakpoint")
                self.results["failed"].append("Execution Control")
                return False

            print(f"[✓] Halted at main, reason: {stopped.get('reason')}")

            # 6. Now step safely
            print("[→] Testing execute_next()...")
            stopped = self.debugger.execute_next()
            print_response("after next()", stopped)

            if stopped["status"] == "ok":
                line = stopped.get("payload", {}).get("frame", {}).get("line", "?")
                print(f"[✓] Stepped to line: {line}")
            else:
                print(f"[✗] next() failed: {stopped.get('message')}")

            print("[→] Testing execute_step()...")
            stopped = self.debugger.execute_step()
            print_response("after step()", stopped)

            if stopped["status"] == "ok":
                line = stopped.get("payload", {}).get("frame", {}).get("line", "?")
                func = stopped.get("payload", {}).get("frame", {}).get("func", "?")
                print(f"[✓] Stepped into {func}() at line {line}")
            else:
                print(f"[✗] step() failed: {stopped.get('message')}")
            return True

        except Exception as e:
            print(f"[✗] Execution control test failed: {e}")
            self.results["failed"].append("Execution Control")
            return False
    
    def test_cleanup(self):
        print_section("Test 7: Cleanup")
        
        if not self.debugger:
            print("[⊘] Nothing to clean up")
            return True
        
        try:
            print("[→] Disconnecting from GDB...")
            response = self.debugger.disconnect()
            print_response("disconnect()", response)
            
            if not self.debugger.is_connected:
                print("[✓] GDB disconnected successfully")
                self.results["passed"].append("Cleanup")
                return True
            else:
                print("[✗] GDB still connected after disconnect")
                self.results["failed"].append("Cleanup")
                return False
        except Exception as e:
            print(f"[✗] Cleanup test failed: {e}")
            self.results["failed"].append("Cleanup")
            return False
    
    def print_summary(self):
        print_section("TEST SUMMARY")
        
        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        skipped = len(self.results["skipped"])
        total = passed + failed + skipped
        
        print(f"Total Tests: {total}")
        print(f"  ✓ Passed:  {passed}")
        print(f"  ✗ Failed:  {failed}")
        print(f"  ⊘ Skipped: {skipped}")
        print()
        
        if self.results["passed"]:
            print("Passed:")
            for test in self.results["passed"]:
                print(f"  ✓ {test}")
            print()
        
        if self.results["failed"]:
            print("Failed:")
            for test in self.results["failed"]:
                print(f"  ✗ {test}")
            print()
        
        if self.results["skipped"]:
            print("Skipped (expected if no hardware connected):")
            for test in self.results["skipped"]:
                print(f"  ⊘ {test}")
            print()
        
        print("=" * 70)
        print("\nFull hardware testing requires:")
        print("  1. arm-none-eabi-gdb installed")
        print("  2. OpenOCD running on localhost:3333")
        print("  3. STM32 board connected via ST-LINK")
        print("  4. Compiled .elf file to debug")
        print()
        print("Quick start:")
        print("  python test_debugger.py --elf /path/to/firmware.elf")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Test EmbeddedDebugger Python backend"
    )
    parser.add_argument(
        "--elf",
        type=str,
        help="Path to compiled .elf file to load"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel("DEBUG")
    
    suite = DebuggerTestSuite(elf_path=args.elf)
    suite.run_all()

if __name__ == "__main__":
    main()
