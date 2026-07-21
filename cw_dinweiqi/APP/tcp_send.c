#include "tcp_send.h"
#include "MN316_TCP.h"
#include "INT_AT6558R.h"
#include "ADXL345.h"
#include <stdlib.h>

// 全局变量
uint32_t tcp_last_send_time = 0;
uint32_t tcp_last_reconnect_time = 0;
uint8_t  tcp_connected = 0;
uint8_t  tcp_socket_created = 0;

// 可靠的字符串转浮点数
static float parse_float(const char *s)
{
    float result = 0.0f;
    float sign = 1.0f;
    float decimal = 0.1f;

    if (!s || !*s) return 0.0f;

    if (*s == '-') { sign = -1.0f; s++; }
    else if (*s == '+') { s++; }

    while (*s >= '0' && *s <= '9')
    {
        result = result * 10.0f + (*s - '0');
        s++;
    }

    if (*s == '.')
    {
        s++;
        while (*s >= '0' && *s <= '9')
        {
            result += (*s - '0') * decimal;
            decimal *= 0.1f;
            s++;
        }
    }

    return sign * result;
}

// GPS 数据缓冲区
static char last_gga_sentence[128] = {0};
static uint8_t gga_updated = 0;

// 服务器配置
#define SERVER_IP     "8.134.127.141"
#define SERVER_PORT   8080

/**
 * 初始化 TCP 发送任务
 */
void TCP_Send_Init(void)
{
    printf("[TCP_Send] 初始化...\r\n");
    tcp_last_send_time = HAL_GetTick();
    tcp_connected = 0;
    tcp_socket_created = 0;

    TCP_Send_Reconnect();
}

/**
 * TCP 发送主任务（保持连接 + 心跳）
 */
void TCP_Send_Task(void)
{
    uint32_t now = HAL_GetTick();

    // 断开则立即重连
    if (!tcp_connected)
    {
        printf("[TCP_Send] 连接断开，立即重连...\r\n");
        TCP_Send_Reconnect();
        return;
    }

    // 每3秒发心跳
    static uint32_t last_heartbeat_time = 0;
    if ((now - last_heartbeat_time) >= TCP_HEARTBEAT_INTERVAL)
    {
        last_heartbeat_time = now;
        uint8_t heart_res = TCP_Send_Heartbeat();
        if (heart_res != 0)
        {
            printf("[TCP_Send] 心跳失败，准备重连\r\n");
            tcp_connected = 0;
            return;
        }
    }

    // 每10秒发数据
    if ((now - tcp_last_send_time) < TCP_SEND_INTERVAL)
    {
        return;
    }
    tcp_last_send_time = now;

    uint8_t gps_res = TCP_Send_GPS_Step();
    if (gps_res != 0)
    {
        printf("[TCP_Send] GPS发送失败，可能连接断开\r\n");
        tcp_connected = 0;
        return;
    }

    // 每5秒发状态（和GPS同步）
    static uint32_t last_status_time = 0;
    if ((now - last_status_time) >= TCP_SEND_INTERVAL)
    {
        TCP_Send_Status();
        last_status_time = now;
    }
}

/**
 * 重连 TCP（完全重新初始化）
 */
