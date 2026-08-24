#!/usr/bin/env python3
"""Read the client-visible terminal state directly from the live CN CDN.

The writable ``production/upload`` used by the mod tools is an output overlay,
not an authoritative read source.  This module replays the same visible archive
graph as the server: official/full and diff archives below ``.cdn/cn``, active
patch archives below ``assets/asset-patch/active``, and anchored character
release archives.  Callers receive bytes from the last archive that wins at the
highest reachable tail without materialising the multi-gigabyte store.
"""
from __future__ import annotations

import os
import hashlib
import re
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


ROOT_ORDER = ("common", "medium", "android", "ios")
_ARCHIVE_DIRECTORIES = tuple(
    f"archive-{root}-{kind}"
    for root in ROOT_ORDER
    for kind in ("full", "diff")
)


class LiveCdnError(RuntimeError):
    """The live server CDN cannot be resolved or safely replayed."""


class LiveCdnUnavailable(LiveCdnError):
    """No live server layout is configured; standalone store fallback is allowed."""


class LiveCdnEntryMissing(FileNotFoundError):
    """The requested payload is not present in the live terminal view."""


@dataclass(frozen=True, slots=True)
class LiveCdnBytes:
    data: bytes
    tail: str
    root: str
    archive: Path
    member: str


@dataclass(slots=True)
class _CachedPlan:
    signature: tuple
    plan: object
    checked_at: float


_LOCK = threading.RLock()
_CACHE: dict[tuple[Path, Path], _CachedPlan] = {}


_HASHED_RELATIVE_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{38}$")
_IOS_PREFIX = "production/ios_upload/"


def clear_cache() -> None:
    """Forget every replay plan (tests and post-publish callers may force this)."""
    with _LOCK:
        _CACHE.clear()


def enabled_for_store(target_store: Path) -> bool:
    """Whether automatic live reads belong to this writable store context.

    The containment check keeps isolated tests and standalone stores from being
    contaminated by an unrelated profile's CDN.  ``WF_LIVE_CDN=1`` explicitly
    opts an external writable store into the configured server view; ``=0``
    disables live reads for diagnostics.
    """
    configured = os.environ.get("WF_LIVE_CDN")
    if configured is not None:
        normalized = configured.strip().casefold()
        if normalized in {"0", "false", "off", "no"}:
            return False
        if normalized in {"1", "true", "on", "yes"}:
            return True
        raise ValueError(f"WF_LIVE_CDN must be 0/1 or false/true: {configured!r}")
    try:
        _cdn_root, server_root = _resolve_locations()
        resolved_target = Path(target_store).resolve()

        # An explicit WF_TARGET_STORE commonly belongs to a unit test or an
        # intentionally isolated scratch store.  Do not couple it to a profile
        # CDN merely because profiles.json exists elsewhere.
        if "WF_TARGET_STORE" not in os.environ:
            import wf_mod_tool as core

            profile = core.resolve_profile(os.environ.get("WF_PROFILE"))
            if (
                profile is not None
                and Path(profile.store).resolve() == resolved_target
                and (profile.cdn_dir is not None or profile.server_dir is not None)
            ):
                # Split source/runtime deployments deliberately keep the
                # writable overlay in Git while reading the running mirror.
                return True

        resolved_target.relative_to(server_root)
        return True
    except (LiveCdnUnavailable, ValueError):
        return False


def _resolve_locations() -> tuple[Path, Path]:
    # Lazy imports avoid a module cycle: wf_store_materialize imports
    # wf_mod_tool, while both wf_mod_tool and wf_quest_lib call this module.
    import wf_mod_tool as core

    try:
        cdn_root = core.resolve_cdn_root().resolve()
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise LiveCdnUnavailable(f"无法定位服务端 CDN: {exc}") from exc

    # An explicit server root is always authoritative.  Otherwise a canonical
    # <server>/.cdn/cn path is stronger evidence than a source-checkout profile:
    # the latter may deliberately point writes at Git while the CDN belongs to
    # the running mirror.
    if "WF_SERVER_DIR" in os.environ:
        try:
            server_root = core.resolve_server_dir().resolve()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise LiveCdnUnavailable(f"无法定位服务端根目录: {exc}") from exc
    elif cdn_root.name.casefold() == "cn" and cdn_root.parent.name.casefold() == ".cdn":
        server_root = cdn_root.parent.parent.resolve()
    else:
        try:
            server_root = core.resolve_server_dir().resolve()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise LiveCdnUnavailable(f"无法定位服务端根目录: {exc}") from exc

    active = server_root / "assets" / "asset-patch" / "active"
    if not active.is_dir():
        raise LiveCdnUnavailable(f"服务端 active 补丁目录不存在: {active}")
    return cdn_root, server_root


