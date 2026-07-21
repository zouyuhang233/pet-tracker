# 秦楚监控平台 (cw_web)

> **QinChu Web** -- 基于 Node.js + Leaflet.js 的实时定位监控平台

---

## 模块概述

监控平台是秦楚 IoT 系统的云端展示层，负责接收定位器和网关上报的 GPS、步数、设备状态等数据，通过 WebSocket 实时推送到前端，在地图上可视化展示设备位置和移动轨迹。

## 系统架构

```
+------------------+
|   cw_web 服务器   |
|                  |
|  +------------+  |
|  | TCP Server |  | <-- :8080 接收设备数据
|  +------------+  |
|  +------------+  |
|  | WebSocket  |  | <-- :8081 实时推送
|  +------------+  |
|  +------------+  |
|  | HTTP Server|  | <-- :3002 网页服务
|  +------------+  |
+--------+---------+
         v
+------------------+
|   Web 浏览器     |
+------------------+
```

## 功能特性

- 实时 GPS 定位 -- Leaflet 地图显示设备位置和轨迹
- 步数统计 -- 实时显示计步数据
- 设备状态 -- 电池电量、信号强度、RSSI
- 数据日志 -- 原始数据流查看
- WebSocket 实时推送 -- 低延迟数据更新
- 响应式设计 -- 手机/平板/电脑自适应
- 深色主题 -- 专业监控界面风格
- 多设备管理 -- 支持多个终端同时在线

## 技术栈

| 技术 | 用途 |
|------|------|
| Node.js | 运行时环境 |
| net 模块 | TCP 服务器 (端口 8080) |
| ws 模块 | WebSocket 服务器 (端口 8081) |
| http 模块 | HTTP 服务器 (端口 3002) |
| Leaflet.js | 交互式地图 |
| 原生 JavaScript | 无框架依赖 |

## 快速开始

```bash
cd cw_web
npm install
node server.js
# 访问 http://localhost:3002/cw_dwq
```

## 配置说明

```javascript
const TCP_PORT = 8080;       // 设备连接端口
const WEB_PORT = 3002;       // 浏览器访问端口
const BASE_PATH = '/cw_dwq'; // 路由前缀
```

## API 接口

- `GET /api/data` -- 获取最新设备数据
- `GET /api/log` -- 获取原始数据日志
- `GET /api/health` -- 健康检查
- `GET /api/history` -- 获取连接历史

## 通信协议

设备通过 TCP 发送数据，服务器自动解析：

```
$GNGGA,014845.00,2233.1234,N,11357.5678,E,1,08,1.2,45.6,M,0.0,M,,*6A
STEP:42
STATUS:Battery=85%,Signal=23,RSSI=-67
```

## 部署指南

### PM2 (推荐)

```bash
npm install -g pm2
pm2 start server.js --name "location-server"
```

### Docker

```bash
docker build -t location-server .
docker run -d -p 3002:3002 -p 8080:8080 location-server
```

## 目录结构

```
cw_web/
+-- package.json
+-- server.js
+-- protocol.md
+-- README.md
+-- public/
|   +-- index.html
|   +-- style.css
|   +-- app.js
+-- *.py / *.sh        # 部署与运维脚本
```

## 开发计划

- [ ] 添加用户认证
- [ ] 数据持久化 (SQLite/MySQL)
- [ ] 历史轨迹回放
- [ ] 电子围栏功能
- [ ] 移动端 App
- [ ] 数据导出 (CSV/GPX)

## 依赖关系

```
cw_web (监控平台)
    |
    <-- cw_dinweiqi (定位器)  TCP:8080
    |
    <-- cw_wg (网关)          TCP:8080
```

---

**分支**: `web` | **作者**: zouyuhang | **许可证**: MIT
