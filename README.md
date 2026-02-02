# mint_ros

**Your robot works. Your robot earns.**

Earn MINT tokens for ROS 2 task execution via [FoundryNet](https://github.com/foundrynet).

## Installation

```bash
cd ~/ros2_ws/src
git clone https://github.com/foundrynet/ros-mint mint_ros
cd ~/ros2_ws
colcon build --packages-select mint_ros
source install/setup.bash
```

## Usage

### Direct API

```python
from mint_ros import MintSettler

settler = MintSettler(keypair_path="~/.config/solana/id.json")

# Track individual tasks
settler.start_task("pick_object_42")
# ... robot does work ...
settler.complete_task("pick_object_42")

# Or use context manager
with settler.task("navigate_to_goal"):
    robot.navigate(goal_position)
    # Auto-settles on exit
```

### With ROS Actions

```python
from mint_ros import MintSettler

class MyActionServer:
    def __init__(self):
        self.settler = MintSettler(keypair_path="...")
    
    def execute_callback(self, goal_handle):
        task_id = str(goal_handle.goal_id)
        self.settler.start_task(task_id)
        
        try:
            result = self.do_work(goal_handle)
            self.settler.complete_task(task_id, success=True)
            return result
        except Exception:
            self.settler.complete_task(task_id, success=False)
            raise
```

## Earnings

| Task Duration | ~MINT Earned |
|---------------|--------------|
| 1 minute | 0.3 MINT |
| 10 minutes | 3 MINT |
| 1 hour | 18 MINT |

Base rate: 0.005 MINT/second

## Setup

1. Generate keypair: `solana-keygen new`
2. Register machine with `foundry-client`
3. Fund wallet with small SOL for tx fees (~0.01 SOL)

## License

MIT
