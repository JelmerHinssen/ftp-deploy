from contextlib import contextmanager
import dataclasses as dc
import os
import ftplib
import hashlib
import json
from entry import *
import typing


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

def split_path(path: str) -> list[str]:
    parts: list[str] = []
    while len(path) > 0:
        path, tail = os.path.split(path)
        if len(tail) == 0: break
        parts.append(tail)
        print(path, tail)
    parts.reverse()
    return parts

@contextmanager
def cwd_single(ftp: ftplib.FTP, dir: str):
    ftp.cwd(dir)
    print(f"cd {dir}")
    try:
        yield
    finally:
        ftp.cwd("..")
        print(f"cd ..")

@contextmanager
def cwd_parts(ftp: ftplib.FTP, parts: list[str]):
    if len(parts) == 0:
        yield
    else:
        with cwd_single(ftp, parts[0]):
            with typing.cast(typing.ContextManager, cwd_parts(ftp, parts[1:])):
                yield

@contextmanager
def cwd(ftp: ftplib.FTP, dir):
    parts = split_path(dir)
    with cwd_parts(ftp, parts):
        yield

def create_remote_file_list(ftp: ftplib.FTP, exclude=[]) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    for name, info in ftp.mlsd():
        path = os.path.normpath(os.path.join(ftp.pwd(), name))
        if path in exclude:
            continue
        if info["type"] == "file":
            file = FileEntry(name, size=int(info["size"]))
            file.modified = info["modify"]
            result[name] = file
        elif info["type"] == "dir":
            with cwd(ftp, name):
                result[name] = DirectoryEntry(name, create_remote_file_list(ftp, exclude))
    return result

def retrieve_file(ftp: ftplib.FTP, path: str) -> bytes:
    result = b""
    def retrieve(data: bytes):
        nonlocal result
        result += data
    path, file = os.path.split(path)
    with cwd(ftp, path):
        print(ftp.pwd())
        ftp.dir()
        print(f"RETR {file}")
        ftp.retrbinary(f"RETR {file}", retrieve)
    return result

def retrieve_remote_file_list(ftp: ftplib.FTP):
    try:
        return json.loads(retrieve_file(ftp, remote_data_file).decode(), cls=EntryJSONDecoder)
    except:
        return {}

with ftplib.FTP(args.server, args.username, args.password, timeout=10) as ftp:
    retrieved = retrieve_remote_file_list(ftp)
    with cwd(ftp, os.path.normpath(args.server_dir)):
        remote = create_remote_file_list(ftp, [remote_data_file])

local = create_file_list(os.path.normpath(args.local_dir), [local_data_file])

obj = {"retrieved": retrieved, "remote": remote, "local": local}

with open("files.json", "w") as f:
    json.dump(obj, f, indent="  ", cls=EnhancedJSONEncoder)


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