void TCP_Send_Reconnect(void)
{
    uint8_t res;
    int retry = 0;

    printf("[TCP_Send] ===== 开始重新初始化 =====\r\n");

    // 1. 关闭旧Socket
    printf("[TCP_Send] 1. 关闭旧Socket...\r\n");
    MN316_SendCmd("AT+NSOCL=0");
    MN316_WaitResponse("OK", 2000);
    MN316_SendCmd("AT+NSOCL=1");
    MN316_WaitResponse("OK", 1000);
    tcp_socket_created = 0;
    tcp_connected = 0;
    HAL_Delay(1000);

    // 2. 检查模块
    printf("[TCP_Send] 2. 检查模块...\r\n");
    MN316_SendCmd("AT");
    res = MN316_WaitResponse("OK", 3000);
    if (res != 0)
    {
        printf("[TCP_Send] 模块无响应，重启模块(AT+NRB)...\r\n");
        MN316_SendCmd("AT+NRB");
        HAL_Delay(30000);
        MN316_Init();
        HAL_Delay(5000);
    }

    // 3. 清理Socket
    printf("[TCP_Send] 3. 清理Socket...\r\n");
    MN316_SendCmd("AT+NSOCL=0");
    MN316_WaitResponse("OK", 2000);
    HAL_Delay(1000);

    // 4. 等待网络注册
    printf("[TCP_Send] 4. 等待网络注册...\r\n");
    for (retry = 0; retry < 30; retry++)
    {
        memset(mn316_rx_buf, 0, MN316_RX_BUF_SIZE);
        mn316_rx_len = 0;
        MN316_SendCmd("AT+CEREG?");
        res = MN316_WaitResponse("+CEREG:", 3000);
        printf("    [%d] CEREG: %s\r\n", retry + 1, mn316_rx_buf);

        if (strstr((char *)mn316_rx_buf, ",1") || strstr((char *)mn316_rx_buf, ",5"))
        {
            printf("[TCP_Send] 网络已注册！\r\n");
            break;
        }

        if ((retry + 1) % 5 == 0)
        {
            printf("[TCP_Send] 重启模块(AT+NRB)...\r\n");
            MN316_SendCmd("AT+NRB");
            HAL_Delay(30000);
            MN316_Init();
            HAL_Delay(5000);
        }
        HAL_Delay(3000);
    }

    if (retry >= 30)
    {
        printf("[TCP_Send] 网络注册超时\r\n");
        return;
    }

    HAL_Delay(2000);

    // 5. 创建Socket
    printf("[TCP_Send] 5. 创建Socket...\r\n");
    res = MN316_TCP_CreateSocket();
    if (res != 0)
    {
        printf("[TCP_Send] 创建Socket失败\r\n");
        return;
    }
    tcp_socket_created = 1;
    HAL_Delay(500);

    // 6. 连接服务器
    printf("[TCP_Send] 6. 连接服务器 %s:%d...\r\n", SERVER_IP, SERVER_PORT);
    res = MN316_TCP_Connect(SERVER_IP, SERVER_PORT);
    if (res != 0)
    {
        printf("[TCP_Send] 连接服务器失败\r\n");
        tcp_connected = 0;
        return;
    }

    // 7. 配置数据格式
    printf("[TCP_Send] 7. 配置数据格式...\r\n");
    char cmd[32];
    sprintf(cmd, "AT+NSOCFG=%d,0,1", tcp_socket_id);
    MN316_SendCmd(cmd);
    MN316_WaitResponse("OK", 3000);

    tcp_connected = 1;
    printf("[TCP_Send] ===== 重新连接成功！ =====\r\n");
}

/**
 * 发送 GPS+步数 数据
 */
