from ftplib import FTP as FTPSocket
from contextlib import contextmanager
import os
import typing

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


class FTP:
    def __init__(self, socket: FTPSocket):
        self.socket = socket

    @contextmanager
    def cwd(self, dir: Path):
        parts = split_path(dir)
        with self._cwd_parts(parts):
            yield

    def retrieve_file(self, path: Path) -> bytes:
        result = b""
        def retrieve(data: bytes):
            nonlocal result
            result += data
        path, file = os.path.split(path)
        with self.cwd(path):
            self.socket.retrbinary(f"RETR {file}", retrieve)
        return result
    
    def ls(self) -> typing.Iterator[tuple[str, dict[str, str]]]:
        return self.socket.mlsd()
    
    def pwd(self) -> Path:
        return self.socket.pwd()

    @contextmanager
    def _cwd_single(self, dir: str):
        self.socket.cwd(dir)
        try:
            yield
        finally:
            self.socket.cwd("..")

    @contextmanager
    def _cwd_parts(self, parts: list[str]):
        if len(parts) == 0:
            yield
        else:
            with self._cwd_single(parts[0]):
                with typing.cast(typing.ContextManager, self._cwd_parts(parts[1:])):
                    yield


@contextmanager
def open_ftp(*args, **kwargs):
    with FTPSocket(*args, **kwargs) as ftp:
        yield FTP(ftp)
