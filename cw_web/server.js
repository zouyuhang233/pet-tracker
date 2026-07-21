/**
 * 定位器网站 - 后端服务器（多设备版）
 * 功能：
 * 1. TCP 服务器（端口 8080）接收多个设备数据
 * 2. HTTP 服务器（端口 3002）提供网页服务
 * 3. WebSocket 实时推送数据到前端
 * 4. 多设备管理：按设备ID分别存储数据，支持前端切换
 */

const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');
const url = require('url');

// ==================== 配置 ====================
const TCP_PORT = 8080;
const WEB_PORT = 3002;
const BASE_PATH = '/cw_dwq';

// ==================== 多设备状态 ====================
// devices: Map<deviceId, deviceData>
// 每个设备独立存储：gps, step, status, connected, lastUpdate, socket等
const devices = new Map();

// socket → deviceId 映射
const socketDeviceMap = new WeakMap();

function createDeviceData(deviceId) {
  return {
    deviceId,
    deviceName: deviceId,
    deviceType: 'unknown',
    connected: false,
    lastUpdate: null,
    socket: null,
    clientAddr: '',
    gps: { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
    step: { count: 0, lastUpdate: null },
    status: { battery: null, signal: null, rssi: null, deviceName: null, raw: null },
    rawLog: [],
    connectionHistory: [],
    stats: { bytesReceived: 0, bytesSent: 0, msgCount: 0, disconnects: 0 }
  };
}

function getOrCreateDevice(deviceId) {
  if (!devices.has(deviceId)) {
    devices.set(deviceId, createDeviceData(deviceId));
    console.log(`[设备] 新设备注册: ${deviceId}`);
    broadcastDeviceList();
  }
  return devices.get(deviceId);
}

// ==================== TCP 客户端列表与消息缓冲 ====================
let connectedClients = [];  // { id, addr, deviceId, remoteAddress, remotePort, connectTime, bytesReceived, bytesSent, msgCount }
let messageBuffer = [];     // 最近收到的原始消息 { time, text, type, from }
const MAX_MESSAGE_BUFFER = 200;

// ==================== TCP 监控状态 ====================
let tcpMonitor = {
  connected: false,
  serverStatus: '运行中',
  port: TCP_PORT,
  clientAddr: '--',
  connStartTime: null,
  connDuration: '--',
  bytesReceived: 0,
  bytesSent: 0,
  msgCount: 0,
  disconnects: 0
};

// ==================== WebSocket 客户端管理 ====================
let wsClients = new Set();

// ==================== 工具函数 ====================
function broadcastToClients(message) {
  const json = JSON.stringify(message);
  for (const ws of wsClients) {
    if (ws.readyState === 1) {
      ws.send(json);
    }
  }
}

function broadcastDeviceList() {
  const list = [];
  for (const [id, dev] of devices) {
    list.push({
      deviceId: id,
      deviceName: dev.deviceName,
      connected: dev.connected,
      lastUpdate: dev.lastUpdate,
      clientAddr: dev.clientAddr,
      stats: dev.stats
    });
  }
  broadcastToClients({ type: 'device_list', data: list });
}

function updateTcpMonitor() {
  if (tcpMonitor.connected && tcpMonitor.connStartTime) {
    const elapsed = Date.now() - tcpMonitor.connStartTime;
    const sec = Math.floor(elapsed / 1000);
    const min = Math.floor(sec / 60);
    const hr = Math.floor(min / 60);
    tcpMonitor.connDuration = hr > 0
      ? `${hr}h ${min % 60}m ${sec % 60}s`
      : min > 0 ? `${min}m ${sec % 60}s` : `${sec}s`;
  }
  broadcastToClients({ type: 'tcp_monitor', data: { ...tcpMonitor } });
}

setInterval(updateTcpMonitor, 2000);

// 定时广播每个设备的统计数据
setInterval(() => {
  for (const [id, dev] of devices) {
    broadcastToClients({ type: 'device_stats', data: { deviceId: id, stats: dev.stats } });
  }
}, 2000);

// ==================== TCP 服务器 ====================
const tcpServer = net.createServer((socket) => {
  const rawAddr = socket.remoteAddress || '';
  const cleanAddr = rawAddr.replace(/^::ffff:/, '');
  const clientAddr = `${cleanAddr}:${socket.remotePort}`;
  console.log(`[TCP] 新连接: ${clientAddr}`);

  // 发送欢迎消息
  socket.write('WELCOME:Location Server Ready\r\n');
  tcpMonitor.bytesSent += 30;

  let buffer = '';
  let identified = false;  // 是否已识别设备ID
  let deviceId = null;
  let dev = null;

  // 超时检测：15秒没收到数据就认为设备离线
  let inactivityTimer = setTimeout(() => {
    console.log(`[TCP] 超时断开: ${clientAddr} (15秒无数据)`);
    socket.destroy();
  }, 15000);

  socket.on('data', (data) => {
    const text = data.toString('utf8');
    tcpMonitor.bytesReceived += data.length;
    tcpMonitor.msgCount++;

    // 重置超时
    clearTimeout(inactivityTimer);
    inactivityTimer = setTimeout(() => {
      console.log(`[TCP] 超时断开: ${clientAddr} (15秒无数据)`);
      socket.destroy();
    }, 15000);

    buffer += text;
    const lines = buffer.split(/\r\n|\r|\n/);
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.trim()) {
        processLine(line.trim());
      }
    }

    // 处理没有换行符的数据
    if (buffer.trim()) {
      if (buffer.trim().startsWith('{') && buffer.trim().endsWith('}')) {
        processLine(buffer.trim());
        buffer = '';
      }
    }
  });

  function processLine(line) {
    // 尝试从JSON中提取device_id来识别设备
    if (!identified && line.startsWith('{')) {
      const idMatch = line.match(/device_id:([^,\}]+)/);
      if (idMatch) {
        deviceId = idMatch[1].trim();
        identified = true;
        dev = getOrCreateDevice(deviceId);

        // 注册socket
        dev.socket = socket;
        dev.connected = true;
        dev.clientAddr = clientAddr;
        dev.lastUpdate = new Date();
        socketDeviceMap.set(socket, deviceId);

        // 更新TCP监控
        tcpMonitor.connected = true;
        tcpMonitor.clientAddr = clientAddr;
        tcpMonitor.connStartTime = Date.now();
        tcpMonitor.connDuration = '0s';
        tcpMonitor.msgCount = 0;
        tcpMonitor.bytesReceived = 0;
        tcpMonitor.bytesSent = 0;

        // 跟踪客户端
        const clientId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
        connectedClients.push({
          id: clientId,
          addr: clientAddr,
          deviceId: deviceId,
          remoteAddress: socket.remoteAddress,
          remotePort: socket.remotePort,
          connectTime: new Date(),
          bytesReceived: 0,
          bytesSent: 0,
          msgCount: 0,
          deviceName: deviceId
        });

        dev.connectionHistory.unshift({ time: new Date(), event: 'connected', address: clientAddr });
        broadcastDeviceList();
        broadcastToClients({ type: 'device_connect', data: { deviceId, connected: true } });
        console.log(`[TCP] 设备识别: ${deviceId} from ${clientAddr}`);
      }
    }

    // 更新客户端统计
    const client = connectedClients.find(c => c.addr === clientAddr);
    if (client) {
      client.bytesReceived += Buffer.byteLength(line);
      client.msgCount++;
    }

    // 更新设备统计
    if (dev) {
      dev.stats.bytesReceived += Buffer.byteLength(line);
      dev.stats.msgCount++;
    }

    // 如果还没识别，用客户端地址作为临时ID
    if (!identified) {
      deviceId = clientAddr;
      identified = true;
      dev = getOrCreateDevice(deviceId);
      dev.socket = socket;
      dev.connected = true;
      dev.clientAddr = clientAddr;
      dev.lastUpdate = new Date();
      socketDeviceMap.set(socket, deviceId);

      tcpMonitor.connected = true;
      tcpMonitor.clientAddr = clientAddr;
      tcpMonitor.connStartTime = Date.now();

      const clientId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      connectedClients.push({
        id: clientId, addr: clientAddr, deviceId, remoteAddress: socket.remoteAddress,
        remotePort: socket.remotePort, connectTime: new Date(), bytesReceived: 0, bytesSent: 0, msgCount: 0, deviceName: deviceId
      });

      broadcastDeviceList();
    }

    console.log(`[TCP][${deviceId}] 收到: ${line.substring(0, 100)}`);

    // 广播原始数据到前端消息流
    broadcastToClients({
      type: 'tcp_raw',
      data: { text: line, time: new Date(), type: 'data', deviceId: deviceId }
    });

    processIncomingData(line, dev);
  }

  socket.on('error', (err) => {
    console.error(`[TCP] 连接错误: ${err.message}`);
    broadcastToClients({ type: 'tcp_raw', data: { text: `[TCP] 错误: ${err.message}`, time: new Date(), type: 'error' } });
  });

  socket.on('end', () => handleDisconnect(socket, clientAddr));
  socket.on('close', () => handleDisconnect(socket, clientAddr));
});

