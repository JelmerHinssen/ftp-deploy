# src/get_num_square.py
from dataclasses import *
import os

def env(name: str, default=None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"No value provided for required {name}")
    return val

def env_int(name: str, default=None) -> int:
    val = env(name, default)
    try:
        return int(val)
    except:
        raise RuntimeError(f"Given {name} is not a valid integer")

@dataclass
class Arguments:
    server: str = env("INPUT_SERVER")
    username: str = env("INPUT_USERNAME")
    password: str = env("INPUT_PASSWORD")
    port: int = env_int("INPUT_PORT", 21)
    local_dir: str = env("INPUT_LOCAL_DIR", "./")
    server_dir: str = env("INPUT_SERVER_DIR", "./")

args = Arguments()
print(f"Action called with {repr(args)}")
