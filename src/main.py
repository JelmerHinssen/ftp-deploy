from contextlib import contextmanager
import dataclasses as dc
import os
import hashlib
import json
from entry import *
from ftp import FTP, open_ftp

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


@dc.dataclass
class Arguments:
    server: str = env("INPUT_SERVER")
    username: str = env("INPUT_USERNAME")
    password: str = dc.field(default=env("INPUT_PASSWORD"), repr=False)
    port: int = env_int("INPUT_PORT", 21)
    local_dir: str = env("INPUT_LOCAL_DIR", "./")
    server_dir: str = env("INPUT_SERVER_DIR", "/")
    data_file: str = env("INPUT_DATA_FILE", "deploy-data/files.json")


args = Arguments()
print(f"Action called with {repr(args)}")

BUF_SIZE = 65536


def sha256(path):
    result = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(BUF_SIZE):
            result.update(data)
    return result.hexdigest()


def filedata(entry: os.DirEntry) -> FileEntry:
    stat = entry.stat()
    return FileEntry(entry.name, size=stat.st_size, sha256=sha256(entry.path))


local_dir = os.path.normpath(args.local_dir)
local_data_file = os.path.normpath(os.path.join(local_dir, args.data_file))
remote_data_file = os.path.normpath(os.path.join(args.server_dir, args.data_file))


def create_file_list(dir, exclude=[]) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    for entry in os.scandir(dir):
        path = os.path.normpath(entry.path)
        if path in exclude:
            continue
        if entry.is_file():
            result[entry.name] = (filedata(entry))
        elif entry.is_dir():
            result[entry.name] = DirectoryEntry(entry.name, create_file_list(entry.path, exclude))
    return result

def create_remote_file_list(ftp: FTP, exclude=[]) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    for name, info in ftp.ls():
        path = os.path.normpath(os.path.join(ftp.pwd(), name))
        if path in exclude:
            continue
        if info["type"] == "file":
            file = FileEntry(name, size=int(info["size"]))
            file.modified = info["modify"]
            result[name] = file
        elif info["type"] == "dir":
            with ftp.cwd(name):
                result[name] = DirectoryEntry(name, create_remote_file_list(ftp, exclude))
    return result

def retrieve_remote_file_list(ftp: FTP):
    try:
        return json.loads(ftp.retrieve_file(remote_data_file).decode(), cls=EntryJSONDecoder)
    except:
        return {}

with open_ftp(args.server, args.username, args.password, timeout=10) as ftp:
    retrieved = retrieve_remote_file_list(ftp)
    with ftp.cwd(os.path.normpath(args.server_dir)):
        remote = create_remote_file_list(ftp, [remote_data_file])

local = create_file_list(os.path.normpath(args.local_dir), [local_data_file])

obj = {"retrieved": retrieved, "remote": remote, "local": local}

with open("files.json", "w") as f:
    json.dump(obj, f, indent="  ", cls=DataclassJSONEncoder)
with open("objects.txt", "w") as f:
    f.writelines([repr(retrieved) + "\n", repr(remote) + "\n", repr(local) + "\n"])


# def file_diff(a, b):
#     added = {"files": {}, "directories": {}}
#     removed = {"files": {}, "directories": {}}
#     updated = {"files": {}, "directories": {}}
#     for name in a["files"]:
#         if name not in b["files"]:
#             added["files"][name] = a["files"][name]
#         elif True:
#             pass
#     for name in a["directories"]:
#         if name not in b["directories"]:
#             added["directories"][name] = a["directories"]["name"]
#         else:
#             pass
