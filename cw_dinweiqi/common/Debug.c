#include "headfile.h"

//日志初始化
void Debug_init(void){

}

int fputc(int ch,FILE *file){
	HAL_UART_Transmit(&huart1,(uint8_t*)&ch,1,1000);
	return ch;
}