function handleDisconnect(socket, clientAddr) {
  const deviceId = socketDeviceMap.get(socket) || clientAddr;
  const dev = devices.get(deviceId);

  console.log(`[TCP] 连接断开: ${clientAddr} (设备: ${deviceId})`);

  if (dev) {
    dev.connected = false;
    dev.socket = null;
    dev.lastUpdate = new Date();
    dev.connectionHistory.unshift({ time: new Date(), event: 'disconnected', address: clientAddr });
  }

  // 更新TCP监控
  tcpMonitor.connected = false;
  tcpMonitor.disconnects++;
  tcpMonitor.clientAddr = '--';
  tcpMonitor.connDuration = '--';

  // 移除客户端
  connectedClients = connectedClients.filter(c => c.addr !== clientAddr);

  broadcastToClients({ type: 'tcp_raw', data: { text: `[TCP] 客户端断开: ${clientAddr}`, time: new Date(), type: 'tcp-event' } });
  broadcastToClients({ type: 'device_connect', data: { deviceId, connected: false } });
  broadcastDeviceList();

  // 广播该设备当前状态（保留数据）
  if (dev) {
    broadcastToClients({ type: 'device_data', data: { deviceId, gps: dev.gps, step: dev.step, status: { ...dev.status, deviceName: dev.deviceName }, connected: false } });
  }
}

