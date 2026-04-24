#!/usr/bin/env python3
"""
Point Cloud WebSocket Bridge (stdlib only, no external deps)
Subscribes to /perception_node/stereo/pcl_output and streams raw
PointCloud2 binary to browser clients over WebSocket port 8767.
"""
import sys
import socket
import threading
import struct
import hashlib
import base64
import time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2

PORT = 8767
clients = []
clients_lock = threading.Lock()

# ─── WebSocket helpers ────────────────────────────────

WS_MAGIC = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

def ws_handshake(conn: socket.socket) -> bool:
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk
    headers = {}
    for line in data.decode(errors='ignore').split('\r\n')[1:]:
        if ':' in line:
            k, v = line.split(':', 1)
            headers[k.strip().lower()] = v.strip()
    key = headers.get('sec-websocket-key', '')
    accept = base64.b64encode(
        hashlib.sha1((key + WS_MAGIC).encode()).digest()
    ).decode()
    response = (
        'HTTP/1.1 101 Switching Protocols\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Accept: {accept}\r\n'
        '\r\n'
    )
    conn.sendall(response.encode())
    return True

def ws_send_binary(conn: socket.socket, data: bytes):
    """Send a binary WebSocket frame."""
    length = len(data)
    if length <= 125:
        header = struct.pack('BB', 0x82, length)
    elif length <= 65535:
        header = struct.pack('!BBH', 0x82, 126, length)
    else:
        header = struct.pack('!BBQ', 0x82, 127, length)
    conn.sendall(header + data)

def ws_recv_frame(conn: socket.socket):
    """Read one WebSocket frame (for ping/close handling)."""
    try:
        header = conn.recv(2)
        if len(header) < 2:
            return None, None
        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack('!H', conn.recv(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', conn.recv(8))[0]
        mask = conn.recv(4) if masked else b'\x00\x00\x00\x00'
        payload = bytearray(conn.recv(length))
        if masked:
            for i in range(len(payload)):
                payload[i] ^= mask[i % 4]
        return opcode, bytes(payload)
    except Exception:
        return None, None

# ─── Client handler ───────────────────────────────────

def handle_client(conn: socket.socket, addr):
    print(f'[pcl_bridge] client connected: {addr}')
    if not ws_handshake(conn):
        conn.close()
        return
    with clients_lock:
        clients.append(conn)
    try:
        while True:
            opcode, _ = ws_recv_frame(conn)
            if opcode is None or opcode == 8:  # close
                break
    except Exception:
        pass
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()
        print(f'[pcl_bridge] client disconnected: {addr}')

def broadcast(data: bytes):
    with clients_lock:
        dead = []
        for conn in clients:
            try:
                ws_send_binary(conn, data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            clients.remove(conn)
            conn.close()

# ─── TCP server ───────────────────────────────────────

def run_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', PORT))
    srv.listen(5)
    print(f'[pcl_bridge] listening on port {PORT}')
    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()

# ─── ROS2 node ────────────────────────────────────────

# Max publish rate and downsampling
MAX_FPS = 10
DOWNSAMPLE = 3  # keep 1 out of every N points

# Point cloud filtering parameters
MIN_DISTANCE = 0.3  # meters, filter out close-range noise
MAX_DISTANCE = 10.0  # meters, filter out far-range noise

class PclBridgeNode(Node):
    def __init__(self):
        super().__init__('pcl_ws_bridge')
        self._last_pub = 0.0
        self.sub = self.create_subscription(
            PointCloud2,
            '/perception_node/stereo/pcl_output',
            self.on_pcl,
            10,
        )
        self.get_logger().info('Subscribed to /perception_node/stereo/pcl_output')

    def on_pcl(self, msg: PointCloud2):
        if not clients:
            return
        now = time.time()
        if now - self._last_pub < 1.0 / MAX_FPS:
            return
        self._last_pub = now

        # Find x/y/z and label field offsets
        label_offset = 0xFFFFFFFF
        for f in msg.fields:
            if f.name == 'label':
                label_offset = f.offset
                break

        point_step = msg.point_step
        raw = bytes(msg.data)
        num_points = msg.height * msg.width

        # Downsample + filter: keep every DOWNSAMPLE-th point, skip label==1 (background)
        # Also filter by distance and depth validity
        out = bytearray()
        for i in range(0, num_points, DOWNSAMPLE):
            base = i * point_step
            if base + point_step > len(raw):
                break

            # Extract z coordinate (depth) - assuming x,y,z are at offsets 0,4,8
            z = struct.unpack_from('<f', raw, base + 8)[0]

            # Depth validity check: skip invalid or out-of-range points
            if z <= 0 or z < MIN_DISTANCE or z > MAX_DISTANCE:
                continue

            # Skip NaN or Inf values
            if not (z == z) or z == float('inf') or z == float('-inf'):
                continue

            # Label filtering (existing logic)
            if label_offset != 0xFFFFFFFF and label_offset + 4 <= point_step:
                label = struct.unpack_from('<I', raw, base + label_offset)[0]
                if label == 1:  # skip background
                    continue

            out += raw[base:base + point_step]

        n_out = len(out) // point_step
        # Serialize: height(4)=1, width(4)=n_out, point_step(4), label_offset(4) + data
        header = struct.pack('<IIII', 1, n_out, point_step, label_offset)
        broadcast(header + bytes(out))

def main():
    # Start TCP server in background thread
    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    rclpy.init(args=sys.argv)
    node = PclBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
