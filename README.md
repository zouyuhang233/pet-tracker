# 秦楚定位器模块 (cw_dinweiqi)

> **QinChu Locator** -- 基于 STM32F103C8T6 + MN316 NB-IoT 的智能定位器

---

## 模块概述

定位器是秦楚 IoT 系统的核心终端设备，负责 GPS 定位信息采集、运动计步检测，并通过 NB-IoT 网络将数据实时上报至云端监控平台。

## 硬件架构

```
+-------------------------------------------+
|              STM32F103C8T6 主控            |
|                                           |
|  USART1 <---> MN316 NB-IoT (AT 命令通信) |
|  USART2 <---> GPS 模块 (NMEA 数据接收)   |
|  I2C1   <---> ADXL345 三轴加速度计        |
|  GPIO   <---> LED 状态指示 / 按键         |
|                                           |
|  PA13/PA14 -- SWD 调试接口                |
+-------------------------------------------+
         |                    |
         v                    v
   +----------+        +----------+
   | MN316    |        | ADXL345  |
   | NB-IoT   |        | 加速度计  |
   +----------+        +----------+
         |
         v TCP
   +----------+
   | 云服务器  |
   | :8080    |
   +----------+
```

## 功能特性

- GPS 定位 -- 实时接收 NMEA 0183 格式定位数据
- 智能计步 -- ADXL345 加速度计实现运动计步
- NB-IoT 上报 -- MN316 模块 TCP 方式无线数据传输
- 断线重连 -- 自动检测连接状态并重连
- 低功耗 -- 支持休眠模式延长续航

## 软件架构

### 文件结构

```
cw_dinweiqi/
+-- APP/                    # 应用层
|   +-- fun.c              # 主业务逻辑 (GPS/计步/上报)
|   +-- tcp_send.c         # TCP 发送任务
|   +-- headfile.h         # 头文件汇总
+-- BSP/                    # 板级支持包
|   +-- MN316/             # NB-IoT 模块驱动
|   +-- GPS/               # GPS 解析驱动
|   +-- ADXL345/           # 加速度计驱动
+-- Core/                   # STM32 HAL 核心
+-- Drivers/                # HAL 驱动库
+-- MDK-ARM/               # Keil 工程文件
+-- cw_dinweiqi.ioc        # STM32CubeMX 配置
```

### 核心代码 (fun.c)

```c
void main_pros(void)
{
    adxl345_pros();      // 计步检测
    uart2_pros_gps();    // GPS 数据处理
    uart1_pros();        // 串口通信
    TCP_Send_Task();     // TCP 数据上报
}
```

### MN316 NB-IoT 通信

```c
// 1. 创建 Socket
MN316_SendCmd("AT+NSOCR=\"STREAM\",6,6008,2");
// 2. 连接服务器
MN316_SendCmd("AT+NSOCO=0,8.134.127.141,8080");
// 3. 发送数据
MN316_SendCmd("AT+NSOSD=0,length,data");
```

### 数据格式

```
$GNGGA,014845.00,2233.1234,N,11357.5678,E,1,08,1.2,45.6,M,0.0,M,,*6A
STEP:42
STATUS:Battery=85%,Signal=23,RSSI=-67
```

## STM32CubeMX 配置

| 参数 | 值 |
|------|-----|
| 芯片 | STM32F103C8T6 |
| 封装 | LQFP48 |
| USART1 | MN316 通信 |
| USART2 | GPS 数据接收 |
| I2C1 | ADXL345 加速度计 |

## 依赖关系

```
cw_dinweiqi (定位器)
    |
    +---> cw_web (监控平台)  <-- TCP:8080
    |
    +-- cw_wg (网关)        <-- 独立设备
```

---

**分支**: `locator` | **作者**: zouyuhang | **许可证**: MIT