tcpServer.listen(TCP_PORT, () => {
  console.log(`[TCP] TCP 服务器启动，监听端口 ${TCP_PORT}`);
});

// ==================== 数据处理（按设备） ====================
function processIncomingData(line, dev) {
  const timestamp = new Date();
  const deviceId = dev.deviceId;

  dev.rawLog.unshift({ time: timestamp, data: line });
  if (dev.rawLog.length > 100) dev.rawLog = dev.rawLog.slice(0, 100);
  dev.lastUpdate = timestamp;

  // 消息缓冲
  let msgType = 'raw';
  if (line.startsWith('$GNGGA') || line.startsWith('$GPGGA')) msgType = 'gps';
  else if (line.startsWith('STEP:')) msgType = 'step';
  else if (line.startsWith('STATUS:')) msgType = 'status';
  else if (line.startsWith('{')) msgType = 'json';
  messageBuffer.push({ time: timestamp, text: line, type: msgType, clientId: dev.clientAddr, deviceId, from: dev.clientAddr });
  if (messageBuffer.length > MAX_MESSAGE_BUFFER) messageBuffer = messageBuffer.slice(-MAX_MESSAGE_BUFFER);

  // GPS NMEA
  if (line.startsWith('$GNGGA') || line.startsWith('$GPGGA') || line.startsWith('$BDGGA')) {
    const gga = parseNMEA_GGA(line);
    if (gga) {
      dev.gps = { ...gga, raw: line, isValid: true };
      console.log(`[GPS][${deviceId}] ${gga.latitude.toFixed(6)}, ${gga.longitude.toFixed(6)}`);
      broadcastToClients({ type: 'device_data', data: { deviceId, gps: dev.gps } });
    }
  }
  // 步数
  else if (line.startsWith('STEP:')) {
    const count = parseInt(line.split(':')[1]);
    if (!isNaN(count)) {
      dev.step.count = count;
      dev.step.lastUpdate = timestamp;
      broadcastToClients({ type: 'device_data', data: { deviceId, step: dev.step } });
    }
  }
  // 状态
  else if (line.startsWith('STATUS:')) {
    const statusText = line.substring(7);
    dev.status.raw = statusText;
    const batteryMatch = statusText.match(/Battery=(\d+)%/);
    const signalMatch = statusText.match(/Signal=(\d+)/);
    const rssiMatch = statusText.match(/RSSI=(-?\d+)/);
    const nameMatch = statusText.match(/Name=([^,]+)/);
    if (batteryMatch) dev.status.battery = parseInt(batteryMatch[1]);
    if (signalMatch) dev.status.signal = parseInt(signalMatch[1]);
    if (rssiMatch) dev.status.rssi = parseInt(rssiMatch[1]);
    if (nameMatch) {
      dev.deviceName = nameMatch[1].trim();
      const client = connectedClients.find(c => c.addr === dev.clientAddr);
      if (client) client.deviceName = dev.deviceName;
      broadcastDeviceList();
    }
    broadcastToClients({ type: 'device_data', data: { deviceId, gps: dev.gps, step: dev.step, status: { ...dev.status, deviceName: dev.deviceName } } });
  }
  // JSON格式
  else if (line.startsWith('{') && line.endsWith('}')) {
    try {
      const typeMatch = line.match(/type:(\w+)/);
      const latMatch = line.match(/lat:([\-.\d]+)/);
      const lonMatch = line.match(/lon:([\-.\d]+)/);
      const altMatch = line.match(/alt:([\-.\d]+)/);
      const fixMatch = line.match(/fix:(\d+)/);
      const satMatch = line.match(/sat:(\d+)/);
      const stepsMatch = line.match(/steps:(\d+)/);
      const signalMatch = line.match(/signal:(\-?\d+)/);
      const rssiMatch = line.match(/rssi:([\-.\d]+)/);
      const batteryMatch = line.match(/battery:(\d+)/);
      const deviceNameMatch = line.match(/deviceName:([^,\}]+)/);
      const deviceTypeMatch = line.match(/deviceType:([^,\}]+)/);

      const jsonData = {};
      if (typeMatch) jsonData.type = typeMatch[1];
      if (deviceTypeMatch) {
        jsonData.deviceType = deviceTypeMatch[1].trim();
        dev.deviceType = jsonData.deviceType;
      }
      if (latMatch) jsonData.lat = parseFloat(latMatch[1]);
      if (lonMatch) jsonData.lon = parseFloat(lonMatch[1]);
      if (altMatch) jsonData.alt = parseFloat(altMatch[1]);
      if (fixMatch) jsonData.fix = parseInt(fixMatch[1]);
      if (satMatch) jsonData.sat = parseInt(satMatch[1]);
      if (stepsMatch) jsonData.steps = parseInt(stepsMatch[1]);
      if (signalMatch) jsonData.signal = parseInt(signalMatch[1]);
      if (rssiMatch) jsonData.rssi = parseFloat(rssiMatch[1]);
      if (batteryMatch) jsonData.battery = parseInt(batteryMatch[1]);
      if (deviceNameMatch) jsonData.deviceName = deviceNameMatch[1].trim();

      if (jsonData.type === 'data') {
        if (jsonData.fix > 0) {
          let lat = jsonData.lat || 0;
          let lng = jsonData.lon || 0;
          // 修复经纬度反转：如果纬度超出范围(>90)或看起来是反转的，交换它们
          if (lat > 90 || lat < -90 || (lat > 55 && lng < 55) || (lat < 55 && lng > 90 && lat > lng)) {
            [lat, lng] = [lng, lat]; // 交换经纬度
          }
          dev.gps = {
            latitude: lat, longitude: lng,
            altitude: jsonData.alt || 0, satellites: jsonData.sat || 0,
            hdop: 0, raw: line, isValid: true
          };
          broadcastToClients({ type: 'device_data', data: { deviceId, gps: dev.gps } });
        }
        // 以太网设备不更新步数，步数只由IoT设备更新
        if (dev.deviceType !== 'ethernet') {
          dev.step.count = jsonData.steps || 0;
          dev.step.lastUpdate = timestamp;
          broadcastToClients({ type: 'device_data', data: { deviceId, step: dev.step } });
        }
      }
      else if (jsonData.type === 'status') {
        dev.status.signal = jsonData.signal || 0;
        dev.status.rssi = jsonData.rssi || 0;
        dev.status.battery = jsonData.battery || 80;
        dev.status.raw = line;
        if (jsonData.deviceName) {
          dev.deviceName = jsonData.deviceName;
          const client = connectedClients.find(c => c.addr === dev.clientAddr);
          if (client) client.deviceName = dev.deviceName;
          broadcastDeviceList();
        }
        broadcastToClients({ type: 'device_data', data: { deviceId, gps: dev.gps, step: dev.step, status: { ...dev.status, deviceName: dev.deviceName } } });
      }
      else if (jsonData.type === 'ping') {
        if (dev.socket) dev.socket.write('{"type":"pong"}\r\n');
        broadcastToClients({ type: 'device_data', data: { deviceId, connected: true } });
      }
    } catch (err) {
      console.error(`[JSON] 解析失败: ${err.message}`);
    }
  }
}

