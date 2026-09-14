"""FTP/FTPS remote filesystem adapter used by the file manager."""
import io
import os
import posixpath
import stat as _stat
import threading
import time
from ftplib import FTP, FTP_TLS


class _FTPStat:
    def __init__(self, name, is_dir=False, size=0, mode=None):
        self.filename = name
        self.st_size = int(size or 0)
        self.st_mode = mode if mode is not None else (_stat.S_IFDIR | 0o755 if is_dir else _stat.S_IFREG | 0o644)


class _FTPWriteFile:
    """Small file-like wrapper that uploads its in-memory contents on close."""
    def __init__(self, fs, path, mode):
        self._fs, self._path, self._mode = fs, path, mode
        self._closed = False
        self._buf = io.BytesIO()
        if "a" in mode:
            self._buf.write(fs._download_bytes(path))
        self._buf.seek(0, io.SEEK_END)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self._buf.write(data)

    def read(self, size=-1):
        data = self._buf.read(size)
        return data

    def seek(self, *args): return self._buf.seek(*args)
    def tell(self): return self._buf.tell()
    def flush(self): pass
    def __enter__(self): return self
    def __exit__(self, *exc): self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if any(x in self._mode for x in ("w", "a", "+")):
            self._buf.seek(0)
            self._fs.putfo(self._buf, self._path)
        self._buf.close()


