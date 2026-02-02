"""
MINT ROS 2 Integration
======================
Earn MINT tokens for robot task execution.

Usage:
    from mint_ros import MintSettler
    
    settler = MintSettler(keypair_path="/path/to/id.json")
    
    # Track a task
    settler.start_task("pick_object_42")
    # ... robot does work ...
    settler.complete_task("pick_object_42")
    
    # Or use context manager
    with settler.task("navigate_to_goal"):
        # ... robot navigates ...
        pass  # Auto-settles on exit
"""

import time
import json
import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
from contextlib import contextmanager

from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.system_program import SYS_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta

# FoundryNet Mainnet
MINT_PROGRAM_ID = PublicKey("4ZvTZ3skfeMF3ZGyABoazPa9tiudw2QSwuVKn45t2AKL")
STATE_ACCOUNT = PublicKey("2Lm7hrtqK9W5tykVu4U37nUNJiiFh6WQ1rD8ZJWXomr2")
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"

# Anchor discriminator for record_job
RECORD_JOB_DISCRIMINATOR = bytes([0x36, 0x7c, 0xa8, 0x9e, 0xec, 0xed, 0x6b, 0xce])


@dataclass
class ActiveTask:
    """Tracks an in-progress task."""
    task_id: str
    start_time: float
    complexity: int = 1000


