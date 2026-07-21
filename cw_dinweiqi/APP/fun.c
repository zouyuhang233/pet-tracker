#include "headfile.h"

char uart1_rx[256];

void uart1_pros(void)
{
}

void uart2_pros_gps(void)
{
    gps_pros();
}

void adxl345_pros(void)
{
    ADXL345_StepDetect();
}

void main_pros(void)
{
    adxl345_pros();
    uart2_pros_gps();
    uart1_pros();
    TCP_Send_Task();
}

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart->Instance == USART1) {
    }
}
