#include "MN316_TCP.h"
#include "usart.h"
#include <string.h>
#include <stdio.h>

// 全局变量
uint8_t tcp_socket_id = 0;
TCP_Status tcp_status = TCP_DISCONNECTED;

// 创建TCP Socket
// 返回: 0=成功, 1=失败
uint8_t MN316_TCP_CreateSocket(void)
{
    uint8_t res;
    char *colon_pos;
    char cmd[64];

    printf("\r\n[TCP] Creating socket...\r\n");

    // 先关闭已存在的Socket（不检查返回值，快速跳过）
    MN316_SendCmd("AT+NSOCL=0");
    MN316_WaitResponse("OK", 1000);
    HAL_Delay(100);

    // 创建socket: AT+NSOCR="STREAM",6,6008,2
    MN316_SendCmd("AT+NSOCR=\"STREAM\",6,6008,2");
    res = MN316_WaitResponse("+NSOCR:", 5000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);

    if (res == 0)
    {
        // 解析socket_id: +NSOCR:0
        colon_pos = strchr((char *)mn316_rx_buf, ':');
        if (colon_pos)
        {
            tcp_socket_id = *(colon_pos + 1) - '0';
            printf("    Socket ID: %d\r\n", tcp_socket_id);
            return 0;
        }
    }
    printf("    Create socket failed!\r\n");
    return 1;
}

// 连接TCP服务器
// ip: 服务器IP地址
// port: 服务器端口号
// 返回: 0=成功, 1=失败
uint8_t MN316_TCP_Connect(const char *ip, uint16_t port)
{
    uint8_t res;
    char cmd[128];

    printf("\r\n[TCP] Connecting to %s:%d...\r\n", ip, port);

    // 连接服务器: AT+NSOCO=socket_id,ip,port
    sprintf(cmd, "AT+NSOCO=%d,%s,%d", tcp_socket_id, ip, port);
    MN316_SendCmd(cmd);

    res = MN316_WaitResponse("OK", 10000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);

    if (res == 0)
    {
        tcp_status = TCP_CONNECTED;
        printf("    Connect OK!\r\n");

        // 配置数据格式: hex_output=0(接收字符串), input_mode=1(发送HEX)
        printf("\r\n[TCP] Config data format...\r\n");
        sprintf(cmd, "AT+NSOCFG=%d,0,1", tcp_socket_id);
        MN316_SendCmd(cmd);
        MN316_WaitResponse("OK", 3000);
        printf("    Raw: [%s]\r\n", mn316_rx_buf);

        return 0;
    }
    printf("    Connect failed!\r\n");
    return 1;
}

// 断开TCP连接
// 返回: 0=成功, 1=失败
uint8_t MN316_TCP_Disconnect(void)
{
    uint8_t res;
    char cmd[64];

    printf("\r\n[TCP] Disconnecting...\r\n");

    // 关闭socket: AT+NSOCL=socket_id
    sprintf(cmd, "AT+NSOCL=%d", tcp_socket_id);
    MN316_SendCmd(cmd);

    res = MN316_WaitResponse("OK", 5000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);

    if (res == 0)
    {
        tcp_status = TCP_DISCONNECTED;
        printf("    Disconnect OK!\r\n");
        return 0;
    }
    printf("    Disconnect failed!\r\n");
    return 1;
}

// 发送TCP数据（使用HEX模式，避免特殊字符问题）
// data: 要发送的数据
// len: 数据长度（原始字节数）
// 返回: 0=成功, 1=失败
uint8_t MN316_TCP_Send(const uint8_t *data, uint16_t len)
{
    uint8_t res;
    static char cmd[600];
    static char hex_buf[600];
    uint16_t i;

    printf("\r\n[TCP] Sending %d bytes (HEX mode)...\r\n", len);

    // 限制最大发送长度（hex_buf大小/2）
    if (len > 280) len = 280;

    // 将数据转换为HEX字符串
    for (i = 0; i < len; i++)
    {
        sprintf(&hex_buf[i * 2], "%02X", data[i]);
    }
    hex_buf[len * 2] = '\0';

    printf("    HEX: %s\r\n", hex_buf);

    // 发送HEX数据: AT+NSOSD=socket_id,length,hex_data
    // NSOCFG已设置为input_mode=1(发送HEX)，直接发送
    sprintf(cmd, "AT+NSOSD=%d,%d,%s", tcp_socket_id, len, hex_buf);
    MN316_SendCmd(cmd);

    // 等待响应
    res = MN316_WaitResponse("OK", 5000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);

    if (res == 0)
    {
        printf("    Send OK!\r\n");
        return 0;
    }

    printf("    Send failed!\r\n");
    return 1;
}