// ==================== NMEA 解析 ====================
function parseNMEA_GGA(sentence) {
  if (!sentence.startsWith('$')) return null;
  const parts = sentence.split(',');
  if (parts.length < 15) return null;

  const fixQuality = parseInt(parts[6]);
  if (fixQuality === 0) {
    return { latitude: 0, longitude: 0, altitude: 0, satellites: 0, hdop: 0, isValid: false };
  }

  const lat = parseDM(parts[2], parts[3] === 'N');
  const lng = parseDM(parts[4], parts[5] === 'E');
  const altitude = parseFloat(parts[9]) || 0;
  const satellites = parseInt(parts[7]) || 0;
  const hdop = parseFloat(parts[8]) || 0;

  return { latitude: lat, longitude: lng, altitude, satellites, hdop, isValid: true };
}

function parseDM(dmStr, isPositive) {
  if (!dmStr || dmStr.length < 4) return 0;
  const dotIndex = dmStr.indexOf('.');
  let degrees, minutes;

  if (dotIndex > 0) {
    const intPart = dmStr.substring(0, dotIndex);
    const decPart = dmStr.substring(dotIndex + 1);
    if (intPart.length <= 2) {
      degrees = parseInt(intPart.substring(0, 2));
      minutes = parseFloat(intPart.substring(2) + '.' + decPart);
    } else {
      degrees = parseInt(intPart.substring(0, 3));
      minutes = parseFloat(intPart.substring(3) + '.' + decPart);
    }
  } else {
    degrees = parseInt(dmStr.substring(0, dmStr.length - 2));
    minutes = parseInt(dmStr.substring(dmStr.length - 2));
  }

  let decimal = degrees + minutes / 60;
  if (!isPositive) decimal = -decimal;
  return decimal;
}

