#include "headfile.h"

void Com_Delay_us(uint16_t us){
uint16_t temp=(us*72)/9;

while(temp--){
   __NOP();
   __NOP();
 }
}

void Com_Delay_ms(uint16_t ms){
HAL_Delay(ms);
}

void Com_Delay_s(uint16_t s){
while(s--){
HAL_Delay(1000);
}
}