def _stat_signature(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (str(path), int(stat.st_size), int(stat.st_mtime_ns))


def _input_signature(cdn_root: Path, server_root: Path) -> tuple:
    """Track every input whose change can alter the client-visible terminal state."""
    records: list[tuple] = []
    for dirname in _ARCHIVE_DIRECTORIES:
        directory = cdn_root / dirname
        if not directory.is_dir():
            records.append((str(directory), "missing"))
            continue
        records.append((str(directory), "dir", int(directory.stat().st_mtime_ns)))
        for path in sorted(directory.glob("*.zip"), key=lambda item: item.name):
            records.append(_stat_signature(path))

    active = server_root / "assets" / "asset-patch" / "active"
    records.append((str(active), "dir", int(active.stat().st_mtime_ns)))
    for path in sorted(active.glob("*.zip"), key=lambda item: item.name):
        records.append(_stat_signature(path))

    anchored = cdn_root / "character-releases" / "active.json"
    if anchored.is_file():
        records.append(_stat_signature(anchored))
    return tuple(records)


def _ios_member(name: str) -> str | None:
    normalized = str(name).replace("\\", "/")
    if not normalized.startswith(_IOS_PREFIX):
        return None
    relative = normalized[len(_IOS_PREFIX):]
    return relative if _HASHED_RELATIVE_RE.fullmatch(relative) else None


def _build_ios_plan(cdn_root: Path, server_root: Path):
    """Build the iOS terminal alongside the legacy three-root materializer.

    The upstream materializer intentionally models Android's three-root store.
    The running server also exposes ``archive-ios-*`` to iOS clients, so the
    live read layer adds that fourth root without changing materialization or
    release-package contracts.
    """
    import wf_chain_squash as chain
    import wf_store_materialize as materialize

    full_dir = cdn_root / "archive-ios-full"
    diff_dir = cdn_root / "archive-ios-diff"
    if not full_dir.is_dir() or not diff_dir.is_dir():
        return None

    entries: dict[tuple[str, str], object] = {}
    full_paths = [path for path in full_dir.glob("*.zip") if path.is_file()]
    try:
        full_paths.sort(key=materialize._full_archive_order)
    except Exception as exc:
        raise LiveCdnError(f"无法排序 iOS full 归档: {exc}") from exc
    for archive_path in full_paths:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    relative = _ios_member(info.filename)
                    if relative is None:
                        continue
                    entries[("ios", relative)] = SimpleNamespace(
                        name=info.filename,
                        root="ios",
                        relative=relative,
                        zip_path=archive_path,
                        crc=info.CRC,
                        size=info.file_size,
                    )
        except (OSError, zipfile.BadZipFile) as exc:
            raise LiveCdnError(f"无法读取 iOS full 归档 {archive_path}: {exc}") from exc

    graph = chain.VisibleGraph()
    for root in ("common", "medium", "ios"):
        dirname = f"archive-{root}-diff"
        chain._scan_zip_dir(
            graph,
            cdn_root / dirname,
            root,
            dirname,
            f"legacy:{root}",
            True,
        )
    chain._scan_zip_dir(
        graph,
        server_root / "assets" / "asset-patch" / "active",
        "patch",
        "asset-patch/active",
        "asset-patch:active",
        False,
    )
    chain._add_anchored_edges(graph, cdn_root)
    tail, path_edges = chain.find_path(graph, chain.FULL_BASE)
    health = materialize._chain_health(graph, tail)
    try:
        final, _conflicts = chain.replay(graph, path_edges)
    except (OSError, zipfile.BadZipFile) as exc:
        raise LiveCdnError(f"无法重放 iOS CDN/active 链: {exc}") from exc
    for name, source in final.items():
        relative = _ios_member(name)
        if relative is None:
            continue
        entries[("ios", relative)] = SimpleNamespace(
            name=name,
            root="ios",
            relative=relative,
            zip_path=source.zip_path,
            crc=source.crc,
            size=source.size,
        )
    return SimpleNamespace(tail=tail, entries=entries, health=health)


def _build_terminal_plan(cdn_root: Path, server_root: Path):
    import wf_store_materialize

    android = wf_store_materialize.build_read_only_plan(
        cdn_root, server_root, None, False
    )
    ios = _build_ios_plan(cdn_root, server_root)
    entries = dict(android.entries)
    tails = {"android": str(android.tail)}
    healths = [(android.health, str(android.tail))]
    if ios is not None:
        entries.update(ios.entries)
        tails["ios"] = str(ios.tail)
        healths.append((ios.health, str(ios.tail)))
    return SimpleNamespace(
        tail=str(android.tail),
        entries=entries,
        health=android.health,
        healths=tuple(healths),
        platform_tails=tails,
    )


def _current_plan():
    cdn_root, server_root = _resolve_locations()
    key = (cdn_root, server_root)
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and now - cached.checked_at < 0.25:
            return cached.plan
    signature = _input_signature(cdn_root, server_root)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached.signature == signature:
            cached.checked_at = now
            return cached.plan

        try:
            plan = _build_terminal_plan(cdn_root, server_root)
        except Exception as exc:
            if isinstance(exc, LiveCdnError):
                raise
            raise LiveCdnError(f"无法重放服务端 CDN/active 链: {exc}") from exc

        health_pairs = getattr(
            plan,
            "healths",
            ((getattr(plan, "health", None), str(plan.tail)),),
        )
        for health, health_tail in health_pairs:
            if health is not None and (
                health.gap(health_tail) or bool(getattr(health, "unreachable", ()))
            ):
                samples = "; ".join(getattr(health, "unreachable", ())[:3])
                raise LiveCdnError(
                    f"服务端资源链不完整，拒绝把旧终态当作当前数据: "
                    f"tail={health_tail}; {samples}"
                )
        _CACHE[key] = _CachedPlan(signature, plan, now)
        return plan


def read_relative(relative: str, roots: tuple[str, ...] = ROOT_ORDER) -> LiveCdnBytes:
    """Read one hashed relative payload from the current live terminal view."""
    clean = str(relative).replace("\\", "/").lstrip("/")
    if not clean or ".." in Path(clean).parts:
        raise ValueError(f"invalid live CDN relative path: {relative!r}")
    plan = _current_plan()
    entry = next(
        (plan.entries.get((root, clean)) for root in roots if plan.entries.get((root, clean))),
        None,
    )
    if entry is None:
        raise LiveCdnEntryMissing(
            f"{clean} 不在服务端当前 CDN/active 终态(tail {plan.tail})"
        )
    try:
        with zipfile.ZipFile(entry.zip_path) as archive:
            data = archive.read(entry.name)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise LiveCdnError(
            f"无法读取服务端终态成员 {entry.zip_path}!{entry.name}: {exc}"
        ) from exc
    return LiveCdnBytes(
        data=data,
        tail=str(plan.tail),
        root=str(entry.root),
        archive=Path(entry.zip_path),
        member=str(entry.name),
    )


def read_logical(logical_path: str) -> LiveCdnBytes:
    """Hash and read a logical production/upload path from the live server."""
    import wf_mod_tool as core

    logical = str(logical_path).replace("\\", "/").lstrip("/")
    digest = core.sha1_path(logical)
    return read_relative(f"{digest[:2]}/{digest[2:]}", roots=("common",))


def describe() -> dict[str, object]:
    """Return the resolved live view without exposing the materialized entry map."""
    cdn_root, server_root = _resolve_locations()
    plan = _current_plan()
    with _LOCK:
        cached = _CACHE.get((cdn_root, server_root))
        revision = hashlib.sha256(
            repr(cached.signature if cached is not None else ()).encode("utf-8")
        ).hexdigest()
    return {
        "cdn_root": str(cdn_root),
        "server_root": str(server_root),
        "active_dir": str(server_root / "assets" / "asset-patch" / "active"),
        "tail": str(plan.tail),
        "platform_tails": dict(getattr(plan, "platform_tails", {})),
        "files": len(plan.entries),
        "files_by_root": {
            root: sum(key[0] == root for key in plan.entries)
            for root in ROOT_ORDER
        },
        "revision": revision,
        "source": "live-cdn+active",
    }


def revision(target_store: Path | None = None) -> str:
    """Return a change token for GUI caches, or ``standalone`` when disabled."""
    if target_store is not None and not enabled_for_store(target_store):
        return "standalone"
    return str(describe()["revision"])
