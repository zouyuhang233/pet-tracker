import paramiko, sys, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=60):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    out = sout.read().decode('utf-8', errors='replace')
    err = serr.read().decode('utf-8', errors='replace')
    return out, err

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# ==================== Fix npm install ====================
print("[1] Fixing npm install...", flush=True)

# Check npm registry access
out, _ = run(ssh, "npm config get registry 2>/dev/null")
print(f"    Registry: {out.strip()}", flush=True)

# Try with explicit registry and retries
print("    Running npm install with registry...", flush=True)
channel = ssh.get_transport().open_session()
channel.get_pty()
channel.exec_command("cd /opt/location-server && npm install --production --registry=https://registry.npmmirror.com 2>&1 | tee /tmp/npm2.log")

# Wait and poll
for i in range(24):
    time.sleep(5)
    out, _ = run(ssh, "tail -3 /tmp/npm2.log 2>/dev/null; ps aux | grep 'npm install' | grep -v grep || echo DONE")
    print(f"    {(i+1)*5}s: {out.strip()[:120]}", flush=True)
    if 'DONE' in out or 'added' in out.lower():
        break

# Check result
out, _ = run(ssh, "ls /opt/location-server/node_modules/express/package.json 2>/dev/null && echo OK || echo FAIL")
print(f"    Express: {out.strip()}", flush=True)

out, _ = run(ssh, "ls /opt/location-server/node_modules/ws/package.json 2>/dev/null && echo OK || echo FAIL")
print(f"    WS: {out.strip()}", flush=True)