class MintSettler:
    """
    MINT Protocol settler for ROS 2.
    
    Tracks task execution and settles MINT rewards on completion.
    Thread-safe for use with ROS callbacks.
    """

    def __init__(
        self,
        keypair_path: Optional[str] = None,
        keypair_bytes: Optional[bytes] = None,
        rpc_endpoint: str = DEFAULT_RPC,
        default_complexity: int = 1000,
        min_duration: int = 1,
    ):
        """
        Initialize MINT settler.
        
        Args:
            keypair_path: Path to Solana keypair JSON file
            keypair_bytes: Raw keypair bytes (alternative to path)
            rpc_endpoint: Solana RPC endpoint
            default_complexity: Default complexity multiplier (1000 = 1.0x)
            min_duration: Minimum task duration in seconds to settle
        """
        self.client = Client(rpc_endpoint)
        self.default_complexity = default_complexity
        self.min_duration = min_duration
        
        self._active_tasks: Dict[str, ActiveTask] = {}
        self._lock = threading.Lock()
        
        # Load keypair
        if keypair_path:
            with open(keypair_path, "r") as f:
                data = json.load(f)
            self.keypair = Keypair.from_bytes(bytes(data))
        elif keypair_bytes:
            self.keypair = Keypair.from_bytes(keypair_bytes)
        else:
            raise ValueError("Must provide keypair_path or keypair_bytes")
        
        self._log(f"MINT Settler initialized: {self.keypair.pubkey()}")

    def _log(self, msg: str):
        """Log message. Override for ROS logging."""
        print(f"[MINT] {msg}")

    # ─────────────────────────────────────────────────────────────
    # Task Tracking
    # ─────────────────────────────────────────────────────────────

    def start_task(self, task_id: str, complexity: Optional[int] = None):
        """
        Start tracking a task.
        
        Args:
            task_id: Unique identifier for this task
            complexity: Complexity multiplier (default: 1000 = 1.0x)
        """
        with self._lock:
            if task_id in self._active_tasks:
                self._log(f"Warning: Task {task_id} already active, restarting")
            
            self._active_tasks[task_id] = ActiveTask(
                task_id=task_id,
                start_time=time.time(),
                complexity=complexity or self.default_complexity,
            )
            self._log(f"Task started: {task_id}")

    def complete_task(self, task_id: str, success: bool = True) -> Optional[float]:
        """
        Complete a task and settle MINT.
        
        Args:
            task_id: Task identifier
            success: Whether task completed successfully
            
        Returns:
            Estimated MINT earned, or None if settlement failed
        """
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
        
        if not task:
            self._log(f"Warning: Task {task_id} not found")
            return None
        
        duration = int(time.time() - task.start_time)
        
        if duration < self.min_duration:
            self._log(f"Task {task_id} too short ({duration}s), skipping")
            return None
        
        status = "completed" if success else "failed"
        self._log(f"Task {status}: {task_id} ({duration}s)")
        
        return self._settle(task_id, duration, task.complexity)

    def abort_task(self, task_id: str):
        """Abort a task without settling."""
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
        
        if task:
            self._log(f"Task aborted: {task_id}")

    @contextmanager
    def task(self, task_id: str, complexity: Optional[int] = None):
        """
        Context manager for task tracking.
        
        Usage:
            with settler.task("my_task"):
                # ... do work ...
                pass  # Auto-settles on exit
        """
        self.start_task(task_id, complexity)
        try:
            yield
            self.complete_task(task_id, success=True)
        except Exception:
            self.complete_task(task_id, success=False)
            raise

    # ─────────────────────────────────────────────────────────────
    # Settlement
    # ─────────────────────────────────────────────────────────────

    def _settle(self, task_id: str, duration: int, complexity: int) -> Optional[float]:
        """Record job on-chain and earn MINT."""
        try:
            job_hash = self._generate_job_hash(task_id, duration)
            tx = self._build_record_job_tx(job_hash, duration, complexity)
            
            signature = self.client.send_transaction(tx, self.keypair).value
            
            base_reward = duration * 0.005 * (complexity / 1000)
            
            self._log(f"✓ Settled ~{base_reward:.3f} MINT")
            self._log(f"  TX: https://solscan.io/tx/{signature}")
            
            return base_reward
            
        except Exception as e:
            self._log(f"Settlement failed: {e}")
            return None

    def _generate_job_hash(self, task_id: str, duration: int) -> str:
        data = f"{task_id}-{time.time()}-{duration}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _build_record_job_tx(self, job_hash: str, duration: int, complexity: int) -> Transaction:
        """Build record_job transaction."""
        machine_pda, _ = PublicKey.find_program_address(
            [b"machine", bytes(self.keypair.pubkey())],
            MINT_PROGRAM_ID
        )
        job_pda, _ = PublicKey.find_program_address(
            [b"job", job_hash.encode()],
            MINT_PROGRAM_ID
        )

        job_hash_bytes = job_hash.encode("utf-8")
        data = (
            RECORD_JOB_DISCRIMINATOR +
            len(job_hash_bytes).to_bytes(4, "little") +
            job_hash_bytes +
            duration.to_bytes(8, "little") +
            complexity.to_bytes(4, "little")
        )

        accounts = [
            AccountMeta(STATE_ACCOUNT, is_signer=False, is_writable=True),
            AccountMeta(machine_pda, is_signer=False, is_writable=True),
            AccountMeta(job_pda, is_signer=False, is_writable=True),
            AccountMeta(self.keypair.pubkey(), is_signer=True, is_writable=False),
            AccountMeta(self.keypair.pubkey(), is_signer=True, is_writable=True),
            AccountMeta(SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ]

        ix = Instruction(MINT_PROGRAM_ID, bytes(data), accounts)

        recent_blockhash = self.client.get_latest_blockhash().value.blockhash
        tx = Transaction.new_signed_with_payer(
            [ix],
            self.keypair.pubkey(),
            [self.keypair],
            recent_blockhash
        )

        return tx


# ─────────────────────────────────────────────────────────────────
# ROS 2 Node (optional - can also use MintSettler directly)
# ─────────────────────────────────────────────────────────────────

def main():
    """Run as standalone ROS 2 node."""
    try:
        import rclpy
        from rclpy.node import Node
    except ImportError:
        print("ROS 2 not available. Use MintSettler class directly.")
        return

    rclpy.init()
    
    class MintNode(Node):
        def __init__(self):
            super().__init__('mint_settler')
            self.declare_parameter('keypair_path', '')
            self.declare_parameter('complexity', 1000)
            
            keypair_path = self.get_parameter('keypair_path').value
            if not keypair_path:
                self.get_logger().error('keypair_path parameter required')
                return
            
            self.settler = MintSettler(keypair_path=keypair_path)
            self.get_logger().info('MINT Settler node ready')
    
    node = MintNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
