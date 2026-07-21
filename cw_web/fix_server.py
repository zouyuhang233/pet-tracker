import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# ==================== Rewrite server.js (no dependencies needed) ====================
print("[1] Writing server.js (built-in modules only)...", flush=True)

NEW_SERVER_JS = r'''const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');

const TCP_PORT = 18080;
const WEB_PORT = 3002;
const BASE_PATH = '/cw_dwq';

let latestData = {
  connected: false, lastUpdate: null,
  gps: { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
  step: { count: 0, lastUpdate: null },
  status: { battery: null, signal: null, rssi: null, raw: null },
  rawLog: [], connectionHistory: []
};

// ===== TCP Server =====
const tcpServer = net.createServer((socket) => {
  console.log('[TCP] New connection');
  latestData.connected = true;
  latestData.lastUpdate = new Date();
  latestData.connectionHistory.unshift({ time: new Date(), event: 'connected', address: socket.remoteAddress });
  let buffer = '';
  socket.on('data', (data) => {
    const text = data.toString('utf8');
    buffer += text;
    const lines = buffer.split(/\r\n|\r|\n/);
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.trim()) processIncomingData(line.trim());
    }
  });
  socket.on('end', () => {
    latestData.connected = false;
    latestData.lastUpdate = new Date();
    latestData.connectionHistory.unshift({ time: new Date(), event: 'disconnected' });
    console.log('[TCP] Disconnected');
  });
  socket.on('error', (err) => { console.log('[TCP] Error:', err.message); });
});

tcpServer.listen(TCP_PORT, () => console.log('[TCP] Listening on port ' + TCP_PORT));

function processIncomingData(line) {
  const ts = new Date();
  latestData.rawLog.unshift({ time: ts, data: line });
  if (latestData.rawLog.length > 100) latestData.rawLog = latestData.rawLog.slice(0, 100);
  latestData.lastUpdate = ts;

  if (line.startsWith('$GNGGA') || line.startsWith('$GPGGA') || line.startsWith('$BDGGA')) {
    const gga = parseNMEA_GGA(line);
    if (gga) {
      latestData.gps = { ...gga, raw: line, isValid: true };
      console.log('[GPS] ' + gga.latitude.toFixed(6) + ', ' + gga.longitude.toFixed(6));
    }
  } else if (line.startsWith('STEP:')) {
    const c = parseInt(line.split(':')[1]);
    if (!isNaN(c)) { latestData.step.count = c; latestData.step.lastUpdate = ts; console.log('[STEP] ' + c); }
  } else if (line.startsWith('STATUS:')) {
    const st = line.substring(7);
    latestData.status.raw = st;
    const bm = st.match(/Battery=(\d+)%/);
    const sm = st.match(/Signal=(\d+)/);
    const rm = st.match(/RSSI=(-?\d+)/);
    if (bm) latestData.status.battery = parseInt(bm[1]);
    if (sm) latestData.status.signal = parseInt(sm[1]);
    if (rm) latestData.status.rssi = parseInt(rm[1]);
  }
}

function parseNMEA_GGA(s) {
  if (!s.startsWith('$')) return null;
  const p = s.split(',');
  if (p.length < 15) return null;
  const fix = parseInt(p[6]);
  if (fix === 0) return { latitude: 0, longitude: 0, altitude: 0, satellites: 0, hdop: 0, isValid: false };
  const lat = parseDM(p[2], p[3] === 'N');
  const lng = parseDM(p[4], p[5] === 'E');
  return { latitude: lat, longitude: lng, altitude: parseFloat(p[9]) || 0, satellites: parseInt(p[7]) || 0, hdop: parseFloat(p[8]) || 0, isValid: true };
}

function parseDM(dm, pos) {
  if (!dm || dm.length < 4) return 0;
  const dot = dm.indexOf('.');
  let deg, min;
  if (dot > 0) {
    const intP = dm.substring(0, dot), decP = dm.substring(dot + 1);
    if (intP.length <= 2) { deg = parseInt(intP.substring(0, 2)); min = parseFloat(intP.substring(2) + '.' + decP); }
    else { deg = parseInt(intP.substring(0, 3)); min = parseFloat(intP.substring(3) + '.' + decP); }
  } else { deg = parseInt(dm.substring(0, dm.length - 2)); min = parseInt(dm.substring(dm.length - 2)); }
  let d = deg + min / 60;
  if (!pos) d = -d;
  return d;
}

// ===== Simple WebSocket Server =====
const wsClients = new Set();
const wsServer = net.createServer((socket) => {
  console.log('[WS] Client connected');
  let buf = '';
  socket.on('data', (data) => {
    buf += data.toString('utf8');
    if (buf.includes('\r\n\r\n')) {
      const headers = buf.split('\r\n');
      const keyLine = headers.find(h => h.startsWith('Sec-WebSocket-Key:'));
      if (keyLine) {
        const key = keyLine.split(':')[1].trim();
        const accept = Buffer.from(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').toString('base64');
        socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n');
        wsClients.add(socket);
        socket.write(encodeWS(JSON.stringify({ type: 'init', data: latestData })));
      }
    }
  });
  socket.on('end', () => { wsClients.delete(socket); console.log('[WS] Client disconnected'); });
  socket.on('error', () => { wsClients.delete(socket); });
});
wsServer.listen(8081, () => console.log('[WS] Listening on port 8081'));

function broadcast(msg) {
  const data = encodeWS(JSON.stringify(msg));
  for (const c of wsClients) { try { c.write(data); } catch(e) {} }
}

function encodeWS(str) {
  const buf = Buffer.alloc(4 + str.length);
  buf[0] = 0x81;
  if (str.length <= 125) {
    buf[1] = str.length;
    buf.write(str, 2);
  } else {
    buf[1] = 126;
    buf[2] = (str.length >> 8) & 0xff;
    buf[3] = str.length & 0xff;
    buf.write(str, 4);
  }
  return buf;
}

// ===== HTTP Server =====
const server = http.createServer((req, res) => {
  const url = req.url;
  console.log('[HTTP] ' + req.method + ' ' + url);

  if (url === BASE_PATH + '/api/data') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(latestData)); return;
  }
  if (url === BASE_PATH + '/api/log') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ log: latestData.rawLog })); return;
  }
  if (url === BASE_PATH + '/api/history') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ history: latestData.connectionHistory })); return;
  }
  if (url === BASE_PATH + '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ status: 'ok', tcpConnected: latestData.connected, lastUpdate: latestData.lastUpdate, uptime: process.uptime() })); return;
  }

  let filePath = url.replace(BASE_PATH, '');
  if (filePath === '' || filePath === '/') filePath = '/index.html';
  const fullPath = path.join(__dirname, 'public', filePath);
  const ext = path.extname(fullPath);
  const mimeTypes = { '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript', '.json': 'application/json', '.png': 'image/png', '.ico': 'image/x-icon' };
  const contentType = mimeTypes[ext] || 'application/octet-stream';

  fs.readFile(fullPath, (err, data) => {
    if (err) {
      if (!ext || ext === '/') {
        fs.readFile(path.join(__dirname, 'public', 'index.html'), (e2, d2) => {
          res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(d2);
        });
      } else {
        res.writeHead(404); res.end('Not Found');
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType }); res.end(data);
    }
  });
});

server.listen(WEB_PORT, () => console.log('[WEB] Listening on port ' + WEB_PORT + BASE_PATH));

setInterval(() => {
  const oneDay = Date.now() - 24 * 60 * 60 * 1000;
  latestData.connectionHistory = latestData.connectionHistory.filter(i => new Date(i.time).getTime() > oneDay);
}, 60000);
console.log('[系统] Server started');
'''

sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(NEW_SERVER_JS.encode('utf-8'))
sftp.close()
print("    [OK] server.js written", flush=True)

# ==================== Restart ====================
print("\n[2] Restarting...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

import time; time.sleep(4)

out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

out, _ = run(ssh, "pm2 logs location-server --lines 10 --nostream 2>&1")
print(f"[Logs]\n{out[:1000]}", flush=True)

# ==================== Test ====================
print("\n[3] Testing...", flush=True)

out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3002/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"    /cw_dwq/ -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -3")
print(f"    Body: {out.strip()[:100]}", flush=True)

out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/ 2>/dev/null || echo FAIL")
print(f"    TCP :18080 -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"    Nginx /cw_dwq -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/ 2>/dev/null || echo FAIL")
print(f"    Main site / -> HTTP {out.strip()}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
