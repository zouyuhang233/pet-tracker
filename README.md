# 秦楚网关模块 (cw_wg)

> **QinChu Gateway** -- 基于 STM32F103ZET6 + W5500 的智能数据网关

---

## 模块概述

网关是秦楚 IoT 系统的边缘计算节点，负责汇聚多个传感器数据，通过 W5500 以太网模块接入网络，将处理后的数据转发至云端监控平台。

## 硬件架构

```
+-------------------------------------------+
|              STM32F103ZET6 主控            |
|                                           |
|  SPI1  <---> W5500 以太网模块 (网络接入)  |
|  SPI2  <---> 扩展传感器                    |
|  USART1 <---> 调试串口 / 数据透传          |
|  GPIO  <---> W5500 复位控制 (PG6)          |
|                                           |
|  PA13/PA14 -- SWD 调试接口                |
|  PG6       -- W5500 硬件复位              |
+-------------------------------------------+
         |
         v Ethernet
+----------+        +----------+
| W5500    |        | 传感器组  |
| 以太网   |        | (SPI/UART)|
+----------+        +----------+
         |
         v TCP
+----------+
| 云服务器  |
| :8080    |
+----------+
```

## 功能特性

- 以太网接入 -- W5500 硬件 TCP/IP 协议栈
- 多传感器汇聚 -- SPI/UART 多路传感器数据采集
- 数据转发 -- 边缘预处理后上报云端
- 稳定可靠 -- 有线网络，不依赖无线信号
- 灵活配置 -- IP/MAC/网关可配置

## 软件架构

### 文件结构

```
cw_wg/
+-- APP/                    # 应用层
|   +-- int_w5500.c        # W5500 初始化与 TCP 客户端
|   +-- headfile.h
+-- BSP/                    # 板级支持包
|   +-- W5500/             # W5500 驱动
+-- Core/                   # STM32 HAL 核心
+-- Drivers/                # HAL 驱动库
+-- MDK-ARM/               # Keil 工程文件
+-- cw_wg.ioc              # STM32CubeMX 配置
```

### W5500 网络初始化 (int_w5500.c)

```c
uint8_t ip[4]  = {192, 168, 137, 100};  // 本机 IP
uint8_t ga[4]  = {192, 168, 137, 1};    // 网关地址
uint8_t sub[4] = {255, 255, 255, 0};    // 子网掩码
uint8_t mac[6] = {110, 120, 13, 140, 150, 16};

void Inf_W5500_Init(void)
{
    Inf_W5500_Rest();          // 1. 软重启芯片
    user_wizchip_reg_func();   // 2. 注册回调函数
    setGAR(ga);                // 3. 设置网关
    setSUBR(sub);              // 4. 设置子网掩码
    setSIPR(ip);               // 5. 设置 IP
    setSHAR(mac);              // 6. 设置 MAC
}
```

### TCP 客户端连接

```c
#define SN            0
#define CLIENT_PORT   9090
uint8_t SERVER_IP[4] = {8, 134, 127, 141};
#define SERVER_PORT   8080

CommmonStatus Int_W5500_Start_TCP_Client(void)
{
    uint8_t sn_sr = getSn_SR(SN);
    if (sn_sr == SOCK_CLOSED)
    {
        socket(SN, Sn_MR_TCP, CLIENT_PORT, 0);
        connect(SN, SERVER_IP, SERVER_PORT);
    }
}
```

## 网络配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| IP 地址 | 192.168.137.100 | 设备 IP |
| 网关 | 192.168.137.1 | 默认网关 |
| 子网掩码 | 255.255.255.0 | 子网掩码 |
| MAC 地址 | 6E:78:0D:8C:96:10 | 物理地址 |
| 服务器 | 8.134.127.141:8080 | 云平台地址 |

## STM32CubeMX 配置

| 参数 | 值 |
|------|-----|
| 芯片 | STM32F103ZET6 |
| 封装 | LQFP144 |
| SPI1 | W5500 以太网通信 |
| SPI2 | 扩展传感器接口 |
| USART1 | 调试串口 |

## 依赖关系

```
cw_wg (网关)
    |
    +---> cw_web (监控平台)  <-- TCP:8080
```

---

**分支**: `gateway` | **作者**: zouyuhang | **许可证**: MIT
