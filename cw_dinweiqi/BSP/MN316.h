#ifndef __MN316_H
#define __MN316_H

#include "main.h"
#include <string.h>
#include <stdio.h>

// 接收缓冲区大小
#define MN316_RX_BUF_SIZE  512

// 全局变量声明
extern UART_HandleTypeDef huart3;
extern uint8_t mn316_rx_buf[MN316_RX_BUF_SIZE];
extern volatile uint16_t mn316_rx_len;
extern volatile uint8_t mn316_rx_flag;
extern uint8_t mn316_byte;

// 函数声明
void MN316_Init(void);
void MN316_SendCmd(const char *cmd);
uint8_t MN316_WaitResponse(const char *expected, uint16_t timeout_ms);
void MN316_Test(void);

#endif
