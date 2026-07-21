# 秦楚 IoT 智能定位监控系统

> **QinChu IoT** -- 基于 STM32 + NB-IoT + W5500 以太网 + Node.js 的智能定位监控平台

---

## 系统架构

```
+-----------------+     NB-IoT (TCP)     +------------------+
|   cw_dinweiqi   | --------------------->|                  |
|  STM32F103C8T6  |                       |   cw_web         |
|  GPS + ADXL345  |                       |   Node.js 服务器  |
|  MN316 NB-IoT   |                       |   Web 监控平台    |
+-----------------+                       |                  |
                                          |  TCP:8080 接收   |
+-----------------+     Ethernet (TCP)    |  WS:8081 推送    |
|    cw_wg        | --------------------->|  HTTP:3000 展示  |
|  STM32F103ZET6  |                       |                  |
|  W5500 以太网    |                       +------------------+
|  多传感器采集    |
+-----------------+
```

## 项目组成

| 模块 | 分支 | 说明 | 核心芯片 |
|------|------|------|----------|
| **cw_dinweiqi** (定位器) | `locator` | GPS 定位 + 计步 + NB-IoT 上报 | STM32F103C8T6 |
| **cw_wg** (网关) | `gateway` | 以太网数据转发 + 多传感器 | STM32F103ZET6 + W5500 |
| **cw_web** (监控平台) | `web` | 实时地图 + 数据展示 + 设备管理 | Node.js + Leaflet |

## 分支说明

- **`main`** -- 项目总览与系统架构
- **`locator`** -- 定位器模块文档 (cw_dinweiqi)
- **`gateway`** -- 网关模块文档 (cw_wg)
- **`web`** -- 监控平台文档 (cw_web)

## 快速开始

### 1. 定位器端 (cw_dinweiqi)

使用 STM32CubeMX 打开 `cw_dinweiqi.ioc`，配置后编译烧录。

```bash
cd cw_dinweiqi/MDK-ARM
# 使用 Keil MDK 编译
```

### 2. 网关端 (cw_wg)

```bash
cd cw_wg/MDK-ARM
# 使用 Keil MDK 编译
```

### 3. 监控平台 (cw_web)

```bash
cd cw_web
npm install
node server.js
# 访问 http://localhost:3002
```

## 硬件清单

| 组件 | 型号 | 用途 |
|------|------|------|
| 主控芯片 (定位器) | STM32F103C8T6 | 定位器主控 |
| 主控芯片 (网关) | STM32F103ZET6 | 网关主控 |
| NB-IoT 模块 | MN316 | 无线数据上报 |
| 以太网模块 | W5500 | 有线网络接入 |
| GPS 模块 | - | 定位信息采集 |
| 计步传感器 | ADXL345 | 运动计步 |

## 通信协议

定位器通过 NB-IoT 以 TCP 方式向服务器发送数据，网关通过 W5500 以太网接入。

数据格式详见各分支文档。

## 作者

**zouyuhang** -- [GitHub](https://github.com/zouyuhang233)

## 许可证

MIT License
