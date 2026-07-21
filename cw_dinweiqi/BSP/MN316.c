#include "MN316.h"
#include "usart.h"
#include <string.h>
#include <stdio.h>

// 接收缓冲区
uint8_t mn316_rx_buf[MN316_RX_BUF_SIZE];
volatile uint16_t mn316_rx_len = 0;
volatile uint8_t mn316_rx_flag = 0;

// USART3接收中断回调
uint8_t mn316_byte;

// 初始化MN316
void MN316_Init(void)
{
    // 开启USART3接收中断
    HAL_UART_Receive_IT(&huart3, &mn316_byte, 1);
    printf("[MN316] Init OK, using USART3 (PB10/PB11) @ 9600\r\n");
}

// 发送AT命令
void MN316_SendCmd(const char *cmd)
{
    // 关闭接收中断
    HAL_UART_AbortReceive_IT(&huart3);

    // 清空缓冲区
    memset(mn316_rx_buf, 0, MN316_RX_BUF_SIZE);
    mn316_rx_len = 0;
    mn316_rx_flag = 0;

    // 先开启接收中断，再发送命令（防止丢失响应）
    HAL_UART_Receive_IT(&huart3, &mn316_byte, 1);

    // 发送命令
    printf("[TX] %s\r\n", cmd);
    HAL_UART_Transmit(&huart3, (uint8_t *)cmd, strlen(cmd), 1000);
    HAL_UART_Transmit(&huart3, (uint8_t *)"\r\n", 2, 100);
}

// 等待响应（等待数据稳定后返回）
uint8_t MN316_WaitResponse(const char *expected, uint16_t timeout_ms)
{
    uint16_t start = HAL_GetTick();
    uint16_t last_len = 0;
    uint16_t stable_count = 0;

    while ((HAL_GetTick() - start) < timeout_ms)
    {
        if (mn316_rx_len > 0 && mn316_rx_len == last_len)
        {
            stable_count++;
            // 500ms内没有新数据，认为接收完成
            if (stable_count > 50)
            {
                mn316_rx_buf[mn316_rx_len] = '\0';
                printf("[RX] %s\r\n", mn316_rx_buf);

                if (strstr((char *)mn316_rx_buf, expected))
                {
                    return 0;
                }
                return 1;
            }
        }
        else
        {
            stable_count = 0;
            last_len = mn316_rx_len;
        }
        HAL_Delay(10);
    }

    // 超时
    if (mn316_rx_len > 0)
    {
        mn316_rx_buf[mn316_rx_len] = '\0';
        printf("[RX timeout] %s\r\n", mn316_rx_buf);
    }
    return 2;
}

// USART3中断回调函数 - 尽量简短
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART3)
    {
        mn316_rx_buf[mn316_rx_len++] = mn316_byte;
        if (mn316_rx_len >= MN316_RX_BUF_SIZE)
        {
            mn316_rx_len = MN316_RX_BUF_SIZE - 1;
        }
        mn316_rx_flag = 1;
        // 立即重新开启接收
        HAL_UART_Receive_IT(&huart3, &mn316_byte, 1);
    }
}

// MN316测试函数
void MN316_Test(void)
{
    uint8_t res;

    printf("\r\n========== MN316 Test Start ==========\r\n");

    printf("\r\n[1] Test AT...\r\n");
    MN316_SendCmd("AT");
    res = MN316_WaitResponse("OK", 3000);
    if (res == 0) printf("    Result: OK!\r\n");
    else printf("    Result: Failed (res=%d)\r\n", res);

    HAL_Delay(300);

    printf("\r\n[2] ATI...\r\n");
    MN316_SendCmd("ATI");
    res = MN316_WaitResponse("OK", 3000);
    if (res == 0) printf("    Result: OK!\r\n");
    else printf("    Result: Failed (res=%d)\r\n", res);

    HAL_Delay(300);

    printf("\r\n[3] AT+CPIN?...\r\n");
    MN316_SendCmd("AT+CPIN?");
    res = MN316_WaitResponse("OK", 3000);
    if (res == 0) printf("    Result: OK!\r\n");
    else printf("    Result: Failed (res=%d)\r\n", res);

    HAL_Delay(300);

    printf("\r\n[4] AT+CSQ...\r\n");
    MN316_SendCmd("AT+CSQ");
    res = MN316_WaitResponse("OK", 3000);
    if (res == 0) printf("    Result: OK!\r\n");
    else printf("    Result: Failed (res=%d)\r\n", res);

    HAL_Delay(300);

    printf("\r\n[5] AT+CEREG?...\r\n");
    MN316_SendCmd("AT+CEREG?");
    res = MN316_WaitResponse("OK", 3000);
    if (res == 0) printf("    Result: OK!\r\n");
    else printf("    Result: Failed (res=%d)\r\n", res);

    printf("\r\n========== MN316 Test End ==========\r\n");
}
