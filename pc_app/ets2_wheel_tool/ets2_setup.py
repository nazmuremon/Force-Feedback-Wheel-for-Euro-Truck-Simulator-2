from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys

from .config import app_root


ETS2_FOLDER_NAME = "Euro Truck Simulator 2"
PLUGIN_FILE_NAME = "ets2-telemetry-server.dll"


@dataclass
class PluginInstallStatus:
    ok: bool
    source_path: Path | None
    target_path: Path | None
    message: str


def _documents_roots() -> list[Path]:
    candidates: list[Path] = []
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    for candidate in (
        Path.home() / "OneDrive" / "Documents",
        userprofile / "OneDrive" / "Documents",
        userprofile / "Documents",
    ):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def ets2_documents_dir() -> Path | None:
    for documents_root in _documents_roots():
        candidate = documents_root / ETS2_FOLDER_NAME
        if candidate.exists():
            return candidate
    return None


def _steam_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        for candidate in (
            Path(base) / "Steam",
            Path(base) / "Valve" / "Steam",
        ):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _steam_library_dirs() -> list[Path]:
    libraries: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        normalized = Path(path)
        if normalized in seen:
            return
        seen.add(normalized)
        libraries.append(normalized)

    for steam_root in _steam_root_candidates():
        steamapps = steam_root / "steamapps"
        if steamapps.exists():
            add(steamapps)
        library_file = steamapps / "libraryfolders.vdf"
        if not library_file.exists():
            continue
        try:
            text = library_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            library_root = Path(match.group(1).replace("\\\\", "\\"))
            steamapps_dir = library_root / "steamapps"
            if steamapps_dir.exists():
                add(steamapps_dir)
    return libraries


def ets2_install_dir() -> Path | None:
    candidates: list[Path] = []

    def add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    for steamapps_dir in _steam_library_dirs():
        add(steamapps_dir / "common" / ETS2_FOLDER_NAME)

    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(env_name)
        if not base:
            continue
        add(Path(base) / ETS2_FOLDER_NAME)

    system_drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    add(system_drive / "Euro Truck Simulator 2")
    add(system_drive / "Euro Truck Simulator")

    for candidate in candidates:
        if (candidate / "eurotrucks2.exe").exists():
            return candidate
        if (candidate / "bin" / "win_x64").exists():
            return candidate
    return None


def ets2_plugin_target_path() -> Path | None:
    install_dir = ets2_install_dir()
    if install_dir is None:
        return None
    arch_dir = "win_x64" if sys.maxsize > 2**32 else "win_x86"
    return install_dir / "bin" / arch_dir / "plugins" / PLUGIN_FILE_NAME


def telemetry_plugin_source_path() -> Path | None:
    arch_dir = "win_x64" if sys.maxsize > 2**32 else "win_x86"
    candidates = (
        app_root() / "ets2_telemetry_server" / "Ets2Plugins" / arch_dir / "plugins" / PLUGIN_FILE_NAME,
        app_root() / "_internal" / "ets2_telemetry_server" / "Ets2Plugins" / arch_dir / "plugins" / PLUGIN_FILE_NAME,
        app_root() / ".research" / "ets2-telemetry-server" / "server" / "Ets2Plugins" / arch_dir / "plugins" / PLUGIN_FILE_NAME,
        Path(__file__).resolve().parents[2] / ".research" / "ets2-telemetry-server" / "server" / "Ets2Plugins" / arch_dir / "plugins" / PLUGIN_FILE_NAME,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_ets2_telemetry_plugin_installed() -> PluginInstallStatus:
    source_path = telemetry_plugin_source_path()
    if source_path is None:
        return PluginInstallStatus(
            ok=False,
            source_path=None,
            target_path=None,
            message="Bundled ETS2 telemetry plugin DLL was not found.",
        )

    target_path = ets2_plugin_target_path()
    if target_path is None:
        return PluginInstallStatus(
            ok=False,
            source_path=source_path,
            target_path=None,
            message="Could not locate the ETS2 game install folder for telemetry plugin install.",
        )

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and _file_sha256(source_path) == _file_sha256(target_path):
            return PluginInstallStatus(
                ok=True,
                source_path=source_path,
                target_path=target_path,
                message=f"ETS2 telemetry plugin is ready in the ETS2 game folder at {target_path}.",
            )
        shutil.copy2(source_path, target_path)
        return PluginInstallStatus(
            ok=True,
            source_path=source_path,
            target_path=target_path,
            message=f"Installed ETS2 telemetry plugin into the ETS2 game folder at {target_path}.",
        )
    except OSError as exc:
        return PluginInstallStatus(
            ok=False,
            source_path=source_path,
            target_path=target_path,
            message=f"Failed to install ETS2 telemetry plugin: {exc}",
        )
