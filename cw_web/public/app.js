/**
 * 宠爱有家 - PetTracker 前端 JavaScript（多设备版）
 * 功能：
 * 1. WebSocket 连接接收实时数据
 * 2. 高德地图显示 GPS 位置
 * 3. 多设备切换选择器
 * 4. 数据更新、步数动画、滚动渐入
 */

// ==================== 全局变量 ====================
const BASE_PATH = '/cw_dwq';
const WS_PATH = '/cw_dwq/ws';

let ws = null;
let reconnectAttempts = 0;
let reconnectDelay = 1000;
let messageCount = 0;
let messagesPerMinute = 0;
let messageTimestamps = [];
let serverStartTime = null;

// 多设备管理
let devices = {};           // { deviceId: { deviceName, connected, lastUpdate, gps, step, status } }
let currentDeviceId = null; // 当前选中的设备ID
let deviceConnected = false;

// ==================== 页面初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    console.log('[前端] 页面加载完成');

    fetch(BASE_PATH + '/api/health')
        .then(res => res.json())
        .then(data => {
            serverStartTime = Date.now() - (data.uptime * 1000);
            updateUptime();
            setInterval(updateUptime, 1000);
        })
        .catch(() => {});

    initMap();
    connectWebSocket();
    setInterval(fetchLatestData, 5000);
    initScrollAnimations();
    initSmoothScroll();
});

// ==================== 平滑滚动 ====================
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                const offset = 80;
                const targetPos = target.getBoundingClientRect().top + window.pageYOffset - offset;
                window.scrollTo({ top: targetPos, behavior: 'smooth' });
            }
        });
    });
}

// ==================== 滚动渐入动画 ====================
function initScrollAnimations() {
    const sections = document.querySelectorAll('.dashboard-section');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
    }, { threshold: 0.05, rootMargin: '0px 0px -30px 0px' });
    sections.forEach(section => observer.observe(section));
    setTimeout(() => {
        sections.forEach(section => {
            if (section.getBoundingClientRect().top < window.innerHeight) section.classList.add('visible');
        });
    }, 300);
}

