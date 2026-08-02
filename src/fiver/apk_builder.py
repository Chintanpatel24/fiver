"""Build the Fiver companion APK from bundled Java sources.

Workflow:  javac → d8 → aapt2 link → zip-merge dex → zipalign → apksigner
All Android SDK components are auto-downloaded to ~/.fiver/sdk/ if missing.
Built APKs are cached at ~/.fiver/apk/ keyed by server-URL hash.
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("fiver")

# ── Paths ────────────────────────────────────────────────────

_FIVER_DIR = Path.home() / ".fiver"
_SDK_DIR = _FIVER_DIR / "sdk"
_APK_CACHE_DIR = _FIVER_DIR / "apk"
_BUILD_DIR = _FIVER_DIR / "build"
_KEYSTORE = _FIVER_DIR / "debug.keystore"

_COMPANION_DIR = Path(__file__).parent / "companion"

# Android SDK download constants
_CMDLINE_TOOLS_URL = (
    "https://dl.google.com/android/repository/"
    "commandlinetools-linux-11076708_latest.zip"
)
_BUILD_TOOLS_VERSION = "34.0.0"
_PLATFORM_VERSION = "34"


# ── Helpers ──────────────────────────────────────────────────


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a subprocess, raising RuntimeError with stderr on failure."""
    log.debug("exec: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n{detail}"
        )
    return result


def _which(name: str) -> Optional[str]:
    """Resolve a binary via PATH."""
    return shutil.which(name)


def _find_in_dirs(name: str, dirs: list[Path]) -> Optional[str]:
    """Search for a binary inside a list of directories (recursive)."""
    for d in dirs:
        if not d.is_dir():
            continue
        for root, _, files in os.walk(str(d)):
            if name in files:
                path = os.path.join(root, name)
                if os.access(path, os.X_OK):
                    return path
    return None


# ── APK Builder ──────────────────────────────────────────────


