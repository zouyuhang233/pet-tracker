#include "headfile.h"
//var
uint8_t gps_buff[512];
uint16_t gps_buff_len=0;
#define AT6558R_FREQ "PCAS02,1000"
#define AT6558R_MODE "PCAS04,3"

uint8_t gps_full_buff[1024];
uint16_t gps_full_buff_len=0;
#define GPS_BUFF_MAX_LEN 1024

uint8_t send_cmd[64];
void INT_AT6558R_Send_Cmd(uint8_t *cmd){
//计算校验和-所有字节异或结果
uint8_t temp=cmd[0];
for(int i=1;cmd[i]!='\0';i++){
temp^=cmd[i];
}
//拼接发送命令

// 拼接发送的名称 => 拼接校验和的细节 8和08不一样  1A 和 1a不一样
sprintf((char *)send_cmd, "$%s*%02X\r\n", cmd, temp);

HAL_UART_Transmit(&huart2, send_cmd, strlen((char *)send_cmd), 10000);
debug_println("%s",send_cmd);
}


//gps初始化
void INT_AT6558R_Init(void){
//初始化底层驱动
//1.设置刷新率
INT_AT6558R_Send_Cmd(AT6558R_FREQ);

//2.设置模式
INT_AT6558R_Send_Cmd(AT6558R_MODE);

//3.查询产品信息


}


//gps接收
void INT_AT6558R_Read(void){
	uint16_t timeout = 0;  // 超时计数器

//一直接收数据，直到数据完整，保护GGA,TXT,如果中断就拼接2次接收的数据
// 一直接收数据 => 直到数据完整包含GGA和TXT，如果接收数据中间出现中断 => 拼接两次接收的数据
	memset(gps_full_buff, 0, GPS_BUFF_MAX_LEN);
	gps_full_buff_len = 0;

while (1)
{
	// 判断数据接收完整（需要同时包含GGA和TXT）
	if (strstr((char *)gps_full_buff, "GGA") != NULL &&
		strstr((char *)gps_full_buff, "TXT") != NULL)
	{
		// 当前一次接收数据完整
		break;
	}

	// 超时保护：最多等待5秒（5000ms / 100ms = 50次）
	if (timeout++ > 50)
	{
		debug_println("GPS receive timeout!");
		break;
	}

	HAL_UARTEx_ReceiveToIdle(&huart2, gps_buff, sizeof(gps_buff), &gps_buff_len, 100);
	if (gps_buff_len > 0)
	{
		// 当前接收到数据 => 拼接到大的缓冲区
		uint16_t old_len = gps_full_buff_len;  // 保存旧长度
		memcpy(&gps_full_buff[old_len], gps_buff, gps_buff_len);
		// 记录长度
		gps_full_buff_len += gps_buff_len;
		// 初始化接收缓冲区
		memset(gps_buff, 0, sizeof(gps_buff));
		gps_buff_len = 0;
		// 重置超时计数器
		timeout = 0;
	}
}

if (gps_full_buff_len > 0)
{
	debug_println("%s", gps_full_buff);
}
}

// GPS非阻塞处理（每次主循环调用）
static uint8_t gps_rx_buf[512];
static uint16_t gps_rx_len = 0;

void gps_pros(void)
{
	// 读USART2数据
	uint8_t tmp[64];
	uint16_t len = 0;
	while (HAL_UART_Receive(&huart2, &tmp[len], 1, 5) == HAL_OK) {
		len++;
		if (len >= 63) break;
	}
	if (len > 0) {
		if (gps_rx_len + len < sizeof(gps_rx_buf)) {
			memcpy(&gps_rx_buf[gps_rx_len], tmp, len);
			gps_rx_len += len;
		}
	}

	// 收到完整数据（GGA+TXT）就打印
	if (gps_rx_len > 0 &&
		strstr((char *)gps_rx_buf, "GGA") != NULL &&
		strstr((char *)gps_rx_buf, "TXT") != NULL)
	{
		// 找GGA
		char *gga = strstr((char *)gps_rx_buf, "$GNGGA");
		// 找TXT
		char *txt = strstr((char *)gps_rx_buf, "$GPTXT");

		// 打印：GGA开头，TXT结尾
		if (gga && txt) {
			printf("[GPS] %.*s", (int)(txt + strlen(txt) - gga), gga);
		}
		// 保存 GGA 句子用于 TCP 发送
		if (gga) {
			extern void TCP_Send_Save_GGA(const char *gga_sentence);
			TCP_Send_Save_GGA(gga);
		}
		// 清空缓冲区
		gps_rx_len = 0;
		memset(gps_rx_buf, 0, sizeof(gps_rx_buf));
	}

	// 缓冲区满了也清空
	if (gps_rx_len >= sizeof(gps_rx_buf) - 10) {
		gps_rx_len = 0;
		memset(gps_rx_buf, 0, sizeof(gps_rx_buf));
	}
}




