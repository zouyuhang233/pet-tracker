#ifndef __INT_AT6558R_H
#define __INT_AT6558R_H
#include "headfile.h"
//gps初始化
void INT_AT6558R_Init(void);
//gps接收一次数据（阻塞）
void INT_AT6558R_Read(void);
//gps非阻塞处理（主循环调用）
void gps_pros(void);

#endif