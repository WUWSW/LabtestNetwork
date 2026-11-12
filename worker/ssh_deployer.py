"""
Paramiko SSH Deployment Engine (Task 7)
Connects to Cisco Routers via independent out-of-band management IP,
deploys configuration, collects output, and handles errors/timeouts safely.
Includes auto-detection for GNS3 local console fallback when SSH bridge is not yet active.
"""

import os
import time
import socket
import logging
from typing import Dict, Any, List, Optional
import paramiko

logger = logging.getLogger("ssh_deployer")

class CiscoSSHDeployer:
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        enable_password: Optional[str] = None,
        port: int = 22,
        timeout: int = 5
    ):
        self.username = username or os.getenv("ROUTER_SSH_USER", "cisco")
        self.password = password or os.getenv("ROUTER_SSH_PASSWORD", "cisco")
        self.enable_password = enable_password or os.getenv("ROUTER_ENABLE_PASSWORD", "cisco")
        self.port = int(os.getenv("ROUTER_SSH_PORT", str(port)))
        self.timeout = timeout

    def _get_gns3_console_port(self, host: str) -> Optional[int]:
        """Detect local GNS3 router console port based on management IP or hostname."""
        r1_mgmt = os.getenv("ROUTER_R1_MGMT_IP", "192.168.122.111")
        r2_mgmt = os.getenv("ROUTER_R2_MGMT_IP", "192.168.122.102")
        
        if host in [r1_mgmt, "R1", "1.1.1.1"]:
            return 5001
        elif host in [r2_mgmt, "R2", "2.2.2.2"]:
            return 5002
        return None

    def _is_ssh_reachable(self, host: str, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, self.port), timeout=timeout):
                return True
        except Exception:
            return False

    def deploy_config(self, host: str, config_text: str) -> Dict[str, Any]:
        """
        Deploy configuration commands to Cisco router via Paramiko SSH.
        Falls back to local GNS3 console socket if SSH port is not reachable.
        """
        start_time = time.time()
        output_buffer = []
        ssh_error = ""

        # 1. Attempt Paramiko SSH if port 22 is reachable
        if self._is_ssh_reachable(host, timeout=1.0):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                logger.info(f"Connecting to {host}:{self.port} as {self.username} via Paramiko SSH...")
                client.connect(
                    hostname=host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=self.timeout,
                    look_for_keys=False,
                    allow_agent=False
                )
                
                shell = client.invoke_shell(width=160, height=200)
                shell.settimeout(10)
                time.sleep(0.5)
                output_buffer.append(self._read_until_prompt(shell))
                
                # Enter enable mode
                shell.send("enable\n")
                time.sleep(0.3)
                shell.send(f"{self.enable_password}\n")
                time.sleep(0.3)
                output_buffer.append(self._read_until_prompt(shell))
                
                # Disable terminal paging
                shell.send("terminal length 0\n")
                time.sleep(0.2)
                output_buffer.append(self._read_until_prompt(shell))
                
                # Send configuration lines
                lines = [l.strip() for l in config_text.splitlines() if l.strip()]
                for line in lines:
                    shell.send(line + "\n")
                    time.sleep(0.15)
                    output_buffer.append(self._read_until_prompt(shell, timeout=3))
                    
                shell.send("\n")
                time.sleep(0.3)
                output_buffer.append(self._read_until_prompt(shell))
                
                shell.close()
                client.close()
                
                full_log = "".join(output_buffer)
                duration = round(time.time() - start_time, 2)
                logger.info(f"Configuration deployed successfully via Paramiko SSH to {host} in {duration}s")
                return {"success": True, "host": host, "duration_seconds": duration, "log": full_log, "error": None}
                
            except Exception as e:
                ssh_error = str(e)
                logger.warning(f"Paramiko SSH to {host}:{self.port} failed ({e}). Checking GNS3 Console fallback...")
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        else:
            ssh_error = f"SSH port {self.port} on {host} is unreachable"

        # 2. GNS3 Telnet Console Fallback (for local lab testing when SSH bridge is inactive)
        console_port = self._get_gns3_console_port(host)
        if console_port:
            try:
                s = socket.create_connection(("127.0.0.1", console_port), timeout=2)
                output_buffer.append(f"[NOTE: Paramiko SSH to {host}:{self.port} unreachable ({ssh_error}). Connected via GNS3 Router Console on port {console_port}]\n\n")
                s.sendall(b"\r\n\r\n")
                time.sleep(0.3)
                s.sendall(b"enable\r\nterminal length 0\r\n")
                time.sleep(0.3)
                
                lines = [l.strip() for l in config_text.splitlines() if l.strip()]
                for line in lines:
                    s.sendall(f"{line}\r\n".encode("utf-8"))
                    time.sleep(0.08)
                
                s.sendall(b"\r\nend\r\nwrite memory\r\n")
                time.sleep(0.8)
                
                chunk = s.recv(8192).decode("utf-8", errors="ignore")
                output_buffer.append(chunk)
                s.close()
                
                duration = round(time.time() - start_time, 2)
                return {
                    "success": True,
                    "host": host,
                    "duration_seconds": duration,
                    "log": "".join(output_buffer),
                    "error": None
                }
            except Exception as ce:
                logger.error(f"Console fallback to port {console_port} failed: {ce}")

        return {"success": False, "host": host, "log": "".join(output_buffer), "error": ssh_error}

    def run_command(self, host: str, command: str) -> Dict[str, Any]:
        """
        Run a single show or exec command on Cisco router and return output.
        """
        if self._is_ssh_reachable(host, timeout=1.0):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    hostname=host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=self.timeout,
                    look_for_keys=False,
                    allow_agent=False
                )
                shell = client.invoke_shell()
                shell.settimeout(5)
                time.sleep(0.3)
                self._read_until_prompt(shell)
                shell.send("enable\nterminal length 0\n")
                time.sleep(0.2)
                self._read_until_prompt(shell)
                shell.send(command + "\n")
                time.sleep(0.8)
                output = self._read_until_prompt(shell, timeout=5)
                shell.close()
                client.close()
                return {"success": True, "output": output}
            except Exception as e:
                logger.warning(f"SSH command execution on {host} failed: {e}")
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        # Fallback to local GNS3 console socket
        console_port = self._get_gns3_console_port(host)
        if console_port:
            try:
                s = socket.create_connection(("127.0.0.1", console_port), timeout=2)
                s.sendall(b"\r\n")
                time.sleep(0.2)
                s.sendall(f"enable\r\nterminal length 0\r\n{command}\r\n".encode("utf-8"))
                time.sleep(1.0)
                output = s.recv(8192).decode("utf-8", errors="ignore")
                s.close()
                return {"success": True, "output": output}
            except Exception as ce:
                return {"success": False, "output": "", "error": str(ce)}
        return {"success": False, "output": "", "error": f"Router {host} unreachable via SSH or Console"}

    def _read_until_prompt(self, shell, timeout: float = 3.0) -> str:
        buf = ""
        end_time = time.time() + timeout
        while time.time() < end_time:
            if shell.recv_ready():
                chunk = shell.recv(4096).decode("utf-8", errors="ignore")
                buf += chunk
                if buf.endswith("# ") or buf.endswith("> ") or buf.endswith("#") or buf.endswith(">"):
                    break
            else:
                time.sleep(0.1)
        return buf
