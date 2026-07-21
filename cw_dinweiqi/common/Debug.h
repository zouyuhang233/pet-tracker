#ifndef __DEBUG_H
#define __DEBUG_H
#include "main.h"

void Debug_init(void);

/* 开发调试的过程中 保留打印输出 一旦项目上线 开关 关闭掉所有的串口输出 */
#define DEBUG_ENABLE

#ifdef DEBUG_ENABLE

// 替换__FILE__ 只保留文件名称 取出路径名称
// FILE__NAME => 去除\\的路径名称
#define FILE__NAME (strrchr(__FILE__,'\\') ? strrchr(__FILE__,'\\') + 1 : __FILE__)

// 最终调用__FILE__NAME__ => 去除带有/路径名称 内部包含FILE__NAME
#define __FILE__NAME__ (strrchr(FILE__NAME,'/') ? strrchr(FILE__NAME,'/') + 1 : FILE__NAME)

#define debug_printf(format,...)  printf("[%s:%d]" format,__FILE__NAME__,__LINE__,##__VA_ARGS__)
#define debug_println(format,...) printf("[%s:%d]" format "\r\n",__FILE__NAME__,__LINE__,##__VA_ARGS__)

// 实现开启串口打印的宏定义
#else
// 空的宏定义 => 编译通过
#define debug_printf(...)
#define debug_println(...)

#endif

#endif