class APKBuilder:
    """Compile the companion Android app into a signed APK."""

    def __init__(self) -> None:
        self._tools: dict[str, Optional[str]] = {}
        self._refresh_tools()

    # ── tool discovery ────────────────────────────────────────

    def _sdk_search_dirs(self) -> list[Path]:
        """Standard places where Android SDK may live."""
        dirs = [_SDK_DIR]
        for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            val = os.environ.get(env)
            if val:
                dirs.append(Path(val))
        dirs += [
            Path("/opt/android-sdk"),
            Path.home() / "Android" / "Sdk",
        ]
        return dirs

    def _refresh_tools(self) -> None:
        dirs = self._sdk_search_dirs()
        for name in ("aapt2", "d8", "apksigner", "zipalign"):
            self._tools[name] = _find_in_dirs(name, dirs) or _which(name)
        self._tools["javac"] = _which("javac")
        self._tools["keytool"] = _which("keytool")
        # android.jar
        self._tools["android.jar"] = self._find_android_jar(dirs)

    def _find_android_jar(self, dirs: list[Path]) -> Optional[str]:
        """Locate android.jar from installed platforms."""
        for d in dirs:
            platforms = d / "platforms"
            if not platforms.is_dir():
                continue
            # pick highest API
            candidates = sorted(platforms.iterdir(), reverse=True)
            for c in candidates:
                jar = c / "android.jar"
                if jar.is_file():
                    return str(jar)
        return None

    def check_tools(self) -> dict[str, Optional[str]]:
        """Return mapping of tool name → resolved path (None if missing)."""
        self._refresh_tools()
        return dict(self._tools)

    def _missing_tools(self) -> list[str]:
        self._refresh_tools()
        return [k for k, v in self._tools.items() if v is None]

    # ── SDK auto-install ──────────────────────────────────────

    def install_sdk(self) -> bool:
        """Download Android command-line tools & install build-tools + platform.

        Requires ``javac`` (JDK) to already be installed.
        """
        if not self._tools.get("javac"):
            raise RuntimeError(
                "Java JDK is required but 'javac' was not found.\n"
                "Install it with:\n"
                "  Arch/CachyOS:  sudo pacman -S jdk-openjdk\n"
                "  Debian/Ubuntu: sudo apt install default-jdk\n"
                "  Fedora:        sudo dnf install java-latest-openjdk-devel\n"
                "  macOS:         brew install openjdk"
            )

        cmdline_dir = _SDK_DIR / "cmdline-tools" / "latest"
        sdkmanager = cmdline_dir / "bin" / "sdkmanager"

        if not sdkmanager.is_file():
            log.info("Downloading Android command-line tools...")
            print("[FIVER] Downloading Android SDK command-line tools...")
            _SDK_DIR.mkdir(parents=True, exist_ok=True)
            zip_path = _SDK_DIR / "cmdline-tools.zip"
            try:
                _run(["curl", "-fsSL", "-o", str(zip_path), _CMDLINE_TOOLS_URL])
            except RuntimeError:
                # Fallback to wget
                _run(["wget", "-q", "-O", str(zip_path), _CMDLINE_TOOLS_URL])

            # Extract — Google ships it as cmdline-tools/ inside the zip
            with zipfile.ZipFile(str(zip_path)) as zf:
                zf.extractall(str(_SDK_DIR / "cmdline-tools"))
            # Move contents to 'latest'
            extracted = _SDK_DIR / "cmdline-tools" / "cmdline-tools"
            if extracted.is_dir():
                if cmdline_dir.exists():
                    shutil.rmtree(cmdline_dir)
                extracted.rename(cmdline_dir)
            zip_path.unlink(missing_ok=True)

        if not sdkmanager.is_file():
            raise RuntimeError(
                "Failed to install Android SDK command-line tools.\n"
                f"Expected sdkmanager at: {sdkmanager}"
            )

        # Make executable
        sdkmanager.chmod(0o755)

        log.info("Installing Android SDK build-tools and platform...")
        print("[FIVER] Installing Android SDK build-tools and platform (this may take a moment)...")
        try:
            proc = subprocess.run(
                [
                    str(sdkmanager),
                    f"--sdk_root={_SDK_DIR}",
                    f"build-tools;{_BUILD_TOOLS_VERSION}",
                    f"platforms;android-{_PLATFORM_VERSION}",
                ],
                input="y\ny\ny\ny\ny\n",
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                log.warning("sdkmanager output: %s", proc.stderr or proc.stdout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("SDK installation timed out after 5 minutes.")

        self._refresh_tools()
        still_missing = self._missing_tools()
        if still_missing:
            log.warning("Still missing after SDK install: %s", still_missing)
            return False

        print("[FIVER] Android SDK installed successfully.")
        return True

    # ── APK cache ─────────────────────────────────────────────

    @staticmethod
    def _cache_key(server_url: str) -> str:
        return hashlib.sha256(server_url.encode()).hexdigest()[:16]

    def get_cached_apk(self, server_url: str) -> Optional[str]:
        """Return path to cached APK if it exists for this server_url."""
        key = self._cache_key(server_url)
        path = _APK_CACHE_DIR / f"companion-{key}.apk"
        return str(path) if path.is_file() else None

    # ── Build ─────────────────────────────────────────────────

    def build_apk(self, server_url: str) -> str:
        """Build the companion APK with *server_url* embedded.

        Returns the absolute path to the signed APK.
        Raises ``RuntimeError`` on failure.
        """
        # 1. Cache check
        cached = self.get_cached_apk(server_url)
        if cached:
            log.info("Using cached APK: %s", cached)
            return cached

        # 2. Tool check — auto-install if needed
        missing = self._missing_tools()
        if missing:
            log.info("Missing SDK tools: %s — attempting auto-install", missing)
            self.install_sdk()
            missing = self._missing_tools()
            if missing:
                raise RuntimeError(
                    f"Required tools not found: {', '.join(missing)}.\n"
                    "Please install the Android SDK build-tools and platform.\n"
                    "  Arch/CachyOS: yay -S android-sdk-build-tools android-platform\n"
                    "  Or run: fiver --doctor"
                )

        javac = self._tools["javac"]
        d8 = self._tools["d8"]
        aapt2 = self._tools["aapt2"]
        zipalign = self._tools["zipalign"]
        apksigner = self._tools["apksigner"]
        keytool = self._tools["keytool"]
        android_jar = self._tools["android.jar"]

        # 3. Set up build directory
        build_dir = Path(tempfile.mkdtemp(prefix="fiver-build-"))
        try:
            return self._do_build(
                build_dir, server_url,
                javac, d8, aapt2, zipalign, apksigner, keytool, android_jar,
            )
        except Exception:
            raise
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)

    def _do_build(
        self,
        build_dir: Path,
        server_url: str,
        javac: str,
        d8: str,
        aapt2: str,
        zipalign: str,
        apksigner: str,
        keytool: str,
        android_jar: str,
    ) -> str:
        src_dir = build_dir / "src" / "com" / "fiver" / "companion"
        classes_dir = build_dir / "classes"
        dex_dir = build_dir / "dex"
        src_dir.mkdir(parents=True)
        classes_dir.mkdir()
        dex_dir.mkdir()

        # ── 4. Copy & patch Java sources ──
        log.info("Patching companion sources with server URL: %s", server_url)
        for java_file in _COMPANION_DIR.glob("*.java"):
            content = java_file.read_text(encoding="utf-8")
            content = content.replace("__FIVER_SERVER_URL__", server_url)
            (src_dir / java_file.name).write_text(content, encoding="utf-8")

        # Copy manifest
        manifest = _COMPANION_DIR / "AndroidManifest.xml"
        shutil.copy2(manifest, build_dir / "AndroidManifest.xml")

        # ── 5. Compile Java → .class ──
        java_files = list(src_dir.glob("*.java"))
        log.info("Compiling %d Java files...", len(java_files))
        _run([
            javac,
            "-source", "1.8",
            "-target", "1.8",
            "-bootclasspath", android_jar,
            "-classpath", android_jar,
            "-d", str(classes_dir),
        ] + [str(f) for f in java_files])

        # ── 6. DEX ──
        class_files = list(classes_dir.rglob("*.class"))
        log.info("Converting %d class files to DEX...", len(class_files))
        _run([
            d8,
            "--output", str(dex_dir),
            "--min-api", "21",
        ] + [str(f) for f in class_files])

        # ── 7. Link APK with manifest ──
        base_apk = build_dir / "base.apk"
        log.info("Linking APK...")
        _run([
            aapt2, "link",
            "-o", str(base_apk),
            "--manifest", str(build_dir / "AndroidManifest.xml"),
            "-I", android_jar,
            "--min-sdk-version", "21",
            "--target-sdk-version", "34",
        ])

        # ── 8. Add classes.dex into APK ──
        dex_file = dex_dir / "classes.dex"
        if not dex_file.is_file():
            raise RuntimeError(f"DEX file not found at {dex_file}")

        merged_apk = build_dir / "merged.apk"
        shutil.copy2(base_apk, merged_apk)
        with zipfile.ZipFile(str(merged_apk), "a") as zf:
            zf.write(str(dex_file), "classes.dex")

        # ── 9. Align ──
        aligned_apk = build_dir / "aligned.apk"
        log.info("Aligning APK...")
        _run([zipalign, "-f", "4", str(merged_apk), str(aligned_apk)])

        # ── 10. Generate debug keystore ──
        self._ensure_keystore(keytool)

        # ── 11. Sign ──
        log.info("Signing APK...")
        _run([
            apksigner, "sign",
            "--ks", str(_KEYSTORE),
            "--ks-pass", "pass:fiverpass",
            "--key-pass", "pass:fiverpass",
            "--ks-key-alias", "fiver",
            str(aligned_apk),
        ])

        # ── 12. Cache ──
        _APK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = self._cache_key(server_url)
        final_apk = _APK_CACHE_DIR / f"companion-{key}.apk"
        shutil.copy2(aligned_apk, final_apk)
        log.info("APK built and cached: %s", final_apk)
        return str(final_apk)

    def _ensure_keystore(self, keytool: str) -> None:
        """Generate a debug keystore if one doesn't already exist."""
        if _KEYSTORE.is_file():
            return
        _FIVER_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Generating debug signing key...")
        _run([
            keytool,
            "-genkeypair", "-v",
            "-keystore", str(_KEYSTORE),
            "-alias", "fiver",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "fiverpass",
            "-keypass", "fiverpass",
            "-dname", "CN=Fiver,O=Fiver",
        ])
