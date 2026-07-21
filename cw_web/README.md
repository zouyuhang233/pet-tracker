# 定位器监控平台

基于 Node.js 的实时定位监控网站，用于接收 STM32 + MN316 NB-IoT 模块发送的 GPS 和步数数据。

## 功能特性

- 🌍 **实时 GPS 定位** - 在地图上显示设备位置和移动轨迹
- 👟 **步数统计** - 实时显示计步数据
- 📊 **设备状态** - 电池电量、信号强度等
- 📋 **数据日志** - 原始数据流查看
- 🔌 **WebSocket 实时推送** - 低延迟数据更新
- 📱 **响应式设计** - 支持手机、平板、电脑访问

## 技术栈

### 后端
- **Node.js** + **Express** - Web 服务器
- **net 模块** - TCP 服务器（端口 8080）
- **ws 模块** - WebSocket 服务器（端口 8081）

### 前端
- **Leaflet.js** - 地图显示
- **原生 JavaScript** - 无框架依赖
- **深色主题** - 专业的监控界面风格

## 快速开始

### 1. 安装依赖

```bash
cd cw_web
npm install
```

### 2. 启动服务器

```bash
# 开发模式
npm start

# 或直接运行
node server.js
```

### 3. 访问网站

打开浏览器访问：http://localhost:3000

## 配置说明

### TCP 服务器配置

在 `server.js` 中修改 TCP 端口：

```javascript
const TCP_PORT = 8080;  // MN316 设备连接的端口
```

### Web 服务器配置

```javascript
const WEB_PORT = 3000;  // 浏览器访问的端口
```

## 部署到云服务器

### 方式一：使用 PM2（推荐）

1. 安装 PM2：
```bash
npm install -g pm2
```

2. 启动服务：
```bash
pm2 start server.js --name "location-server"
```

3. 查看状态：
```bash
pm2 status
pm2 logs location-server
```

4. 设置开机自启：
```bash
pm2 startup
pm2 save
```

### 方式二：使用 systemd

创建 `/etc/systemd/system/location-server.service`：

```ini
[Unit]
Description=Location Monitor Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/cw_web
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable location-server
sudo systemctl start location-server
sudo systemctl status location-server
```

### 方式三：使用 Docker

创建 `Dockerfile`：

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --production
COPY . .
EXPOSE 3000 8080 8081
CMD ["node", "server.js"]
```

构建并运行：
```bash
docker build -t location-server .
docker run -d -p 3000:3000 -p 8080:8080 -p 8081:8081 location-server
```

## STM32 端配置

### 修改连接参数

在 `BSP/MN316_TCP.c` 中修改服务器地址和端口：

```c
// MN316_TCP_Test() 函数中
res = MN316_TCP_Connect("8.134.127.141", 8080);
```

### 发送数据

在 `APP/fun.c` 的 `main_pros()` 中添加 TCP 发送逻辑：

```c
// 发送 GPS 数据
char gps_data[128];
sprintf(gps_data, "$GNGGA,%s", gga_sentence);
MN316_TCP_Send((uint8_t*)gps_data, strlen(gps_data));

// 发送步数数据
char step_data[16];
sprintf(step_data, "STEP:%d", ADXL345_GetStepCount());
MN316_TCP_Send((uint8_t*)step_data, strlen(step_data));
```

详细协议请参考 [protocol.md](protocol.md)

## API 接口

### GET /api/data
获取最新数据

**响应示例：**
```json
{
  "connected": true,
  "lastUpdate": "2026-07-19T22:30:00.000Z",
  "gps": {
    "latitude": 22.543097,
    "longitude": 113.963917,
    "altitude": 45.6,
    "satellites": 8,
    "hdop": 1.2,
    "isValid": true
  },
  "step": {
    "count": 42,
    "lastUpdate": "2026-07-19T22:30:00.000Z"
  }
}
```

### GET /api/log
获取原始数据日志

### GET /api/health
健康检查

### GET /api/history
获取连接历史

## 防火墙配置

如果使用云服务器，需要开放端口：

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 3000/tcp  # Web 访问
sudo ufw allow 8080/tcp  # TCP 设备连接
sudo ufw allow 8081/tcp  # WebSocket

# CentOS/RHEL (firewall-cmd)
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --permanent --add-port=8081/tcp
sudo firewall-cmd --reload
```

## Nginx 反向代理（可选）

如果需要域名访问，配置 Nginx：

```nginx
server {
    listen 80;
    server_name zouyuhang.omline;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /ws {
        proxy_pass http://localhost:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

## 目录结构

```
cw_web/
├── package.json          # 项目配置
├── server.js             # 后端服务器
├── protocol.md           # 通信协议文档
├── README.md             # 项目说明
└── public/               # 前端文件
    ├── index.html        # 主页
    ├── style.css         # 样式
    └── app.js            # 前端逻辑
```

## 故障排查

### 1. TCP 连接失败

检查防火墙是否开放 8080 端口：
```bash
sudo ufw status
```

### 2. WebSocket 连接失败

检查 8081 端口是否开放，浏览器控制台是否有错误。

### 3. 地图不显示

检查网络连接，Leaflet 需要从 CDN 加载资源。

## 注意事项

1. **安全性**：当前版本没有认证机制，生产环境请添加身份验证
2. **数据持久化**：当前数据存储在内存中，重启会丢失，生产环境建议添加数据库
3. **HTTPS**：生产环境建议使用 HTTPS（Let's Encrypt 免费证书）
4. **域名解析**：确保 `zouyuhang.omline` 已解析到服务器 IP

## 开发计划

- [ ] 添加用户认证
- [ ] 数据持久化（SQLite/MySQL）
- [ ] 历史轨迹回放
- [ ] 电子围栏功能
- [ ] 移动端 App
- [ ] 数据导出（CSV/GPX）

## 作者

zouyuhang

## 许可证

MIT
