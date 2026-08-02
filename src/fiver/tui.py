"""Fiver Wi-Fi Setup TUI — scan networks, discover devices, mirror screen."""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from .adb import ADB, ADBError


# ── Data ─────────────────────────────────────────────────────


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    in_use: bool


@dataclass
class NetworkDevice:
    ip: str
    hostname: str
    mac: str


# ── Scanning helpers ─────────────────────────────────────────


def scan_wifi() -> List[WifiNetwork]:
    """Return visible Wi-Fi networks via nmcli."""
    try:
        proc = subprocess.run(
            [
                "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE",
                "dev", "wifi", "list", "--rescan", "yes",
            ],
            capture_output=True, text=True, timeout=20,
        )
        nets: List[WifiNetwork] = []
        seen: set = set()
        for raw in proc.stdout.strip().splitlines():
            cols = [c.replace("\\:", ":") for c in re.split(r"(?<!\\):", raw)]
            if len(cols) < 3:
                continue
            ssid = cols[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            nets.append(WifiNetwork(
                ssid=ssid,
                signal=int(cols[1]) if cols[1].isdigit() else 0,
                security=cols[2] or "Open",
                in_use=cols[3].strip().lower() == "yes" if len(cols) > 3 else False,
            ))
        nets.sort(key=lambda n: (-n.in_use, -n.signal))
        return nets
    except Exception:
        return []


def _local_subnet() -> tuple:
    """Return (local_ip, subnet_cidr) or (None, None)."""
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if m:
                ip = m.group(1)
                return ip, str(ipaddress.ip_network(
                    "{}/{}".format(ip, m.group(2)), strict=False
                ))
    except Exception:
        pass
    return None, None


def scan_devices() -> List[NetworkDevice]:
    """Discover hosts on the local network."""
    local_ip, subnet = _local_subnet()
    if not subnet:
        return []
    return (
        _nmap_scan(subnet, local_ip)
        or _arp_scan_tool(local_ip)
        or _ping_sweep(subnet, local_ip)
    )


def _nmap_scan(subnet, local_ip):
    """Try nmap host discovery."""
    try:
        out = subprocess.run(
            ["nmap", "-sn", "-T4", subnet],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    devs = []
    for block in re.split(r"Nmap scan report for ", out)[1:]:
        m = re.search(r"(?:(\S+) \()?(\d+\.\d+\.\d+\.\d+)", block)
        if not m:
            continue
        ip = m.group(2)
        if ip == local_ip:
            continue
        host = m.group(1) or ""
        mm = re.search(r"MAC Address: ([\dA-Fa-f:]+)\s*(.*)", block)
        mac = mm.group(1) if mm else ""
        vendor = mm.group(2).strip("() ") if mm else ""
        devs.append(NetworkDevice(
            ip=ip, hostname=host or vendor or _resolve(ip), mac=mac
        ))
    return devs or None


def _arp_scan_tool(local_ip):
    """Try arp-scan tool."""
    try:
        out = subprocess.run(
            ["arp-scan", "-l", "-q"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    devs = []
    for line in out.strip().splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            ip = cols[0].strip()
            mac = cols[1].strip() if len(cols) > 1 else ""
            vendor = cols[2].strip() if len(cols) > 2 else ""
            if ip != local_ip:
                devs.append(NetworkDevice(
                    ip=ip, hostname=vendor or _resolve(ip), mac=mac
                ))
    return devs or None


def _ping_sweep(subnet, local_ip):
    """Parallel ping sweep + read ARP neighbour table."""
    net = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(h) for h in list(net.hosts())[:254] if str(h) != local_ip]

    def _ping(ip):
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    with ThreadPoolExecutor(max_workers=60) as pool:
        list(pool.map(_ping, hosts))

    devs = []
    try:
        out = subprocess.run(
            ["ip", "neigh", "show"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            state = parts[-1]
            if state not in ("REACHABLE", "STALE", "DELAY"):
                continue
            ip = parts[0]
            if ":" in ip and "." not in ip:
                continue
            if ip == local_ip:
                continue
            mac = ""
            if "lladdr" in parts:
                idx = parts.index("lladdr")
                if idx + 1 < len(parts):
                    mac = parts[idx + 1]
            devs.append(NetworkDevice(ip=ip, hostname=_resolve(ip), mac=mac))
    except Exception:
        pass
    return devs


def _resolve(ip):
    """Reverse-DNS lookup for an IP."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unknown"


def _bars(sig):
    """Signal-strength bar characters."""
    if sig >= 75:
        return "[||||]"
    if sig >= 50:
        return "[||| ]"
    if sig >= 25:
        return "[||  ]"
    return "[|   ]"


# ── TUI list items ───────────────────────────────────────────


class WifiItem(ListItem):
    """One Wi-Fi network in the list."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def compose(self):
        n = self.net
        mark = "[ACTIVE]" if n.in_use else "[      ]"
        lock = "[SECURE]" if n.security not in ("", "--", "Open") else "[OPEN]  "
        yield Label(
            " {}  {:<24} {} {:>3}%  {} {}".format(
                mark, n.ssid, _bars(n.signal), n.signal, lock, n.security,
            )
        )

    def on_click(self) -> None:
        """Instant single-click selection for Wi-Fi network."""
        if hasattr(self, 'app') and isinstance(self.app, FiverSetupTUI):
            self.app._go_devices(self.net)


class DeviceItem(ListItem):
    """One network device in the list."""

    def __init__(self, dev):
        super().__init__()
        self.dev = dev

    def compose(self):
        d = self.dev
        yield Label(
            "   [DEVICE]  {:<18}{:<24}{}".format(d.ip, d.hostname, d.mac)
        )

    def on_click(self) -> None:
        """Instant single-click selection for network device."""
        if hasattr(self, 'app') and isinstance(self.app, FiverSetupTUI):
            self.app._send(self.dev)


# ── Main TUI application (Matte Black Theme) ─────────────────


class FiverSetupTUI(App):
    """Two-phase TUI: Wi-Fi list → device list → send request → mirror."""

    TITLE = "fiver"
    SUB_TITLE = "wireless setup"

    CSS = """
Screen {
    background: #000000;
}

#banner {
    dock: top;
    height: 3;
    padding: 1 2;
    background: #0a0a0a;
    color: #ffffff;
    border-bottom: solid #222222;
}

#hint {
    padding: 0 2;
    color: #888888;
    height: 2;
}

#phase {
    padding: 0 2;
    color: #ffffff;
    height: 2;
}

#wifi-lv, #dev-lv {
    margin: 0 2;
    border: solid #222222;
    padding: 0 1;
    height: 1fr;
    background: #050505;
}

.hidden {
    display: none;
}

#bar {
    dock: bottom;
    height: 3;
    padding: 0 2;
    layout: horizontal;
    background: #0a0a0a;
    border-top: solid #222222;
}

#bar Button {
    margin: 0 1;
    background: #111111;
    color: #ffffff;
    border: solid #333333;
}

#status {
    dock: bottom;
    height: auto;
    max-height: 25;
    padding: 0 2;
    background: #000000;
    color: #aaaaaa;
}

WifiItem {
    height: auto;
}

DeviceItem {
    height: auto;
}

WifiItem:hover, DeviceItem:hover {
    background: #151515;
}

ListView:focus > ListItem.--highlight {
    background: #222222;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.adb = ADB(cfg.adb_path)
        self._phase = "wifi"
        self._net = None  # type: Optional[WifiNetwork]
        self.web_server = None

    def compose(self):
        yield Header(show_clock=True)
        yield Static("", id="banner")
        yield Label("", id="hint")
        yield Label("", id="phase")
        yield ListView(id="wifi-lv")
        yield ListView(id="dev-lv", classes="hidden")
        with Horizontal(id="bar", classes="hidden"):
            yield Button("Back", id="b-back")
            yield Button("Refresh", id="b-ref")
            yield Button("Send Request", id="b-send")
        yield Static("", id="status")
        yield Footer()

    # ── lifecycle ─────────────────────────────────────────────

    def on_mount(self):
        self.adb.start_server()
        self._go_wifi()

    def on_unmount(self) -> None:
        """Clean shutdown on exit: stop servers and terminate Cloudflare tunnels."""
        if self.web_server:
            self.web_server.stop()
            self.web_server = None

    # ── phase: Wi-Fi list ─────────────────────────────────────

    def _go_wifi(self):
        self._phase = "wifi"
        self._update_status("Scanning Wi-Fi networks...")
        self.query_one("#banner", Static).update("FIVER - WI-FI SETUP")
        self.query_one("#hint", Label).update(
            "Click or press Enter on your Wi-Fi network to scan for devices."
        )
        self.query_one("#phase", Label).update("Scanning...")
        self.query_one("#wifi-lv").remove_class("hidden")
        self.query_one("#dev-lv").add_class("hidden")
        self.query_one("#bar").add_class("hidden")
        self.run_worker(self._load_wifi, thread=True)

    def _load_wifi(self):
        nets = scan_wifi()
        self.call_from_thread(self._fill_wifi, nets)

    def _fill_wifi(self, nets):
        lv = self.query_one("#wifi-lv", ListView)
        lv.clear()
        for n in nets:
            lv.append(WifiItem(n))
        self.query_one("#phase", Label).update(
            "Wi-Fi Networks ({})".format(len(nets))
        )
        self._update_status(
            "  {} networks found - click or press Enter to select".format(len(nets))
        )

    # ── phase: device list ────────────────────────────────────

    def _go_devices(self, net):
        self._phase = "devices"
        self._net = net
        self.query_one("#banner", Static).update(
            'Devices on "{}"'.format(net.ssid)
        )
        self.query_one("#hint", Label).update(
            "Click a device to send screen share request."
        )
        self.query_one("#phase", Label).update("Scanning network...")
        self.query_one("#wifi-lv").add_class("hidden")
        self.query_one("#dev-lv").remove_class("hidden")
        self.query_one("#bar").remove_class("hidden")
        self._update_status("  Scanning... this may take a moment")
        self.run_worker(self._load_devs, thread=True)

    def _load_devs(self):
        devs = scan_devices()
        self.call_from_thread(self._fill_devs, devs)

    def _fill_devs(self, devs):
        lv = self.query_one("#dev-lv", ListView)
        lv.clear()
        for d in devs:
            lv.append(DeviceItem(d))
        name = self._net.ssid if self._net else "network"
        self.query_one("#phase", Label).update(
            'Devices on "{}" ({})'.format(name, len(devs))
        )
        self._update_status(
            "  {} devices found - click one or press Send Request".format(len(devs))
        )

    # ── events ────────────────────────────────────────────────

    @on(ListView.Selected)
    def on_list_view_selected(self, ev: ListView.Selected):
        if self._phase == "wifi" and isinstance(ev.item, WifiItem):
            self._go_devices(ev.item.net)
        elif self._phase == "devices" and isinstance(ev.item, DeviceItem):
            self._send(ev.item.dev)

    def on_button_pressed(self, ev):
        bid = ev.button.id
        if bid == "b-back":
            self.action_back()
        elif bid == "b-ref":
            self.action_refresh()
        elif bid == "b-send":
            lv = self.query_one("#dev-lv", ListView)
            ch = lv.highlighted_child
            if isinstance(ch, DeviceItem):
                self._send(ch.dev)
            else:
                self._update_status("  [WARNING] Select a device first")

    def _send(self, dev):
        self._update_status("  [CONNECTING] Sending request to {}...".format(dev.ip))
        self.run_worker(lambda: self._try_connect(dev), thread=True)

    def _try_connect(self, dev):
        ports = sorted(set([5555, self.cfg.adb_port]))
        for port in ports:
            tgt = "{}:{}".format(dev.ip, port)
            self.call_from_thread(
                self._update_status,
                "  [ADB CHECK] Checking ADB on {}...".format(tgt),
            )
            try:
                if self.adb.connect(tgt, timeout=3.0):
                    self.call_from_thread(self.exit, tgt)
                    return
            except ADBError:
                continue

        # Non-developer phone fallback — build companion APK and serve it
        self.call_from_thread(
            self._update_status,
            "  [COMPANION MODE] ADB unavailable — building companion app...",
        )

        from .web_mirror import WebMirrorServer, generate_ascii_qr, MirrorHandler
        from .apk_builder import APKBuilder

        local_ip, _ = _local_subnet()
        local_ip = local_ip or "127.0.0.1"

        # Start web server first to get the port
        if self.web_server:
            self.web_server.stop()

        self.web_server = WebMirrorServer(port=8080)
        server_addr = self.web_server.start()

        # Build companion APK with server address embedded
        server_url = f"http://{local_ip}:{self.web_server.port}"
        try:
            self.call_from_thread(
                self._update_status,
                "  [BUILDING APK] Compiling companion app (first time may take a moment)...",
            )
            builder = APKBuilder()
            apk_path = builder.build_apk(server_url)
            self.web_server.set_apk(apk_path)
            self.call_from_thread(
                self._update_status,
                "  [APK READY] Companion app built successfully.",
            )
        except RuntimeError as e:
            self.call_from_thread(
                self._update_status,
                f"  [ERROR] Failed to build companion app: {e}",
            )
            return

        # Start Cloudflare tunnel for QR code access
        self.call_from_thread(
            self._update_status,
            "  [CLOUDFLARE TUNNEL] Deploying secure HTTPS tunnel...",
        )

        public_url = self.web_server.start_cloudflare_tunnel()
        phone_url = public_url or server_url

        qr_box = generate_ascii_qr(phone_url)

        # Open desktop viewer
        self.web_server.open_desktop_viewer(local_ip)

        self.call_from_thread(
            self._show_web_request,
            dev,
            phone_url,
            qr_box,
        )

        # Poll until phone starts streaming or user exits
        while not MirrorHandler.accepted and not MirrorHandler.declined:
            time.sleep(0.5)

        if MirrorHandler.accepted:
            self.call_from_thread(
                self._update_status,
                "  [SUCCESS] Companion app connected! Live screen stream active.",
            )
        else:
            self.call_from_thread(
                self._update_status,
                "  [DECLINED] Request declined by phone user.",
            )

    def _show_web_request(self, dev, url: str, qr_box: str):
        self.query_one("#banner", Static).update("COMPANION APP")
        self.query_one("#hint", Label).update(f"Scan QR code to download companion app for {dev.ip}!")
        self.query_one("#phase", Label).update("Waiting for phone user to install and open app...")
        self.query_one("#dev-lv").add_class("hidden")
        self.query_one("#status", Static).update(qr_box)

    # ── helpers ───────────────────────────────────────────────

    def _update_status(self, msg):
        self.query_one("#status", Static).update(msg)

    def action_back(self):
        if self._phase == "devices":
            self._go_wifi()

    def action_refresh(self):
        if self._phase == "wifi":
            self._go_wifi()
        elif self._net:
            self._go_devices(self._net)


def run_tui(cfg):
    """Launch the TUI; returns device address on success, None on quit."""
    app = FiverSetupTUI(cfg)
    return app.run()