// 接收TCP数据
// buf: 接收缓冲区
// max_len: 缓冲区最大长度
// 返回: 实际接收的数据长度
uint16_t MN316_TCP_Receive(uint8_t *buf, uint16_t max_len)
{
    uint8_t res;
    char cmd[64];
    char *data_start;
    uint16_t data_len = 0;

    // 查询接收数据: AT+NSORF=socket_id,length
    sprintf(cmd, "AT+NSORF=%d,512", tcp_socket_id);
    MN316_SendCmd(cmd);

    res = MN316_WaitResponse("+NSORF:", 5000);

    if (res == 0)
    {
        // 解析数据: +NSORF:socket_id,length,data,remaining_length
        // 简化处理，直接复制缓冲区内容
        data_len = mn316_rx_len;
        if (data_len > max_len) data_len = max_len;
        memcpy(buf, mn316_rx_buf, data_len);
        buf[data_len] = '\0';
    }

    return data_len;
}

// TCP测试函数
void MN316_TCP_Test(void)
{
    uint8_t res;

    printf("\r\n========== MN316 TCP Test Start ==========\r\n");

    // 0. 先测试AT通信
    printf("\r\n[0] Test AT...\r\n");
    MN316_SendCmd("AT");
    res = MN316_WaitResponse("OK", 3000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);
    if (res == 0) printf("    OK!\r\n");
    else printf("    Failed (res=%d)\r\n", res);
    HAL_Delay(500);

    // 1. 关闭回显
    printf("\r\n[1] Disable echo...\r\n");
    MN316_SendCmd("ATE0");
    res = MN316_WaitResponse("OK", 3000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);
    if (res == 0) printf("    OK!\r\n");
    else printf("    Failed (res=%d)\r\n", res);
    HAL_Delay(500);

    // 2. 测试AT通信（关闭回显后）
    printf("\r\n[2] Test AT again...\r\n");
    MN316_SendCmd("AT");
    res = MN316_WaitResponse("OK", 3000);
    printf("    Raw: [%s]\r\n", mn316_rx_buf);
    if (res == 0) printf("    OK!\r\n");
    else printf("    Failed (res=%d)\r\n", res);
    HAL_Delay(500);

    // 3. 创建Socket
    printf("\r\n[3] Create Socket...\r\n");
    res = MN316_TCP_CreateSocket();
    if (res != 0)
    {
        printf("    Failed! Stop.\r\n");
        return;
    }
    HAL_Delay(1000);

    // 4. 连接服务器（阿里云）
    printf("\r\n[4] Connect Server...\r\n");
    res = MN316_TCP_Connect("8.134.127.141", 8080);
    if (res != 0)
    {
        printf("    Failed! Stop.\r\n");
        return;
    }
    HAL_Delay(1000);

    // 5. 发送测试数据
    printf("\r\n[5] Send Data...\r\n");
    char test_data[] = "Hello from MN316 TCP Client!";
    res = MN316_TCP_Send((uint8_t *)test_data, strlen(test_data));
    if (res != 0)
    {
        printf("    Failed!\r\n");
    }
    HAL_Delay(2000);

    // 6. 尝试接收数据
    printf("\r\n[6] Receive Data...\r\n");
    uint8_t rx_buf[256];
    uint16_t rx_len;

    memset(rx_buf, 0, sizeof(rx_buf));
    rx_len = MN316_TCP_Receive(rx_buf, sizeof(rx_buf));

    if (rx_len > 0)
    {
        printf("    Received %d bytes: %s\r\n", rx_len, rx_buf);
    }
    else
    {
        printf("    No data received.\r\n");
    }

    // 7. 断开连接
    printf("\r\n[7] Disconnect...\r\n");
    MN316_TCP_Disconnect();

    printf("\r\n========== MN316 TCP Test End ==========\r\n");
}
