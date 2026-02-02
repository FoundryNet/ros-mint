"""
MINT ROS 2 Integration
======================
Earn MINT tokens for robot task execution via FoundryNet.

Your robot works. Your robot earns.

Usage:
    from mint_ros import MintSettler
    
    settler = MintSettler(keypair_path="~/.config/solana/id.json")
    
    settler.start_task("pick_item_42")
    # ... robot does work ...
    settler.complete_task("pick_item_42")
    
    # Or use context manager:
    with settler.task("navigate_home"):
        robot.navigate(home_position)

Links:
    - GitHub: https://github.com/foundrynet
    - Dashboard: https://foundrynet.github.io/foundry_net_MINT/
    - Program: https://solscan.io/account/4ZvTZ3skfeMF3ZGyABoazPa9tiudw2QSwuVKn45t2AKL
"""

from .settler import MintSettler

__version__ = "1.0.0"
__all__ = ["MintSettler"]
