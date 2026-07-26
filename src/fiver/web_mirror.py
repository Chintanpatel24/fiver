"""Web-based screen mirroring server for non-developer phones (No USB debugging / No dev mode needed)."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional


def ensure_ssl_certs() -> Optional[tuple[str, str]]:
    """Generate self-signed SSL certificate for local HTTPS streaming."""
    cert_dir = os.path.expanduser("~/.fiver/certs")
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "cert.pem")
    key_path = os.path.join(cert_dir, "key.pem")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        try:
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", key_path, "-out", cert_path,
                    "-days", "365", "-nodes", "-subj", "/CN=fiver.local"
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
            )
        except Exception:
            return None

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path
    return None


def generate_ascii_qr(url: str) -> str:
    """Generate a scannable ASCII QR code + link presentation for terminal display."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)

        f = io.StringIO()
        qr.print_ascii(out=f, invert=True)
        qr_str = f.getvalue()

        return f"""
NON-DEVELOPER PHONE SETUP (No USB Debugging Required)
Scan this QR code with your phone camera or open the link below:

{qr_str}
HTTPS Link: {url}
"""
    except Exception:
        width = max(len(url) + 6, 44)
        border = "=" * width
        padding = " " * ((width - len(url) - 4) // 2)

        return f"""
+{border}+
|{' ' * width}|
|  NON-DEVELOPER PHONE SETUP (No USB Debugging Required)    |
|{' ' * width}|
|  Open this link on your phone's browser:                 |
|{padding}   {url}  {padding}|
|{' ' * width}|
+{border}+
"""


# Manifest for PWA installation on phone
MANIFEST_JSON = json.dumps({
    "name": "Fiver Screen Mirror",
    "short_name": "Fiver",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#000000",
    "description": "Live screen sharing companion for Fiver Desktop"
})


# HTML template for the phone (Matte Black Theme, Instant Tap Permission)
PHONE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/manifest.json">
    <title>Fiver Screen Mirror</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            width: 100%;
            height: 100%;
        }
        body {
            font-family: monospace, sans-serif;
            background: #000000;
            color: #ffffff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            text-align: center;
            user-select: none;
            -webkit-user-select: none;
        }
        .card {
            background: #0a0a0a;
            border: 1px solid #222222;
            padding: 28px 24px;
            max-width: 400px;
            width: 100%;
        }
        h1 { font-size: 20px; margin-bottom: 12px; color: #ffffff; text-transform: uppercase; letter-spacing: 1px; }
        p { font-size: 14px; color: #888888; margin-bottom: 24px; line-height: 1.5; }
        .btn-group { display: flex; gap: 12px; flex-direction: column; }
        button {
            width: 100%;
            padding: 16px;
            border: 1px solid #333333;
            font-family: monospace;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
        }
        .btn-accept { background: #ffffff; color: #000000; }
        .btn-accept:hover { background: #cccccc; }
        .btn-decline { background: #1a1a1a; color: #ffffff; margin-top: 8px; }
        .btn-decline:hover { background: #333333; }
        .status {
            margin-top: 20px;
            font-size: 13px;
            color: #aaaaaa;
            line-height: 1.4;
        }
        #video, #canvas { display: none; }
    </style>
</head>
<body>
    <div class="card" id="card">
        <h1>Desktop Screen Request</h1>
        <p id="desc">TAP ANYWHERE TO SHARE SCREEN.<br><br>Your computer will view your phone screen in real time.</p>
        <div class="btn-group" id="btnGroup">
            <button class="btn-accept" id="startBtn">TAP TO ALLOW SCREEN SHARE</button>
            <button class="btn-decline" id="declineBtn">DECLINE</button>
        </div>
        <div class="status" id="statusMsg">[READY] Tap screen to start.</div>
    </div>

    <video id="video" autoplay playsinline></video>
    <canvas id="canvas"></canvas>

    <script>
        const startBtn = document.getElementById('startBtn');
        const declineBtn = document.getElementById('declineBtn');
        const statusMsg = document.getElementById('statusMsg');
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');

        let isStreaming = false;

        declineBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fetch('/api/decline', { method: 'POST' });
            document.getElementById('card').innerHTML = '<h1>Request Declined</h1><p>You declined the screen sharing request.</p>';
        });

        // Trigger permission on touch/click
        function handleTap(e) {
            if (isStreaming) return;
            requestScreenCapture();
        }

        document.body.addEventListener('click', handleTap);
        document.body.addEventListener('touchstart', handleTap);

        function requestScreenCapture() {
            if (isStreaming) return;
            statusMsg.textContent = 'Requesting screen permission...';
            
            if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
                navigator.mediaDevices.getDisplayMedia({
                    video: {
                        cursor: "always",
                        displaySurface: "monitor",
                        frameRate: { ideal: 30, max: 60 }
                    }
                }).then(stream => {
                    handleStream(stream);
                }).catch(err => {
                    console.error(err);
                    statusMsg.innerHTML = '[PERMISSION REQUIRED]<br>Tap screen again and select <b>"Start Now"</b> when prompted.';
                    startBtn.textContent = 'RETRY ALLOW SCREEN SHARE';
                });
            } else {
                statusMsg.innerHTML = '[HTTPS REQUIRED]<br>Screen sharing requires an HTTPS link.<br>Opening HTTPS Cloudflare link...';
            }
        }

        function handleStream(stream) {
            video.srcObject = stream;
            statusMsg.textContent = '[ACTIVE] Screen sharing live to desktop...';
            document.getElementById('btnGroup').style.display = 'none';

            video.onloadedmetadata = () => {
                canvas.width = video.videoWidth || 720;
                canvas.height = video.videoHeight || 1280;
                isStreaming = true;
                sendFrames();
            };

            stream.getVideoTracks()[0].onended = () => {
                isStreaming = false;
                statusMsg.textContent = '[STOPPED] Screen sharing ended.';
                document.getElementById('btnGroup').style.display = 'block';
                startBtn.textContent = 'RESTART SCREEN SHARE';
            };
        }

        async function sendFrames() {
            if (!isStreaming) return;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
            
            try {
                await fetch('/api/frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'text/plain' },
                    body: dataUrl
                });
            } catch (e) {}

            setTimeout(sendFrames, 40); // ~25 FPS
        }

        // Heartbeat status poll
        setInterval(async () => {
            if (isStreaming) return;
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                if (data.request && !isStreaming) {
                    statusMsg.textContent = '[REQUEST] Desktop server ready. Tap screen to share.';
                }
            } catch (e) {}
        }, 2000);
    </script>
</body>
</html>
"""

# HTML template for the Desktop viewer (Matte Black Theme, No Blur, No Emojis)
DESKTOP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fiver — Live Screen Stream</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #000000;
            color: #ffffff;
            font-family: monospace, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            overflow: hidden;
        }
        header {
            position: absolute;
            top: 10px;
            background: #0a0a0a;
            padding: 8px 20px;
            border: 1px solid #222222;
            font-size: 13px;
            color: #ffffff;
            letter-spacing: 1px;
        }
        #stream {
            max-width: 90vw;
            max-height: 90vh;
            border: 1px solid #333333;
            background: #050505;
        }
    </style>
</head>
<body>
    <header>[FIVER RECEIVER] Live Mobile Screen Stream</header>
    <img id="stream" src="/stream.mjpeg" alt="Waiting for phone stream...">
</body>
</html>
"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MirrorHandler(BaseHTTPRequestHandler):
    latest_frame: Optional[bytes] = None
    frame_event = threading.Event()
    accepted = False
    declined = False
    requested = True

    def log_message(self, format, *args):
        pass  # Suppress HTTP server stdout logs

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PHONE_HTML.encode("utf-8"))
        elif self.path == "/manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(MANIFEST_JSON.encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            res = json.dumps({"request": MirrorHandler.requested, "accepted": MirrorHandler.accepted})
            self.wfile.write(res.encode("utf-8"))
        elif self.path == "/desktop":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DESKTOP_HTML.encode("utf-8"))
        elif self.path == "/stream.mjpeg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    MirrorHandler.frame_event.wait(timeout=1.0)
                    MirrorHandler.frame_event.clear()
                    if MirrorHandler.latest_frame:
                        self.wfile.write(b"--frame\r\n")
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(MirrorHandler.latest_frame)))
                        self.end_headers()
                        self.wfile.write(MirrorHandler.latest_frame)
                        self.wfile.write(b"\r\n")
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/frame":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            if "," in body:
                body = body.split(",", 1)[1]
            try:
                MirrorHandler.latest_frame = base64.b64decode(body)
                MirrorHandler.accepted = True
                MirrorHandler.frame_event.set()
                self.send_response(200)
                self.end_headers()
            except Exception:
                self.send_error(400)
        elif self.path == "/api/decline":
            MirrorHandler.declined = True
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)


class WebMirrorServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.tunnel_proc: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.desktop_opened = False
        self.is_ssl = False

    def start(self) -> str:
        # Reset state flags
        MirrorHandler.accepted = False
        MirrorHandler.declined = False
        MirrorHandler.latest_frame = None
        MirrorHandler.requested = True

        # Dynamically find open port if 8080 is occupied
        for p in range(self.port, self.port + 20):
            try:
                self.server = ThreadedHTTPServer((self.host, p), MirrorHandler)
                self.port = p
                break
            except OSError:
                continue

        if not self.server:
            self.server = ThreadedHTTPServer((self.host, 0), MirrorHandler)
            self.port = self.server.server_port

        # Enable SSL if certificates are available
        certs = ensure_ssl_certs()
        if certs:
            try:
                cert_path, key_path = certs
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
                self.is_ssl = True
            except Exception:
                self.is_ssl = False

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        proto = "https" if self.is_ssl else "http"
        return f"{proto}://{self.host}:{self.port}"

    def start_cloudflare_tunnel(self) -> Optional[str]:
        """Start cloudflared tunnel to expose local server via Cloudflare HTTPS for mobile browser compatibility."""
        target_scheme = "https" if self.is_ssl else "http"
        cmd = ["npx", "-y", "cloudflared", "tunnel", "--no-tls-verify", "--url", f"{target_scheme}://localhost:{self.port}"]
        try:
            self.tunnel_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.time() + 25.0
            while time.time() < deadline:
                if not self.tunnel_proc.stderr:
                    break
                line = self.tunnel_proc.stderr.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    self.public_url = m.group(0)
                    return self.public_url
        except Exception:
            pass
        return None

    def stop(self):
        """Clean shutdown of HTTP server and Cloudflare Tunnel process."""
        if self.tunnel_proc:
            try:
                self.tunnel_proc.terminate()
                self.tunnel_proc.kill()
            except Exception:
                pass
            self.tunnel_proc = None
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None

    def open_desktop_viewer(self, local_ip: str):
        if self.desktop_opened:
            return
        self.desktop_opened = True
        url = f"{self.public_url}/desktop" if self.public_url else f"http://localhost:{self.port}/desktop"
        try:
            webbrowser.open(url)
        except Exception:
            pass
