from sharedrive.commands.auth import register_auth_commands
from sharedrive.commands.config import register_config_commands
from sharedrive.commands.descriptor import register_descriptor_commands

__all__ = [
    "register_auth_commands",
    "register_config_commands",
    "register_descriptor_commands",
]