uint8_t TCP_Send_GPS_Step(void)
{
    if (!tcp_connected) return 1;

    printf("[TCP_Send] 发送 GPS+步数 数据...\r\n");

    float latitude = 0, longitude = 0, altitude = 0;
    int fix_quality = 0, satellites = 0;
    char lat_dir = 'N', lon_dir = 'E';

    char *gga = strstr(last_gga_sentence, "$GNGGA");
    if (gga)
    {
        char fields[12][16];
        int field = 0, pos = 0;
        char *p = gga;

        while (*p && *p != ',') p++;
        if (*p == ',') p++;

        while (*p && *p != '*' && field < 12)
        {
            pos = 0;
            while (*p && *p != ',' && *p != '*' && pos < 15)
            {
                fields[field][pos++] = *p++;
            }
            fields[field][pos] = '\0';
            field++;
            if (*p == ',') p++;
        }

        printf("[GGA] f0=%s f1=%s f2=%s f3=%s f4=%s f5=%s f6=%s f8=%s\r\n",
               fields[0], fields[1], fields[2], fields[3], fields[4], fields[5], fields[6], fields[8]);
        if (field >= 9)
        {
            fix_quality = atoi(fields[5]);
            satellites = atoi(fields[6]);
            lat_dir = fields[2][0];
            lon_dir = fields[4][0];
            altitude = parse_float(fields[8]);

            if (strlen(fields[1]) >= 4)
            {
                int lat_dd = (fields[1][0] - '0') * 10 + (fields[1][1] - '0');
                float lat_mm = parse_float(fields[1] + 2);
                latitude = lat_dd + lat_mm / 60.0f;
                if (lat_dir == 'S') latitude = -latitude;
            }

            if (strlen(fields[3]) >= 5)
            {
                int lon_ddd = (fields[3][0] - '0') * 100 + (fields[3][1] - '0') * 10 + (fields[3][2] - '0');
                float lon_mm = parse_float(fields[3] + 3);
                longitude = lon_ddd + lon_mm / 60.0f;
                if (lon_dir == 'W') longitude = -longitude;
            }
        }
    }

    uint32_t steps = ADXL345_GetStepCount();

    printf("[GPS_Parse] lat=%.6f lon=%.6f fix=%d sat=%d\r\n",
           latitude, longitude, fix_quality, satellites);

    char send_buf[256];
    sprintf(send_buf,
        "{type:data,"
        "lat:%.6f,"
        "lon:%.6f,"
        "alt:%.1f,"
        "fix:%d,"
        "sat:%d,"
        "steps:%lu,"
        "time:%lu}",
        latitude, longitude, altitude,
        fix_quality, satellites,
        steps, HAL_GetTick() / 1000);

    uint8_t res = MN316_TCP_Send((uint8_t*)send_buf, strlen(send_buf));
    if (res != 0)
    {
        printf("[TCP_Send] 数据发送失败\r\n");
        return 1;
    }

    printf("[TCP_Send] 数据发送成功: lat=%.6f lon=%.6f steps=%lu\r\n", latitude, longitude, steps);
    gga_updated = 0;
    return 0;
}

/**
 * 发送设备状态信息
 */
uint8_t TCP_Send_Status(void)
{
    if (!tcp_connected) return 1;

    printf("[TCP_Send] 发送状态信息...\r\n");

    int8_t rssi = 0;
    uint8_t signal_quality = 0;

    MN316_SendCmd("AT+CSQ");
    uint8_t res = MN316_WaitResponse("+CSQ:", 3000);
    if (res == 0)
    {
        char *comma = strchr((char*)mn316_rx_buf, ':');
        if (comma)
        {
            int rssi_val = atoi(comma + 1);
            if (rssi_val != 99)
            {
                rssi = -113 + rssi_val * 2;
                signal_quality = rssi_val * 100 / 31;
            }
        }
    }

    char send_buf[256];
    sprintf(send_buf,
        "{type:status,"
        "signal:%d,"
        "rssi:%d,"
        "steps:%lu,"
        "uptime:%lu,"
        "battery:80,"
        "deviceName:NB-IoT}",
        signal_quality, rssi,
        ADXL345_GetStepCount(),
        HAL_GetTick() / 1000);

    res = MN316_TCP_Send((uint8_t*)send_buf, strlen(send_buf));
    if (res != 0)
    {
        printf("[TCP_Send] 状态信息发送失败\r\n");
        return 1;
    }

    printf("[TCP_Send] 状态信息发送成功\r\n");
    return 0;
}

/**
 * 发送心跳包
 */
uint8_t TCP_Send_Heartbeat(void)
{
    if (!tcp_connected) return 1;

    char heartbeat[] = "{type:ping}";
    printf("[TCP] 发送心跳... (%lu秒)\r\n", HAL_GetTick() / 1000);
    uint8_t res = MN316_TCP_Send((uint8_t*)heartbeat, strlen(heartbeat));
    if (res == 0)
    {
        printf("[TCP] 心跳发送成功\r\n");
        return 0;
    }

    printf("[TCP] 心跳发送失败\r\n");
    tcp_connected = 0;
    return 1;
}

/**
 * 保存最新的 GGA 句子
 */
void TCP_Send_Save_GGA(const char *gga_sentence)
{
    strncpy(last_gga_sentence, gga_sentence, sizeof(last_gga_sentence) - 1);
    last_gga_sentence[sizeof(last_gga_sentence) - 1] = '\0';
    gga_updated = 1;
}

/**
 * 检查 TCP 连接状态
 */
uint8_t TCP_Send_IsConnected(void)
{
    return tcp_connected;
}
