/**
 * ADXL345加速度传感器头文件
 */
#ifndef __ADXL345_H
#define __ADXL345_H
#include "headfile.h"

// I2C地址
#define ADXL345_ADDR            0x53
#define ADXL345_ADDR_WRITE      0xA6
#define ADXL345_ADDR_READ       0xA7

// 寄存器地址
#define ADXL345_DEVID           0x00    // 器件ID
#define ADXL345_OFSX            0x1E    // X偏移
#define ADXL345_OFSY            0x1F    // Y偏移
#define ADXL345_OFSZ            0x20    // Z偏移
#define ADXL345_BW_RATE         0x2C    // 数据速率
#define ADXL345_POWER_CTL       0x2D    // 电源控制
#define ADXL345_DATA_FORMAT     0x31    // 数据格式
#define ADXL345_DATAX0          0x32    // 数据寄存器

// 计步参数
#define STEP_THRESHOLD          0.3f    // 摇晃阈值(g)，很灵敏
#define STEP_MIN_GAP            300     // 最小间隔(ms)

// 函数声明
void ADXL345_Init(void);                // 初始化
uint8_t ADXL345_ReadID(void);           // 读取ID
void ADXL345_ReadXYZ(float *x, float *y, float *z);  // 读取加速度
void ADXL345_StepDetect(void);          // 计步检测
uint32_t ADXL345_GetStepCount(void);    // 获取步数

#endif
