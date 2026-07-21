#ifndef __TCP_SEND_H
#define __TCP_SEND_H

#include "headfile.h"

// TCP 发送配置
#define TCP_SEND_INTERVAL    5000    // 数据发送间隔（毫秒）- 5秒
#define TCP_HEARTBEAT_INTERVAL 3000  // 心跳间隔（毫秒）- 3秒防模块超时
#define TCP_RECONNECT_DELAY  10000   // 重连延迟（毫秒）

// 全局变量
extern uint32_t tcp_last_send_time;
extern uint32_t tcp_last_reconnect_time;
extern uint8_t  tcp_connected;
extern uint8_t  tcp_socket_created;

// 函数声明
void TCP_Send_Init(void);
void TCP_Send_Task(void);
void TCP_Send_Reconnect(void);
uint8_t TCP_Send_GPS_Step(void);
uint8_t TCP_Send_Status(void);
uint8_t TCP_Send_Heartbeat(void);
void TCP_Send_Save_GGA(const char *gga_sentence);
uint8_t TCP_Send_IsConnected(void);

#endif