// ==================== HTTP 服务器 ====================
const httpServer = http.createServer((req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const reqPath = parsedUrl.pathname;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

  // API: 获取所有设备列表
  if (reqPath === BASE_PATH + '/api/devices' && req.method === 'GET') {
    const list = [];
    for (const [id, dev] of devices) {
      list.push({
        deviceId: id, deviceName: dev.deviceName, connected: dev.connected,
        lastUpdate: dev.lastUpdate, clientAddr: dev.clientAddr,
        gps: dev.gps, step: dev.step, status: dev.status
      });
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ devices: list }));
    return;
  }

  // API: 获取指定设备数据
  if (reqPath.startsWith(BASE_PATH + '/api/device/') && req.method === 'GET') {
    const deviceId = reqPath.substring((BASE_PATH + '/api/device/').length);
    const dev = devices.get(deviceId);
    if (dev) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        deviceId: dev.deviceId, deviceName: dev.deviceName, connected: dev.connected,
        lastUpdate: dev.lastUpdate, gps: dev.gps, step: dev.step, status: dev.status
      }));
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: '设备不存在' }));
    }
    return;
  }

  // API: 兼容旧接口 - 返回第一个设备的数据
  if (reqPath === BASE_PATH + '/api/data' && req.method === 'GET') {
    const firstDev = devices.values().next().value;
    if (firstDev) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        connected: firstDev.connected, lastUpdate: firstDev.lastUpdate,
        gps: firstDev.gps, step: firstDev.step, status: firstDev.status,
        rawLog: firstDev.rawLog, connectionHistory: firstDev.connectionHistory
      }));
    } else {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ connected: false }));
    }
    return;
  }

  // 健康检查
  if (reqPath === BASE_PATH + '/api/health' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', devices: devices.size, uptime: process.uptime() }));
    return;
  }

  // TCP 调试面板 API
  if (reqPath === BASE_PATH + '/api/tcp-debug' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      serverStatus: tcpMonitor.serverStatus, connected: tcpMonitor.connected,
      port: tcpMonitor.port, uptime: process.uptime(),
      totalConnections: tcpMonitor.disconnects + (tcpMonitor.connected ? 1 : 0),
      totalDisconnects: tcpMonitor.disconnects, totalMessages: tcpMonitor.msgCount,
      clients: connectedClients.map(c => ({
        id: c.id, addr: c.addr, deviceId: c.deviceId, deviceName: c.deviceName,
        connectTime: c.connectTime, bytesReceived: c.bytesReceived, bytesSent: c.bytesSent, msgCount: c.msgCount
      })),
      messages: messageBuffer.slice(-100)
    }));
    return;
  }

  // 发送数据到 TCP 客户端
  if (reqPath === BASE_PATH + '/api/tcp-send' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const { message, deviceId } = JSON.parse(body);
        let targetSocket = null;
        if (deviceId) {
          const dev = devices.get(deviceId);
          if (dev && dev.socket) targetSocket = dev.socket;
        } else {
          targetSocket = [...devices.values()].find(d => d.socket)?.socket;
        }
        if (targetSocket && !targetSocket.destroyed) {
          targetSocket.write(message + '\r\n');
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: true, sent: message }));
        } else {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: false, error: '没有活动的 TCP 连接' }));
        }
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: false, error: err.message }));
      }
    });
    return;
  }

  // 静态文件服务
  if (reqPath === BASE_PATH + '/' || reqPath === BASE_PATH) {
    serveStaticFile(res, 'index.html'); return;
  }
  if (reqPath.startsWith(BASE_PATH + '/')) {
    const filePath = reqPath.substring(BASE_PATH.length + 1);
    if (filePath && !filePath.includes('.')) { serveStaticFile(res, 'index.html'); return; }
    if (filePath) { serveStaticFile(res, filePath); return; }
  }

  res.writeHead(404); res.end('Not Found');
});