# If still failed, use alternative approach
out, _ = run(ssh, "test -f /opt/location-server/node_modules/express/package.json && echo READY || echo NOT_READY")
if 'NOT_READY' in out:
    print("\n[!] npm install failed, using built-in modules only...", flush=True)
    
    # Rewrite server.js to use only built-in Node.js modules (no express, no ws)
    sftp = ssh.open_sftp()
    with sftp.open('/opt/location-server/server.js', 'r') as f:
        js = f.read().decode('utf-8')
    sftp.close()
    
    # Replace the server.js with a version that doesn't need express/ws
    new_js = """const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');

const TCP_PORT = 8080;
const WEB_PORT = 3002;
const BASE_PATH = '/cw_dwq';

let latestData = {
  connected: false, lastUpdate: null,
  gps: { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
  step: { count: 0, lastUpdate: null },
  status: { battery: null, signal: null, rssi: null, raw: null },
  rawLog: [], connectionHistory: []
};

// TCP Server
const tcpServer = net.createServer((socket) => {
  console.log('[TCP] New connection');
  latestData.connected = true;
  latestData.lastUpdate = new Date();
  let buffer = '';
  socket.on('data', (data) => {
    const text = data.toString('utf8');
    buffer += text;
    const lines = buffer.split(/\\r\\n|\\r|\\n/);
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.trim()) processIncomingData(line.trim());
    }
  });
  socket.on('end', () => {
    latestData.connected = false;
    console.log('[TCP] Disconnected');
  });
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
    if (!isNaN(c)) { latestData.step.count = c; latestData.step.lastUpdate = ts; }
  } else if (line.startsWith('STATUS:')) {
    const st = line.substring(7);
    latestData.status.raw = st;
    const bm = st.match(/Battery=(\\d+)%/);
    const sm = st.match(/Signal=(\\d+)/);
    const rm = st.match(/RSSI=(-?\\d+)/);
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
  const alt = parseFloat(p[9]) || 0;
  const sat = parseInt(p[7]) || 0;
  const hdop = parseFloat(p[8]) || 0;
  return { latitude: lat, longitude: lng, altitude: alt, satellites: sat, hdop: hdop, isValid: true };
}

function parseDM(dm, pos) {
  if (!dm || dm.length < 4) return 0;
  const dot = dm.indexOf('.');
  let deg, min;
  if (dot > 0) {
    const intP = dm.substring(0, dot);
    const decP = dm.substring(dot + 1);
    if (intP.length <= 2) { deg = parseInt(intP.substring(0, 2)); min = parseFloat(intP.substring(2) + '.' + decP); }
    else { deg = parseInt(intP.substring(0, 3)); min = parseFloat(intP.substring(3) + '.' + decP); }
  } else { deg = parseInt(dm.substring(0, dm.length - 2)); min = parseInt(dm.substring(dm.length - 2)); }
  let d = deg + min / 60;
  if (!pos) d = -d;
  return d;
}

// WebSocket server (simple implementation)
const wssClients = new Set();
const wsServer = net.createServer((socket) => {
  console.log('[WS] Client connected');
  // Simple WS handshake
  let wsBuffer = '';
  socket.on('data', (data) => {
    wsBuffer += data.toString('utf8');
    if (wsBuffer.includes('\\r\\n\\r\\n')) {
      const headers = wsBuffer.split('\\r\\n');
      const key = headers.find(h => h.startsWith('Sec-WebSocket-Key:'));
      if (key) {
        const accept = Buffer.from(key.split(':')[1].trim() + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').toString('base64');
        const response = 'HTTP/1.1 101 Switching Protocols\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\nSec-WebSocket-Accept: ' + accept + '\\r\\n\\r\\n';
        socket.write(response);
        wssClients.add(socket);
        socket.write(encodeWS(JSON.stringify({ type: 'init', data: latestData })));
      }
    }
  });
  socket.on('end', () => { wssClients.delete(socket); console.log('[WS] Client disconnected'); });
});
wssClients.send = function(msg) {
  const data = encodeWS(JSON.stringify(msg));
  for (const c of wssClients) { try { c.write(data); } catch(e) {} }
};

function encodeWS(str) {
  const buf = Buffer.alloc(4 + str.length);
  buf[0] = 0x81; // fin + text
  buf[1] = str.length;
  buf.write(str, 2);
  return buf;
}

wsServer.listen(8081, () => console.log('[WS] Listening on port 8081'));

// HTTP Server
const server = http.createServer((req, res) => {
  const url = req.url;
  console.log('[HTTP] ' + req.method + ' ' + url);

  // API endpoints
  if (url === BASE_PATH + '/api/data') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(latestData));
    return;
  }
  if (url === BASE_PATH + '/api/log') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ log: latestData.rawLog }));
    return;
  }
  if (url === BASE_PATH + '/api/history') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ history: latestData.connectionHistory }));
    return;
  }
  if (url === BASE_PATH + '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ status: 'ok', tcpConnected: latestData.connected, lastUpdate: latestData.lastUpdate, uptime: process.uptime() }));
    return;
  }

  // Serve static files
  let filePath = url.replace(BASE_PATH, '');
  if (filePath === '' || filePath === '/') filePath = '/index.html';
  const fullPath = path.join(__dirname, 'public', filePath);
  
  const ext = path.extname(fullPath);
  const mimeTypes = { '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript', '.json': 'application/json', '.png': 'image/png', '.ico': 'image/x-icon' };
  const contentType = mimeTypes[ext] || 'application/octet-stream';
  
  fs.readFile(fullPath, (err, data) => {
    if (err) {
      if (ext === '') {
        // SPA fallback
        fs.readFile(path.join(__dirname, 'public', 'index.html'), (e2, d2) => {
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(d2);
        });
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(data);
    }
  });
});

server.listen(WEB_PORT, () => console.log('[WEB] Listening on port ' + WEB_PORT + BASE_PATH));

// Keep alive
setInterval(() => {
  // cleanup old history
  const oneDay = Date.now() - 24 * 60 * 60 * 1000;
  latestData.connectionHistory = latestData.connectionHistory.filter(i => new Date(i.time).getTime() > oneDay);
}, 60000);

console.log('[系统] Server started on port ' + WEB_PORT);
"""
    
    sftp = ssh.open_sftp()
    with sftp.open('/opt/location-server/server.js', 'w') as f:
        f.write(new_js.encode('utf-8'))
    sftp.close()
    print("    [OK] Rewrote server.js without external dependencies", flush=True)

# ==================== Restart service ====================
print("\n[2] Restarting service...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

time.sleep(4)
out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

# Check for errors
out, _ = run(ssh, "pm2 logs location-server --lines 10 --nostream 2>&1")
print(f"[Logs]\n{out[:1500]}", flush=True)

# Test
out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3002/cw_dwq 2>/dev/null || echo FAIL")
print(f"\n[Local test] HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq 2>/dev/null || echo FAIL")
print(f"[Nginx test] HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/ 2>/dev/null || echo FAIL")
print(f"[Main site] HTTP {out.strip()}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
