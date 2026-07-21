#ifndef __INT_W5500_H_
#define __INT_W5500_H_

#include "headfile.h"

 typedef enum {
    COMMON_OK = 0,
    COMMON_ERROR
} CommmonStatus;

extern void user_wizchip_reg_func(void);

//软重启
void Inf_W5500_Rest(void);
//初始化
void Inf_W5500_Init(void);

//socket启动一个客户端连接电脑服务端
CommmonStatus Int_W5500_Start_TCP_Client(void);

void Int_W5500_Send_Data(uint8_t data[], uint16_t data_len);

#endif