function serveStaticFile(res, fileName) {
  const filePath = path.join(__dirname, 'public', fileName);
  const ext = path.extname(fileName);
  const mimeTypes = {
    '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
    '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf'
  };
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not Found'); return; }
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    res.end(data);
  });
}

// ==================== WebSocket ====================
function handleWebSocketUpgrade(req, socket, head) {
  const key = req.headers['sec-websocket-key'];
  const accept = generateAcceptKey(key);

  socket.write('HTTP/1.1 101 Switching Protocols\r\n' +
    'Upgrade: websocket\r\n' +
    'Connection: Upgrade\r\n' +
    `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);

  const ws = createWebSocket(socket);
  wsClients.add(ws);
  console.log('[WS] 新 WebSocket 客户端连接');

  // 发送初始数据：所有设备列表 + 每个设备的完整数据
  const deviceList = [];
  const deviceDataMap = {};
  for (const [id, dev] of devices) {
    deviceList.push({
      deviceId: id, deviceName: dev.deviceName, connected: dev.connected,
      lastUpdate: dev.lastUpdate, clientAddr: dev.clientAddr, stats: dev.stats
    });
    deviceDataMap[id] = {
      gps: dev.gps, step: dev.step, status: { ...dev.status, deviceName: dev.deviceName }, connected: dev.connected, stats: dev.stats
    };
  }
  ws.send(JSON.stringify({ type: 'init', data: { devices: deviceList, deviceData: deviceDataMap }, tcp: tcpMonitor }));

  ws.on('data', (data) => {
    if (data.length >= 2) {
      const opcode = data[0] & 0x0F;
      if (opcode === 0x08) ws.close();
      else if (opcode === 0x09) {
        const pong = Buffer.alloc(2);
        pong[0] = 0x8A; pong[1] = 0x00;
        socket.write(pong);
      }
    }
  });

  ws.on('error', () => { ws.readyState = 3; wsClients.delete(ws); });
  ws.on('close', () => { ws.readyState = 3; wsClients.delete(ws); });
}

function generateAcceptKey(key) {
  const crypto = require('crypto');
  return crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
}

function createWebSocket(socket) {
  const ws = {
    readyState: 1,
    send: function(data) { socket.write(encodeWSFrame(data)); },
    close: function() { ws.readyState = 3; socket.end(); },
    on: function(event, callback) { socket.on(event, callback); }
  };
  socket.on('error', () => { ws.readyState = 3; wsClients.delete(ws); });
  socket.on('close', () => { ws.readyState = 3; wsClients.delete(ws); });
  return ws;
}

function encodeWSFrame(data) {
  const buf = Buffer.from(data, 'utf8');
  const len = buf.length;
  let header;
  if (len < 126) {
    header = Buffer.alloc(2);
    header[0] = 0x81; header[1] = len;
  } else if (len < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81; header[1] = 126;
    header.writeUInt16BE(len, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81; header[1] = 127;
    header.writeBigUInt64BE(BigInt(len), 2);
  }
  return Buffer.concat([header, buf]);
}

// ==================== 启动 ====================
const wss = net.createServer(() => {});
wss.listen(8081, () => console.log('[WS] WebSocket 服务器启动，端口 8081'));

httpServer.listen(WEB_PORT, () => {
  console.log(`[WEB] Web 服务器启动，访问 http://localhost:${WEB_PORT}${BASE_PATH}`);
});

httpServer.on('upgrade', (req, socket, head) => {
  const parsedUrl = url.parse(req.url, true);
  if (parsedUrl.pathname === BASE_PATH + '/ws') {
    handleWebSocketUpgrade(req, socket, head);
  } else {
    socket.destroy();
  }
});

process.on('SIGINT', () => {
  console.log('\n[系统] 正在关闭服务器...');
  for (const ws of wsClients) ws.close();
  tcpServer.close(); httpServer.close();
  console.log('[系统] 服务器已关闭');
  process.exit(0);
});
