#include "headfile.h"

uint8_t ip[4] = {192,168,137,100};//给单片机分配的物理地址(ICS网段)
uint8_t ga[4] = {192,168,137,1};//网关地址(PC的ICS地址)
uint8_t sub[4] = {255,255,255,0};//子网掩码
uint8_t mac[6] = {110,120,13,140,150,16};
//软重启
void Inf_W5500_Rest(void){
HAL_GPIO_WritePin(GPIOG,GPIO_PIN_6,GPIO_PIN_RESET);
HAL_Delay(5);
HAL_GPIO_WritePin(GPIOG,GPIO_PIN_6,GPIO_PIN_SET);
HAL_Delay(5);
}

//初始化
void Inf_W5500_Init(void){
//1.软重启芯片
Inf_W5500_Rest();

//2.注册函数
user_wizchip_reg_func();

//3.设置w5500参数，ip,mac，网关，子网掩码
setGAR(ga);
setSUBR(sub);
setSIPR(ip);
setSHAR(mac);

char text[30];
sprintf(text,"ok");
HAL_UART_Transmit(&huart1,(uint8_t*)text,strlen(text),1000);

}

// 选择使用的socket 0~7
#define SN 0
#define CLIENT_PORT 9090
uint8_t SERVER_IP[4] = {8,134,127,141};
#define SERVER_PORT 8080
CommmonStatus Int_W5500_Start_TCP_Client(void){


    // 0. 判断当前的状态
    uint8_t sn_sr = getSn_SR(SN);
    // 1. 创建客户端
    if (sn_sr == SOCK_CLOSED)
    {
        // 资源被释放 能够用来创建客户端
        int8_t r = socket(SN,Sn_MR_TCP,CLIENT_PORT,0);
        if (r == SN)
        {
            // 创建socket成功 初始化客户端成功
            
        }
        else
        {
            //失败
        }
    }

    // 2. 连接服务端
else if (sn_sr == SOCK_INIT)
{
    // 主动连接服务端
    int8_t c_r = connect(SN, SERVER_IP, SERVER_PORT);
    if (c_r == SOCK_OK)
    {
       // debug_println("连接服务端成功");
    }
    else
    {
        //debug_println("连接服务端失败");
    }
}
// 3. 等待进入ES状态
else if (sn_sr == SOCK_ESTABLISHED)
{
    // 创建客户端成功
return COMMON_OK;
}else if (sn_sr == SOCK_CLOSE_WAIT)
{
    // 断开连接
    close(SN);
}
return COMMON_ERROR;

}

//发送数据方法
void Int_W5500_Send_Data(uint8_t data[], uint16_t data_len)
{
    // 健壮性判断
    if (data_len == 0)
    {
        return;
    }

    // 创建客户端等待连接服务端成功 => 才能发送数据
    while (Int_W5500_Start_TCP_Client() != COMMON_OK)
    {
        HAL_Delay(10);
    }

    // 只有当前SN的状态为ES的时候 才能发送数据
    // 0. 判断当前的状态
    uint8_t sn_sr = getSn_SR(SN);
    if (sn_sr == SOCK_ESTABLISHED)
    {
        // 才能发送数据
        send(SN, data, data_len);
    }
}
