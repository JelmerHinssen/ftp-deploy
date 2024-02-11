from dataclasses import *
import os
from ftplib import *
import hashlib

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
    password: str = field(default=env("INPUT_PASSWORD"), repr=False)
    port: int = env_int("INPUT_PORT", 21)
    local_dir: str = env("INPUT_LOCAL_DIR", "./")
    server_dir: str = env("INPUT_SERVER_DIR", "./")

args = Arguments()
print(f"Action called with {repr(args)}")

BUF_SIZE = 65536

def sha256(path):
    result = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(BUF_SIZE):
            result.update(data)
    return result.hexdigest()

def filedata(entry: os.DirEntry):
    result = {}
    stat = entry.stat()
    result["size"] = stat.st_size
    result["sha256"] = sha256(entry.path)
    return result

def create_file_list(dir, root=False):
    result = {"files":{}, "directories":{}}
    for entry in os.scandir(dir):
        print(entry.name)
        if entry.is_file():
            result["files"][entry.name] = filedata(entry)
        elif entry.is_dir():
            if not root or entry.name != "deploy-data":
                result["directories"][entry.name] = create_file_list(entry.path)
    return result


print(create_file_list(args.local_dir, True))

# with FTP(args.server, args.username, args.password, timeout=10) as ftp:
#     print(ftp.retrlines("LIST"))
#     print(ftp.retrlines("SITE HELP"))
