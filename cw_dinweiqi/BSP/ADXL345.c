/**
 * ADXL345加速度传感器驱动（I2C）
 * 功能：读取三轴加速度，实现计步检测
 */
#include "adxl345.h"
#include <math.h>

static uint32_t step_count = 0;        // 步数计数
static uint32_t last_step_time = 0;    // 上次步伐时间

// I2C写一个字节
static void ADXL345_WriteByte(uint8_t reg, uint8_t data)
{
    HAL_I2C_Mem_Write(&hi2c1, ADXL345_ADDR_WRITE, reg,
                      I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
}

// I2C读一个字节
static uint8_t ADXL345_ReadByte(uint8_t reg)
{
    uint8_t data;
    HAL_I2C_Mem_Read(&hi2c1, ADXL345_ADDR_READ, reg,
                     I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
    return data;
}

// I2C连续读取
static void ADXL345_ReadBytes(uint8_t reg, uint8_t *buf, uint8_t len)
{
    HAL_I2C_Mem_Read(&hi2c1, ADXL345_ADDR_READ, reg,
                     I2C_MEMADD_SIZE_8BIT, buf, len, 100);
}

// 初始化
void ADXL345_Init(void)
{
    HAL_Delay(100);

    // 验证ID（应为0xE5）
    if (ADXL345_ReadID() != 0xE5)
    {
        debug_println("ADXL345 Not Found!");
        return;  // 没找到就返回，不卡死
    }

    ADXL345_WriteByte(0x31, 0x0B);  // ±16g，全分辨率
    ADXL345_WriteByte(0x2C, 0x0A);  // 100Hz数据速率
    ADXL345_WriteByte(0x2D, 0x08);  // 测量模式
    ADXL345_WriteByte(0x1E, 0x00);  // X偏移
    ADXL345_WriteByte(0x1F, 0x00);  // Y偏移
    ADXL345_WriteByte(0x20, 0x05);  // Z偏移

    debug_println("ADXL345 Init OK");
}

// 读取器件ID
uint8_t ADXL345_ReadID(void)
{
    return ADXL345_ReadByte(ADXL345_DEVID);
}

// 读取三轴加速度（单位：g）
void ADXL345_ReadXYZ(float *x, float *y, float *z)
{
    uint8_t buf[6];
    ADXL345_ReadBytes(ADXL345_DATAX0, buf, 6);

    int16_t raw_x = (int16_t)((buf[1] << 8) | buf[0]);
    int16_t raw_y = (int16_t)((buf[3] << 8) | buf[2]);
    int16_t raw_z = (int16_t)((buf[5] << 8) | buf[4]);

    *x = (float)raw_x * 3.9f / 1000.0f;  // 3.9mg/LSB
    *y = (float)raw_y * 3.9f / 1000.0f;
    *z = (float)raw_z * 3.9f / 1000.0f;
}

// 获取总加速度（去掉重力）
static float ADXL345_GetTotalAcc(void)
{
    float x, y, z;
    ADXL345_ReadXYZ(&x, &y, &z);
    float total = sqrt(x * x + y * y + z * z) - 1.0f;
    return (total < 0) ? -total : total;
}

// 计步检测（摇晃检测，更简单）
void ADXL345_StepDetect(void)
{
    float acc = ADXL345_GetTotalAcc();
    uint32_t now = HAL_GetTick();

    // 只要超过阈值就计数（间隔足够）
    if (acc >= STEP_THRESHOLD && (now - last_step_time) > STEP_MIN_GAP)
    {
        step_count++;
        last_step_time = now;

     printf("step%d\n",step_count);
    }
}

// 获取当前步数
uint32_t ADXL345_GetStepCount(void)
{
    return step_count;
}
