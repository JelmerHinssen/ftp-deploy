from contextlib import contextmanager
import dataclasses as dc
import io
import os
import hashlib
import json
import logging
from entry import *
from ftp import FTP, open_ftp, split_path


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

Path = str


def create_file_list(dir: Path, exclude=[]) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    print(f"scanning {dir} in {os.getcwd()}")
    for entry in os.scandir(dir):
        path = os.path.normpath(entry.path)
        if path in exclude:
            continue
        if entry.is_file():
            result[entry.name] = filedata(entry)
        elif entry.is_dir():
            result[entry.name] = DirectoryEntry(
                entry.name, create_file_list(entry.path, exclude)
            )
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
                result[name] = DirectoryEntry(
                    name, create_remote_file_list(ftp, exclude)
                )
    return result


def retrieve_remote_file_list(ftp: FTP):
    try:
        return json.loads(
            ftp.retrieve_file(remote_data_file).decode(), cls=EntryJSONDecoder
        )
    except:
        return {}


def execute_remove(ftp: FTP, to_remove: DirectoryContent):
    for entry in to_remove.values():
        if isinstance(entry, DirectoryEntry):
            with ftp.cwd(entry.name):
                execute_remove(ftp, entry.content)
            if entry.changed == "remove":
                ftp.rmdir(entry.name)
        elif entry.changed == "remove":
            ftp.delete(entry.name)


def execute_add(ftp: FTP, to_add: DirectoryContent, path: Path, exclude=[]):
    for entry in to_add.values():
        entry_path = os.path.normpath(os.path.join(path, entry.name))
        if entry_path in exclude:
            continue
        if isinstance(entry, DirectoryEntry):
            if entry.changed == "add":
                ftp.mkdir(entry.name)
            with ftp.cwd(entry.name):
                execute_add(ftp, entry.content, entry_path, exclude)
        elif entry.changed == "add":
            with open(entry_path, "rb") as f:
                ftp.upload(entry.name, f)


logging.info(f"")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info(f"Args {repr(args)}")

local = create_file_list(os.path.normpath(args.local_dir), [local_data_file])
parts = split_path(args.data_file)
dataEntry = FileEntry(parts[-1])
current = local
for part in parts[:-1]:
    if part in current:
        sub = current[part]
        if isinstance(sub, DirectoryEntry):
            current = sub.content
        else:
            raise RuntimeError("Illegal location for datafile")
    else:
        sub = DirectoryEntry(part)
        current[part] = sub
        current = sub.content

current[dataEntry.name] = dataEntry


with open_ftp(args.server, args.username, args.password, timeout=10) as ftp:
    retrieved = retrieve_remote_file_list(ftp)
    with ftp.cwd(os.path.normpath(args.server_dir)):
        remote = create_remote_file_list(ftp, [])
        merged = merge_entries(remote, retrieved)
        to_remove, to_add = create_update_list(local, merged)

        execute_remove(ftp, to_remove)
        execute_add(ftp, to_add, local_dir, [local_data_file])
        updated_remote = create_remote_file_list(ftp, [])
        result = merge_modified(local, updated_remote)
        result_file = json.dumps(result, indent=" ", cls=DataclassJSONEncoder)
        ftp.upload(remote_data_file, io.BytesIO(result_file.encode()))
