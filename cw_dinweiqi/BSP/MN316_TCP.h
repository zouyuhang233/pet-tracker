#ifndef __MN316_TCP_H
#define __MN316_TCP_H

#include "MN316.h"

// TCP连接状态
typedef enum {
    TCP_DISCONNECTED = 0,
    TCP_CONNECTED
} TCP_Status;

// 全局变量
extern uint8_t tcp_socket_id;
extern TCP_Status tcp_status;

// 函数声明
uint8_t MN316_TCP_CreateSocket(void);
uint8_t MN316_TCP_Connect(const char *ip, uint16_t port);
uint8_t MN316_TCP_Disconnect(void);
uint8_t MN316_TCP_Send(const uint8_t *data, uint16_t len);
uint16_t MN316_TCP_Receive(uint8_t *buf, uint16_t max_len);
void MN316_TCP_Test(void);

#endif
