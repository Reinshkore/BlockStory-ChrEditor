"""存档的发现、读取、备份与原子写入。

写入顺序与游戏自身一致：tmp → 自检 → 备份 → 替换。任何一步失败都不动原文件。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import bsjson
import schema
import validate as _validate
from model import SaveDoc

DEFAULT_DIR = Path(
    os.environ.get(
        "BS_SAVE_DIR",
        Path.home() / "AppData" / "LocalLow" / "Mindblocks" / "Block Story" / "characters",
    )
)

KEEP_BACKUPS = 10
LABEL_DIR = Path(__file__).resolve().parent / "labels"


class SaveError(RuntimeError):
    """读档失败。stage 标明失败阶段，供界面给出可操作的提示。"""

    def __init__(self, stage: str, message: str, *, path: Path | None = None,
                 line: int = 0, column: int = 0) -> None:
        super().__init__(message)
        self.stage = stage
        self.path = path
        self.line = line
        self.column = column


@dataclass
class SaveInfo:
    path: Path
    name: str
    character: str = ""
    level: int | None = None
    gender: str = ""
    size: int = 0
    mtime: float = 0.0
    keys: int = 0
    error: str = ""

    @property
    def mtime_text(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class WriteResult:
    path: Path
    backup: Path | None
    size: int
    identical_to_original: bool


# --------------------------------------------------------------------------- #
# 发现
# --------------------------------------------------------------------------- #

def save_dir() -> Path:
    return DEFAULT_DIR


def list_saves(directory: Path | None = None) -> list[SaveInfo]:
    directory = Path(directory or DEFAULT_DIR)
    if not directory.is_dir():
        return []
    out: list[SaveInfo] = []
    for path in directory.glob("*.chr"):
        if path.name.lower().endswith(".mp.chr"):
            continue  # 联机临时档，服务端权威
        stat = path.stat()
        info = SaveInfo(path=path, name=path.stem, size=stat.st_size, mtime=stat.st_mtime)
        try:
            text = path.read_text(encoding="utf-8")
            parsed = bsjson.loads(text)
            data = dict(parsed.entries)
            info.keys = len(parsed.entries)
            info.character = str(data.get("charName") or path.stem)
            level = data.get("Current Level")
            if not isinstance(level, int):
                # 仅某个模式有数据时，等级只存在于带后缀的键里。
                for mode in schema.WORLD_MODES:
                    suffix = schema.WORLD_MODE_SUFFIX.get(mode, "")
                    if not suffix:
                        continue
                    candidate = data.get(f"Current Level{suffix}")
                    if isinstance(candidate, int):
                        level = candidate
                        break
            info.level = level if isinstance(level, int) else None
            info.gender = str(data.get("charGender") or "")
        except (bsjson.SaveParseError, UnicodeDecodeError, OSError) as exc:
            info.error = str(exc)
        out.append(info)
    out.sort(key=lambda i: i.mtime, reverse=True)
    return out


def list_backups(path: Path) -> list[Path]:
    path = Path(path)
    pattern = f"{path.stem}.bak_*"
    items = list(path.parent.glob(pattern))
    items.sort(key=lambda p: p.name, reverse=True)
    return items


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #

def read_save(path: Path) -> SaveDoc:
    path = Path(path)
    if not path.is_file():
        raise SaveError("read", "file not found", path=path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SaveError("read", str(exc), path=path) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SaveError("decode", "not UTF-8 text", path=path) from None
    if not text.lstrip("\ufeff \t\r\n").startswith("{"):
        raise SaveError("parse", "does not start with '{' (possibly encrypted)", path=path)
    try:
        doc = SaveDoc.from_text(text, path=path)
    except bsjson.SaveParseError as exc:
        raise SaveError("parse", exc.message, path=path, line=exc.line, column=exc.column) from exc
    return doc


def verify_roundtrip(doc: SaveDoc) -> tuple[bool, str]:
    """序列化 → 重新解析 → 比对键与类型。返回 (是否通过, 说明)。"""
    try:
        text = doc.serialize()
        parsed = bsjson.loads(text)
    except (bsjson.SaveParseError, ValueError, TypeError) as exc:
        return False, str(exc)
    back = dict(parsed.entries)
    if len(parsed.entries) != len(doc.values):
        return False, f"key count changed: {len(doc.values)} -> {len(parsed.entries)}"
    for key, value in doc.values.items():
        if key not in back:
            return False, f"missing key after reparse: {key}"
        if bsjson.entry_kind(back[key]) != bsjson.entry_kind(value):
            return False, f"type drift on {key!r}"
    return True, "ok"


def write_save(doc: SaveDoc, path: Path | None = None, *, keep: int = KEEP_BACKUPS) -> WriteResult:
    """原子写入：自检 → 备份 → tmp → 替换。"""
    target = Path(path or doc.path or "")
    if not str(target):
        raise SaveError("write", "no target path")
    text = doc.serialize()

    # 第一道闸：阻断性校验（类型不符等会让游戏读档抛异常）
    issues = _validate.validate(doc)
    errors = [i for i in issues if i.level == _validate.ERROR]
    if errors:
        first = errors[0]
        raise SaveError("validate",
                        f"{len(errors)} blocking issue(s); first: {first.code} @ {first.key}",
                        path=target)

    # 第二道闸：序列化 → 重新解析 → 逐键比对
    ok, detail = verify_roundtrip(doc)
    if not ok:
        raise SaveError("verify", detail, path=target)

    identical = False
    if target.is_file():
        try:
            identical = target.read_text(encoding="utf-8") == text
        except OSError:
            identical = False

    backup: Path | None = None
    if target.is_file():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = target.with_name(f"{target.stem}.bak_{stamp}")
        n = 1
        while backup.exists():
            backup = target.with_name(f"{target.stem}.bak_{stamp}_{n}")
            n += 1
        try:
            shutil.copy2(target, backup)
        except OSError as exc:
            raise SaveError("backup", str(exc), path=target) from exc

    tmp = target.with_name(target.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # 落盘后从磁盘再读一次，确认没被编码或换行改写
        if tmp.read_text(encoding="utf-8") != text:
            raise SaveError("verify", "temp file content mismatch after write", path=target)
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise SaveError("write", str(exc), path=target) from exc
    except SaveError:
        tmp.unlink(missing_ok=True)
        raise

    if backup is not None:
        _prune_backups(target, keep)

    return WriteResult(path=target, backup=backup, size=len(text.encode("utf-8")),
                       identical_to_original=identical)


def _prune_backups(path: Path, keep: int) -> None:
    for old in list_backups(path)[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def restore_backup(backup: Path, target: Path | None = None) -> WriteResult:
    """把某个备份还原成主存档（同样先备份当前主文件）。"""
    backup = Path(backup)
    target = Path(target) if target else backup.with_name(
        backup.name.split(".bak_")[0] + ".chr")
    doc = read_save(backup)
    doc.path = target
    return write_save(doc, target)


# --------------------------------------------------------------------------- #
# 分类标注（按存档分开存，换档不互相污染）
# --------------------------------------------------------------------------- #

def _label_path(name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name) or "default"
    return LABEL_DIR / f"{safe}.json"


def load_labels(name: str) -> dict[str, str]:
    path = _label_path(name)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_labels(name: str, labels: dict[str, str]) -> None:
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    _label_path(name).write_text(
        json.dumps(labels, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