class FTPFS:
    """Filesystem-shaped wrapper around ftplib.FTP / FTP_TLS.

    It intentionally exposes the subset of Paramiko SFTP used by Deckhand:
    normalize, listdir_attr, stat, open, mkdir, rmdir, remove, rename,
    put/putfo/get/getfo, plus close and a sudo_user-compatible no-op.
    """
    def __init__(self, host, port=21, user="", password="", tls=False,
                 passive=True, timeout=15, initial_path="/"):
        self.host = host
        self.port = int(port or (990 if tls else 21))
        self.user = user
        self.password = password or ""
        self.tls = bool(tls)
        self.passive = bool(passive)
        self.timeout = timeout
        self.sudo_user = None
        self._ftp = None
        self._stats_lock = threading.Lock()
        self.connected_at = None
        self.downloaded_bytes = 0
        self.uploaded_bytes = 0
        self.download_count = 0
        self.upload_count = 0
        self.last_operation = None
        self.last_operation_at = None
        self._connect()
        self._initial_path = self.normalize(initial_path or "/")

    def _connect(self):
        cls = FTP_TLS if self.tls else FTP
        ftp = cls()
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.user, self.password)
        if self.tls:
            ftp.prot_p()
        ftp.set_pasv(self.passive)
        self._ftp = ftp
        self.connected_at = time.time()

    def close(self):
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                try: self._ftp.close()
                except Exception: pass
            self._ftp = None

    def set_sudo_user(self, username):
        if username:
            raise NotImplementedError("sudo mode is only available for SSH/SFTP connections")
        self.sudo_user = None

    def normalize(self, path):
        if not path or path == "~":
            return self._initial_path if self._initial_path else "/"
        if not path.startswith("/"):
            try:
                cwd = self._ftp.pwd()
            except Exception:
                cwd = "/"
            path = posixpath.join(cwd, path)
        path = posixpath.normpath(path)
        return path if path.startswith("/") else "/" + path

    def _cwd_parent(self, path):
        path = self.normalize(path)
        return posixpath.dirname(path) or "/", posixpath.basename(path)

    def _facts(self, path):
        parent, name = self._cwd_parent(path)
        try:
            facts = self._ftp.mlsd(parent, facts=["type", "size", "unix.mode"])
            for n, f in facts:
                if n == name:
                    return f
        except Exception:
            pass
        return None

    def listdir_attr(self, path):
        path = self.normalize(path)
        entries = []
        try:
            for name, facts in self._ftp.mlsd(path, facts=["type", "size", "unix.mode"]):
                if name in (".", ".."):
                    continue
                typ = facts.get("type", "file")
                is_dir = typ in ("dir", "cdir", "pdir")
                try: size = int(facts.get("size") or 0)
                except Exception: size = 0
                try: mode = int(str(facts.get("unix.mode", "0")), 8)
                except Exception: mode = None
                entries.append(_FTPStat(name, is_dir, size, mode | (_stat.S_IFDIR if is_dir else _stat.S_IFREG) if mode else None))
            return entries
        except Exception:
            # Portable fallback for older FTP servers that don't implement MLSD.
            raw = []
            self._ftp.cwd(path)
            self._ftp.retrlines("LIST", raw.append)
            for line in raw:
                parts = line.split(None, 8)
                if len(parts) < 9: continue
                perms, size_s, name = parts[0], parts[4], parts[8]
                is_dir = perms.startswith("d")
                try: size = int(size_s)
                except Exception: size = 0
                entries.append(_FTPStat(name, is_dir, size))
            return entries

    def listdir(self, path):
        return [e.filename for e in self.listdir_attr(path)]

    def stat(self, path):
        path = self.normalize(path)
        facts = self._facts(path)
        if facts:
            typ = facts.get("type", "file")
            is_dir = typ in ("dir", "cdir", "pdir")
            try: size = int(facts.get("size") or 0)
            except Exception: size = 0
            try: mode = int(str(facts.get("unix.mode", "0")), 8)
            except Exception: mode = 0
            return _FTPStat(posixpath.basename(path), is_dir, size,
                            mode | (_stat.S_IFDIR if is_dir else _stat.S_IFREG) if mode else None)
        # Try cwd for directory, then SIZE for file.
        try:
            cur = self._ftp.pwd(); self._ftp.cwd(path); self._ftp.cwd(cur)
            return _FTPStat(posixpath.basename(path), True)
        except Exception:
            size = self._ftp.size(path) or 0
            return _FTPStat(posixpath.basename(path), False, size)

    def open(self, path, mode="r"):
        path = self.normalize(path)
        if any(x in mode for x in ("w", "a", "+")):
            return _FTPWriteFile(self, path, mode)
        return io.BytesIO(self._download_bytes(path))

    def _download_bytes(self, path):
        out = io.BytesIO()
        self._ftp.retrbinary("RETR " + self.normalize(path), out.write)
        return out.getvalue()

    def _record_transfer(self, direction, amount):
        with self._stats_lock:
            if direction == "download":
                self.downloaded_bytes += int(amount)
                self.download_count += 1
            else:
                self.uploaded_bytes += int(amount)
                self.upload_count += 1
            self.last_operation = direction
            self.last_operation_at = time.time()

    def getfo(self, remote, fileobj, callback=None):
        done = [0]
        def cb(data):
            fileobj.write(data); done[0] += len(data)
            if callback: callback(len(data), done[0])
        self._ftp.retrbinary("RETR " + self.normalize(remote), cb)
        if done[0]:
            self._record_transfer("download", done[0])

    def putfo(self, fileobj, remote, callback=None):
        total = None
        try:
            pos = fileobj.tell(); fileobj.seek(0, io.SEEK_END); total = fileobj.tell(); fileobj.seek(pos)
        except Exception: pass
        done = [0]
        class Reader:
            def read(_, n=-1):
                data = fileobj.read(n)
                if data:
                    done[0] += len(data)
                    if callback: callback(len(data), done[0])
                return data
        self._ftp.storbinary("STOR " + self.normalize(remote), Reader())
        if done[0]:
            self._record_transfer("upload", done[0])

    def get(self, remote, local, callback=None):
        with open(local, "wb") as f:
            self.getfo(remote, f, callback)

    def put(self, local, remote, callback=None):
        with open(local, "rb") as f:
            self.putfo(f, remote, callback)

    def mkdir(self, path): self._ftp.mkd(self.normalize(path))
    def rmdir(self, path): self._ftp.rmd(self.normalize(path))
    def remove(self, path): self._ftp.delete(self.normalize(path))
    def rename(self, old, new): self._ftp.rename(self.normalize(old), self.normalize(new))
