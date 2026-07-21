# 宠物定位器 - 监控平台 (cw_web)

> Pet Tracker Web -- 基于 Node.js + Leaflet.js 的实时定位监控平台

---

## 模块概述

监控平台是宠物定位系统的云端展示层，负责接收定位器和网关上报的 GPS、步数、设备状态等数据，通过 WebSocket 实时推送到前端，在地图上可视化展示宠物位置和移动轨迹。

## 系统架构

```
+------------------+
|   cw_web 服务器   |
|                  |
|  TCP Server     | <-- :8080 接收设备数据
|  WebSocket      | <-- :8081 实时推送
|  HTTP Server    | <-- :3002 网页服务
+--------+---------+
         v
+------------------+
|   Web 浏览器     |
+------------------+
```

## 功能特性

- 实时 GPS 定位 -- Leaflet 地图显示宠物位置和轨迹
- 步数统计 -- 实时显示计步数据
- 设备状态 -- 电池电量、信号强度、RSSI
- WebSocket 实时推送 -- 低延迟数据更新
- 响应式设计 -- 手机/平板/电脑自适应
- 深色主题 -- 专业监控界面风格
- 多设备管理 -- 支持多个终端同时在线

## 快速开始

```bash
cd cw_web
npm install
node server.js
# 访问 http://localhost:3002/cw_dwq
```

## 文件结构

```
cw_web/
+-- package.json
+-- server.js
+-- protocol.md
+-- public/
|   +-- index.html
|   +-- style.css
|   +-- app.js
+-- *.py / *.sh        # 部署与运维脚本
```

---

**分支**: `web` | **作者**: zouyuhang | **许可证**: MIT
