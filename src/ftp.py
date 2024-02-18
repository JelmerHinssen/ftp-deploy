from ftplib import FTP as FTPSocket
from contextlib import contextmanager
from functools import wraps
import os
import typing
import logging

Path = str


def split_path(path: str) -> list[str]:
    parts: list[str] = []
    while len(path) > 0:
        path, tail = os.path.split(path)
        if len(tail) == 0:
            break
        parts.append(tail)
    parts.reverse()
    return parts


def with_logger(cls, name="logger"):
    def fullname(cls):
        module = cls.__module__
        if module == "builtins":
            return cls.__qualname__
        return module + "." + cls.__qualname__

    logger = logging.getLogger(fullname(cls))
    logger.setLevel(logging.INFO)
    setattr(cls, name, logger)
    return cls


@with_logger
class FTP:
    logger: logging.Logger

    def __init__(self, socket: FTPSocket):
        self.socket = socket

    @contextmanager
    def cwd(self, dir: Path, make_dir: bool = False):
        parts = split_path(dir)
        with self._cwd_parts(parts, make_dir):
            yield

    @staticmethod
    def local_cmd(f):
        @wraps(f)
        def inner(self: "FTP", path: Path, *args, **kwargs):
            self.info(f"{f.__name__} '{path}'")
            path, file = os.path.split(path)
            with self.cwd(path):
                return f(self, file, *args, **kwargs)

        return inner

    def info(self, msg):
        self.logger.info(f"{self.pwd()}> {msg}")

    def dbg(self, msg):
        self.logger.debug(f"{self.pwd()}> {msg}")

    def warn(self, msg):
        self.logger.warn(f"{self.pwd()}> {msg}")

    @local_cmd
    def retrieve_file(self, file: str) -> bytes:
        result = b""

        def retrieve(data: bytes):
            nonlocal result
            result += data

        self.socket.retrbinary(f"RETR {file}", retrieve)
        return result

    @local_cmd
    def delete(self, file: str):
        self.socket.delete(file)

    @local_cmd
    def rmdir(self, file: str):
        try:
            self.socket.rmd(file)
            return True
        except:
            self.warn(f"Could not delete directory '{file}'")
            return False

    def upload(self, path: Path, data: typing.BinaryIO):
        self.info(f"upload '{path}'")
        path, file = os.path.split(path)
        with self.cwd(path, True):
            self.socket.storbinary(f"STOR {file}", data)

    @local_cmd
    def mkdir(self, file: str):
        try:
            self.socket.mkd(file)
            return True
        except:
            self.warn(f"Could not create directory '{file}'")
            return False

    def ls(self) -> typing.Iterator[tuple[str, dict[str, str]]]:
        return self.socket.mlsd()

    def pwd(self) -> Path:
        return self.socket.pwd()

    def exists(self, path: Path):
        try:
            return len(list(self.socket.mlsd(path))) > 0
        except:
            return False

    @contextmanager
    def _cwd_single(self, dir: str, make_dir: bool):
        if make_dir and not self.exists(dir):
            self.mkdir(dir)
        self.socket.cwd(dir)
        try:
            yield
        finally:
            self.socket.cwd("..")

    @contextmanager
    def _cwd_parts(self, parts: list[str], make_dir: bool):
        if len(parts) == 0:
            yield
        else:
            with self._cwd_single(parts[0], make_dir):
                with typing.cast(typing.ContextManager, self._cwd_parts(parts[1:], make_dir)):
                    yield


@contextmanager
def open_ftp(*args, **kwargs):
    with FTPSocket(*args, **kwargs) as ftp:
        yield FTP(ftp)