// ==================== WebSocket 连接 ====================
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${WS_PATH}`;
    console.log(`[WebSocket] 连接到 ${wsUrl}`);

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[WebSocket] 连接成功');
        reconnectAttempts = 0;
        reconnectDelay = 1000;
    };

    ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (err) {
            console.error('[WebSocket] 解析消息失败:', err);
        }
    };

    ws.onerror = (err) => console.error('[WebSocket] 错误:', err);

    ws.onclose = () => {
        console.log('[WebSocket] 连接断开');
        const dot = document.getElementById('connectionDot');
        const text = document.getElementById('connectionText');
        if (dot) dot.className = 'conn-dot disconnected';
        if (text) text.textContent = '网页已断开，等待重连...';
        if (reconnectAttempts < 10) {
            setTimeout(connectWebSocket, reconnectDelay);
            reconnectAttempts++;
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        }
    };
}

function handleWebSocketMessage(message) {
    messageCount++;
    messageTimestamps.push(Date.now());

    switch (message.type) {
        case 'init':
            // 初始化设备列表 + 设备数据
            if (message.data && message.data.devices) {
                message.data.devices.forEach(d => {
                    const existing = devices[d.deviceId];
                    const dd = (message.data.deviceData && message.data.deviceData[d.deviceId]) || {};
                    devices[d.deviceId] = {
                        ...d,
                        gps: (existing && existing.gps) || dd.gps || { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
                        step: (existing && existing.step) || dd.step || { count: 0, lastUpdate: null },
                        status: (existing && existing.status) || dd.status || { battery: null, signal: null, rssi: null, deviceName: null, raw: null },
                        stats: (existing && existing.stats) || dd.stats || { bytesReceived: 0, bytesSent: 0, msgCount: 0 }
                    };
                });
                updateDeviceSelector();
                // 自动选中第一个设备并更新UI
                if (!currentDeviceId && Object.keys(devices).length > 0) {
                    selectDevice(Object.keys(devices)[0]);
                } else if (currentDeviceId && devices[currentDeviceId]) {
                    const dev = devices[currentDeviceId];
                    updateConnectionStatus(dev.connected);
                    if (dev.gps) updateGPSData(dev.gps);
                    if (dev.step) updateStepData(dev.step);
                    if (dev.status) updateStatusData(dev.status);
                }
            }
            if (message.tcp) updateTcpMonitor(message.tcp);
            break;

        case 'device_list':
            // 更新设备列表
            message.data.forEach(d => {
                if (!devices[d.deviceId]) {
                    devices[d.deviceId] = {
                        ...d,
                        gps: { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
                        step: { count: 0, lastUpdate: null },
                        status: { battery: null, signal: null, rssi: null, deviceName: null, raw: null },
                        stats: d.stats || { bytesReceived: 0, bytesSent: 0, msgCount: 0 }
                    };
                } else {
                    devices[d.deviceId].connected = d.connected;
                    devices[d.deviceId].deviceName = d.deviceName;
                    devices[d.deviceId].lastUpdate = d.lastUpdate;
                    if (d.stats) devices[d.deviceId].stats = d.stats;
                }
            });
            // 移除已不存在的设备
            const activeIds = message.data.map(d => d.deviceId);
            Object.keys(devices).forEach(id => {
                if (!activeIds.includes(id)) delete devices[id];
            });
            updateDeviceSelector();
            break;

        case 'device_data':
            // 设备数据更新
            const dd = message.data;
            if (dd.deviceId && devices[dd.deviceId]) {
                const dev = devices[dd.deviceId];
                if (dd.gps) dev.gps = dd.gps;
                if (dd.step) dev.step = dd.step;
                if (dd.status) dev.status = dd.status;
                if (dd.connected !== undefined) dev.connected = dd.connected;
                if (dd.stats) dev.stats = dd.stats;
                // 如果是当前选中的设备，更新UI（始终用设备最新数据）
                if (dd.deviceId === currentDeviceId) {
                    updateGPSData(dev.gps);
                    updateStepData(dev.step);
                    updateStatusData(dev.status);
                    if (dd.connected !== undefined) updateConnectionStatus(dd.connected);
                    if (dd.stats) updateDeviceStats(dd.stats);
                }
                updateDeviceSelector();
            }
            break;

        case 'device_stats':
            // 设备统计数据更新
            const ds = message.data;
            if (ds.deviceId && devices[ds.deviceId]) {
                devices[ds.deviceId].stats = ds.stats;
                if (ds.deviceId === currentDeviceId) {
                    updateDeviceStats(ds.stats);
                }
            }
            break;

        case 'device_connect':
            // 设备连接/断开
            const dc = message.data;
            if (dc.deviceId && devices[dc.deviceId]) {
                devices[dc.deviceId].connected = dc.connected;
            } else if (dc.connected) {
                devices[dc.deviceId] = {
                    deviceId: dc.deviceId, deviceName: dc.deviceId, connected: true,
                    lastUpdate: new Date(),
                    gps: { latitude: null, longitude: null, altitude: null, satellites: null, hdop: null, raw: null, isValid: false },
                    step: { count: 0, lastUpdate: null },
                    status: { battery: null, signal: null, rssi: null, deviceName: null, raw: null },
                    stats: { bytesReceived: 0, bytesSent: 0, msgCount: 0 }
                };
            }
            // 如果当前设备离线，切换到下一个在线设备
            if (dc.deviceId === currentDeviceId && !dc.connected) {
                const onlineIds = Object.keys(devices).filter(id => devices[id].connected && id !== dc.deviceId);
                if (onlineIds.length > 0) {
                    selectDevice(onlineIds[0]);
                } else {
                    currentDeviceId = null;
                    updateConnectionStatus(false);
                }
            }
            updateDeviceSelector();
            break;

        case 'tcp_monitor':
            updateTcpMonitor(message.data);
            break;

        case 'tcp_raw':
            addTcpRawLog(message.data);
            break;
    }
}

// ==================== 设备选择器 ====================
function updateDeviceSelector() {
    const container = document.getElementById('deviceSelector');
    if (!container) return;

    // 只显示在线设备
    const ids = Object.keys(devices).filter(id => devices[id].connected);
    if (ids.length === 0) {
        container.innerHTML = '<div class="device-selector-empty">等待设备连接...</div>';
        // 如果当前选中的设备离线了，清空选择
        if (currentDeviceId && devices[currentDeviceId] && !devices[currentDeviceId].connected) {
            currentDeviceId = null;
        }
        return;
    }

    // 如果当前选中的设备离线了，自动切换到第一个在线设备
    if (currentDeviceId && !devices[currentDeviceId]?.connected) {
        currentDeviceId = ids[0];
        selectDevice(ids[0]);
        return; // selectDevice 会再次调用 updateDeviceSelector
    }
    if (!currentDeviceId) {
        currentDeviceId = ids[0];
    }

    let html = '';
    ids.forEach(id => {
        const dev = devices[id];
        const isActive = id === currentDeviceId;
        const name = dev.deviceName || id;
        html += `<div class="device-item ${isActive ? 'active' : ''}" onclick="selectDevice('${id}')">
            <span class="device-status-dot online"></span>
            <span class="device-name">${escapeHtml(name)}</span>
        </div>`;
    });
    container.innerHTML = html;
}

function selectDevice(deviceId) {
    if (!devices[deviceId]) return;
    currentDeviceId = deviceId;
    const dev = devices[deviceId];

    // 更新UI
    updateConnectionStatus(dev.connected);
    updateGPSData(dev.gps);
    updateStepData(dev.step);
    updateStatusData(dev.status);
    updateDeviceStats(dev.stats || { bytesReceived: 0, bytesSent: 0, msgCount: 0 });
    updateDeviceSelector();

    // 更新连接时间显示
    if (dev.connected && dev.lastUpdate) {
        const connText = document.getElementById('connectionText');
        if (connText) connText.textContent = `追踪中 · 更新于 ${formatTime(new Date(dev.lastUpdate))}`;
    }
}

function updateDeviceStats(stats) {
    setText('tcpBytesReceived', formatBytes(stats.bytesReceived || 0));
    setText('tcpMsgCount', stats.msgCount || '0');
    // 更新客户端地址为当前设备的
    const dev = devices[currentDeviceId];
    if (dev) setText('tcpClientAddr', dev.clientAddr || '--');
}

// ==================== 连接状态 ====================
function updateConnectionStatus(connected) {
    deviceConnected = connected;
    const dot = document.getElementById('connectionDot');
    const text = document.getElementById('connectionText');
    if (dot) dot.className = connected ? 'conn-dot connected' : 'conn-dot disconnected';
    if (text) {
        text.textContent = connected ? '设备已连接，实时追踪中' : '设备已离线，显示最后数据';
    }
}

// ==================== UI 更新函数 ====================
function updateGPSData(gps) {
    if (!gps) return;
    const latEl = document.getElementById('latitude');
    const lonEl = document.getElementById('longitude');
    const altEl = document.getElementById('altitude');
    const satEl = document.getElementById('satellites');
    const statusBadge = document.getElementById('gpsStatus');

    if (gps.latitude != null && gps.latitude !== 0) {
        if (latEl) latEl.textContent = gps.latitude.toFixed(6);
        if (lonEl) lonEl.textContent = gps.longitude.toFixed(6);
    }
    if (altEl) altEl.textContent = (gps.altitude != null && gps.altitude !== 0) ? `${gps.altitude.toFixed(1)} m` : '--';
    if (satEl) satEl.textContent = gps.satellites || '--';

    if (statusBadge) {
        if (gps.isValid) {
            statusBadge.textContent = '定位有效';
            statusBadge.className = 'dash-badge valid';
        } else {
            statusBadge.textContent = '等待定位...';
            statusBadge.className = 'dash-badge';
        }
    }

    if (gps.isValid && gps.latitude && gps.longitude) {
        updateMapMarker(gps.latitude, gps.longitude, gps.altitude);
    }
}

function updateStepData(step) {
    if (!step) return;
    const stepCountEl = document.getElementById('stepCount');
    if (!stepCountEl) return;

    const currentCount = parseInt(stepCountEl.textContent) || 0;
    if (step.count > currentCount) animateStepCount(step.count);
    stepCountEl.textContent = step.count;

    const statStepsEl = document.getElementById('statSteps');
    if (statStepsEl) statStepsEl.textContent = step.count;

    const stepRing = document.getElementById('stepRing');
    if (stepRing) {
        const progress = Math.min(step.count / 10000, 1);
        const circumference = 2 * Math.PI * 54;
        stepRing.style.strokeDashoffset = circumference * (1 - progress);
    }

    if (step.lastUpdate) {
        document.getElementById('stepTime').textContent = `最后更新: ${formatTime(new Date(step.lastUpdate))}`;
    }
}

function updateStatusData(status) {
    if (!status) return;
    const batteryEl = document.getElementById('battery');
    if (batteryEl && status.battery !== null && status.battery !== undefined) {
        batteryEl.textContent = `${status.battery}%`;
        batteryEl.style.color = status.battery > 50 ? '#6A9E84' : status.battery > 20 ? '#C49A3C' : '#D48B7E';
    } else if (batteryEl) {
        batteryEl.textContent = '--';
        batteryEl.style.color = '';
    }

    document.getElementById('signal').textContent = status.signal || '--';
    document.getElementById('rssi').textContent = status.rssi !== null ? `${status.rssi} dBm` : '--';

    const statBatteryEl = document.getElementById('statBattery');
    if (statBatteryEl) statBatteryEl.textContent = status.battery !== null ? `${status.battery}%` : '--';

    if (status.deviceName) {
        const el = document.getElementById('deviceName');
        if (el) el.textContent = status.deviceName;
        const statEl = document.getElementById('statDeviceName');
        if (statEl) statEl.textContent = status.deviceName;
    }
}

// ==================== TCP 服务监控 ====================
let tcpMonitorData = { connected: false, serverStatus: '未启动', port: 8080, clientAddr: '--', connDuration: '--', bytesReceived: 0, bytesSent: 0, msgCount: 0, disconnects: 0 };

function updateTcpMonitor(data) {
    tcpMonitorData = { ...tcpMonitorData, ...data };
    const statusBadge = document.getElementById('tcpStatusBadge');
    if (statusBadge) {
        statusBadge.textContent = tcpMonitorData.connected ? '在线' : '离线';
        statusBadge.className = tcpMonitorData.connected ? 'dash-badge valid' : 'dash-badge';
    }
    setText('tcpServerStatus', tcpMonitorData.serverStatus || '--');
    setText('tcpPort', tcpMonitorData.port || '8080');

    // 如果当前选中了设备，显示该设备的客户端地址
    const dev = devices[currentDeviceId];
    if (dev && dev.connected) {
        setText('tcpClientAddr', dev.clientAddr || '--');
    } else {
        setText('tcpClientAddr', tcpMonitorData.clientAddr || '--');
    }
}

function addTcpRawLog(data) {
    const container = document.getElementById('tcpRawContainer');
    if (!container) return;
    const emptyMsg = container.querySelector('.log-empty');
    if (emptyMsg) emptyMsg.remove();

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const time = data.time || new Date();
    const text = data.text || data.data || '';
    const typeClass = data.type || 'tcp-event';
    entry.innerHTML = `<span class="log-time">${formatTime(time)}</span><span class="log-text ${typeClass}">${escapeHtml(text)}</span>`;
    container.insertBefore(entry, container.firstChild);
    while (container.children.length > 200) container.removeChild(container.lastChild);
}

function clearTcpRaw() {
    const container = document.getElementById('tcpRawContainer');
    if (container) container.innerHTML = '<div class="log-empty">等待 TCP 连接...</div>';
}

// ==================== 坐标转换 WGS84 → GCJ-02 ====================
const PI = Math.PI, a = 6378245.0, ee = 0.00669342162296594323;

function outOfChina(lat, lng) {
    return (lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271);
}

function transformLat(x, y) {
    let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(y * PI) + 40.0 * Math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(y / 12.0 * PI) + 320.0 * Math.sin(y * PI / 30.0)) * 2.0 / 3.0;
    return ret;
}

function transformLng(x, y) {
    let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(x * PI) + 40.0 * Math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(x / 12.0 * PI) + 300.0 * Math.sin(x / 30.0 * PI)) * 2.0 / 3.0;
    return ret;
}

function wgs84ToGcj02(lat, lng) {
    if (outOfChina(lat, lng)) return { lat, lng };
    let dLat = transformLat(lng - 105.0, lat - 35.0);
    let dLng = transformLng(lng - 105.0, lat - 35.0);
    const radLat = lat / 180.0 * PI;
    let magic = Math.sin(radLat);
    magic = 1 - ee * magic * magic;
    const sqrtMagic = Math.sqrt(magic);
    dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * PI);
    dLng = (dLng * 180.0) / (a / sqrtMagic * Math.cos(radLat) * PI);
    return { lat: lat + dLat, lng: lng + dLng };
}

// ==================== 地图功能（高德地图） ====================
let amap = null, amapMarker = null, amapPolyline = null, amapInfoWindow = null, amapPathPoints = [], mapLoaded = false;

function initMap() {
    if (typeof AMap === 'undefined') {
        document.getElementById('map').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8C7B74;">地图加载失败，请刷新页面</div>';
        return;
    }
    amap = new AMap.Map('map', { zoom: 13, center: [113.9639, 22.5431], viewMode: '2D', mapStyle: 'amap://styles/whitesmoke', features: ['bg', 'road', 'building'] });
    amapMarker = new AMap.Marker({ position: [113.9639, 22.5431], map: amap, title: '当前位置' });
    amapPathPoints = [];
    amapPolyline = new AMap.Polyline({ path: amapPathPoints, strokeColor: '#8CB8A0', strokeWeight: 4, strokeOpacity: 0.7, lineJoin: 'round', lineCap: 'round', showDir: true });
    amap.add(amapPolyline);
    amapInfoWindow = new AMap.InfoWindow({ isCustom: true, offset: new AMap.Pixel(0, -30) });
    mapLoaded = true;
}

function updateMapMarker(lat, lng, altitude) {
    if (!mapLoaded || !amap) return;
    // WGS84 → GCJ-02 坐标转换
    const gcj = wgs84ToGcj02(lat, lng);
    lat = gcj.lat;
    lng = gcj.lng;
    const position = [lng, lat];
    if (amapMarker) { amapMarker.setPosition(position); amapMarker.setTitle('当前位置'); }

    const infoContent = `<div style="padding:10px 14px;background:#FFF;border-radius:10px;box-shadow:0 4px 16px rgba(90,74,66,0.12);font-family:Nunito,Arial,sans-serif;min-width:180px;border:1px solid rgba(140,184,160,0.15);">
        <div style="font-weight:700;color:#6A9E84;margin-bottom:6px;font-size:0.95rem;">🐾 当前位置</div>
        <div style="font-size:0.82rem;color:#5A4A42;line-height:1.8;">
            <div>纬度: <strong>${lat.toFixed(6)}</strong></div>
            <div>经度: <strong>${lng.toFixed(6)}</strong></div>
            ${altitude ? `<div>海拔: <strong>${altitude.toFixed(1)} m</strong></div>` : ''}
            <div style="color:#8C7B74;font-size:0.72rem;margin-top:4px;">${formatTime(new Date())}</div>
        </div>
    </div>`;
    amapInfoWindow.setContent(infoContent);
    amapInfoWindow.open(amap, position);

    amapPathPoints.push(position);
    if (amapPathPoints.length > 200) amapPathPoints.shift();
    if (amapPolyline) amapPolyline.setPath(amapPathPoints);
}

function centerMap() {
    if (!mapLoaded || !amap) return;
    const dev = devices[currentDeviceId];
    if (dev && dev.gps && dev.gps.isValid) {
        // WGS84 → GCJ-02 坐标转换
        const gcj = wgs84ToGcj02(dev.gps.latitude, dev.gps.longitude);
        amap.setZoomAndCenter(15, [gcj.lng, gcj.lat]);
    }
}

// ==================== 工具函数 ====================
function formatTime(date) {
    if (!date) return '--:--:--';
    const pad = (n) => n.toString().padStart(2, '0');
    const d = date instanceof Date ? date : new Date(date);
    if (isNaN(d.getTime())) return '--:--:--';
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function animateStepCount(targetCount) {
    const stepCountEl = document.getElementById('stepCount');
    const currentCount = parseInt(stepCountEl.textContent) || 0;
    const increment = targetCount - currentCount;
    const duration = 600, steps = 30, stepValue = increment / steps;
    let current = currentCount, step = 0;
    const timer = setInterval(() => {
        step++; current += stepValue;
        if (step >= steps) { current = targetCount; clearInterval(timer); }
        stepCountEl.textContent = Math.round(current);
    }, duration / steps);
}

// ==================== 运行时间与统计 ====================
function updateUptime() {
    const pad = (n) => n.toString().padStart(2, '0');

    const uptimeEl = document.getElementById('uptime');
    const statUptimeEl = document.getElementById('statUptime');

    // 显示当前选中设备的在线时长
    const dev = devices[currentDeviceId];
    if (dev && dev.connected && dev.lastUpdate) {
        // 用lastUpdate近似（实际应从连接时间开始计）
        if (uptimeEl) uptimeEl.textContent = '--:--:--';
        if (statUptimeEl) statUptimeEl.textContent = '--:--:--';
    } else {
        if (uptimeEl) uptimeEl.textContent = '00:00:00';
        if (statUptimeEl) statUptimeEl.textContent = '00:00:00';
    }

    const now = Date.now();
    messageTimestamps = messageTimestamps.filter(t => now - t < 60000);
    messagesPerMinute = messageTimestamps.length;
    const dataRateEl = document.getElementById('dataRate');
    const totalMsgEl = document.getElementById('totalMessages');
    if (dataRateEl) dataRateEl.textContent = messagesPerMinute;
    if (totalMsgEl) totalMsgEl.textContent = messageCount;
}

// ==================== 数据获取（备用） ====================
function fetchLatestData() {
    fetch(BASE_PATH + '/api/devices')
        .then(res => res.json())
        .then(data => {
            if (data.devices) {
                data.devices.forEach(d => {
                    if (!devices[d.deviceId]) {
                        devices[d.deviceId] = { ...d, gps: d.gps || {}, step: d.step || {}, status: d.status || {}, stats: d.stats || {} };
                    } else {
                        Object.assign(devices[d.deviceId], d);
                    }
                });
                updateDeviceSelector();
                if (!currentDeviceId && Object.keys(devices).length > 0) {
                    selectDevice(Object.keys(devices)[0]);
                } else if (currentDeviceId && devices[currentDeviceId]) {
                    const dev = devices[currentDeviceId];
                    if (dev.gps) updateGPSData(dev.gps);
                    if (dev.step) updateStepData(dev.step);
                    if (dev.status) updateStatusData(dev.status);
                }
            }
        })
        .catch(() => {});
}

setInterval(() => { if (serverStartTime) updateUptime(); }, 1000);

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) fetchLatestData();
});

// ==================== 详情弹窗 ====================
function openStatusModal() {
    const dev = devices[currentDeviceId];
    const modal = document.getElementById('modalOverlay');
    const header = document.getElementById('modalHeader');
    const body = document.getElementById('modalBody');
    header.textContent = '📊 设备状态详情';
    body.innerHTML = `<div class="modal-data-list">
        <div class="modal-data-item"><span class="modal-data-label">设备ID</span><span class="modal-data-value highlight">${currentDeviceId || '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">设备名称</span><span class="modal-data-value highlight">${dev ? (dev.deviceName || '--') : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">连接状态</span><span class="modal-data-value ${dev && dev.connected ? 'highlight' : ''}">${dev && dev.connected ? '在线' : '离线'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">电池电量</span><span class="modal-data-value">${dev && dev.status ? (dev.status.battery !== null ? dev.status.battery + '%' : '--') : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">信号强度</span><span class="modal-data-value">${dev && dev.status ? (dev.status.signal || '--') : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">RSSI</span><span class="modal-data-value">${dev && dev.status && dev.status.rssi !== null ? dev.status.rssi + ' dBm' : '--'}</span></div>
    </div>`;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function openGPSModal() {
    const dev = devices[currentDeviceId];
    const gps = dev ? dev.gps : {};
    const modal = document.getElementById('modalOverlay');
    document.getElementById('modalHeader').textContent = '🌍 GPS 位置详情';
    document.getElementById('modalBody').innerHTML = `<div class="modal-data-list">
        <div class="modal-data-item"><span class="modal-data-label">定位状态</span><span class="modal-data-value highlight">${gps && gps.isValid ? '定位有效' : '等待定位...'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">纬度</span><span class="modal-data-value highlight">${gps && gps.latitude ? gps.latitude.toFixed(6) : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">经度</span><span class="modal-data-value highlight">${gps && gps.longitude ? gps.longitude.toFixed(6) : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">海拔</span><span class="modal-data-value">${gps && gps.altitude ? gps.altitude + ' m' : '--'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">卫星数</span><span class="modal-data-value">${gps ? (gps.satellites || '--') : '--'}</span></div>
    </div>`;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function openStepModal() {
    const dev = devices[currentDeviceId];
    const step = dev ? dev.step : {};
    const modal = document.getElementById('modalOverlay');
    document.getElementById('modalHeader').textContent = '🦴 今日步数详情';
    document.getElementById('modalBody').innerHTML = `<div class="modal-data-list">
        <div class="modal-data-item"><span class="modal-data-label">步数</span><span class="modal-data-value highlight" style="font-size:1.3rem;">${step.count || 0} 步</span></div>
        <div class="modal-data-item"><span class="modal-data-label">目标</span><span class="modal-data-value">10,000 步</span></div>
        <div class="modal-data-item"><span class="modal-data-label">完成度</span><span class="modal-data-value">${(Math.min((step.count || 0) / 10000, 1) * 100).toFixed(1)}%</span></div>
        <div class="modal-data-item"><span class="modal-data-label">最后更新</span><span class="modal-data-value">${step.lastUpdate ? formatTime(new Date(step.lastUpdate)) : '--'}</span></div>
    </div>`;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function openTcpModal() {
    const modal = document.getElementById('modalOverlay');
    document.getElementById('modalHeader').textContent = '🔌 TCP 服务监控详情';
    document.getElementById('modalBody').innerHTML = `<div class="modal-data-list">
        <div class="modal-data-item"><span class="modal-data-label">服务状态</span><span class="modal-data-value highlight">${tcpMonitorData.connected ? '在线' : '离线'}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">监听端口</span><span class="modal-data-value highlight">${tcpMonitorData.port}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">客户端地址</span><span class="modal-data-value">${tcpMonitorData.clientAddr}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">连接时长</span><span class="modal-data-value">${tcpMonitorData.connDuration}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">接收字节</span><span class="modal-data-value">${formatBytes(tcpMonitorData.bytesReceived)}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">接收消息数</span><span class="modal-data-value">${tcpMonitorData.msgCount}</span></div>
        <div class="modal-data-item"><span class="modal-data-label">断开次数</span><span class="modal-data-value">${tcpMonitorData.disconnects}</span></div>
    </div>`;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
window.addEventListener('error', (event) => console.error('[前端] 全局错误:', event.error));
window.addEventListener('unhandledrejection', (event) => console.error('[前端] 未处理的 Promise 拒绝:', event.reason));
