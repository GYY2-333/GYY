#include <Arduino.h>
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"

// —— PIO 时钟配置 ——  
#define CLK_10MHZ_PIN 6    // 10 MHz 系统时钟输出
#define CLK_1KHZ_PIN  7    // 1 kHz CONV 积分
#define PIO_INST      pio0
#define SM_10MHZ      0
#define SM_1KHZ       1

// —— SPI & CSN 引脚 ——  
#define PIN_MISO      16   // DDC112 DOUT → RP2040 MISO
#define PIN_MOSI      19   // DDC112 DIN  ← RP2040 
#define PIN_SCK       18   // RP2040 SCLK → DDC112 DCLK
#define PIN_CSN       17   // RP2040 → DDC112 nDXMIT (CS)，低选中
#define SPI_PORT      spi0

// —— 控制引脚 ——  
#define PIN_nDVALID   12   // DDC112 nDVALID → RP2040 IRQ
#define PIN_TEST      8    // RP2040 → DDC112 TEST 

// —— ADC／积分参数 ——  
#define ADC_BITS   20      // 20位（每通道）
#define INTEG_US   500.0f   // 500 µs 积分时间 → 1 kHz

// DDC112内部积分电容设置 (pC) - 根据实际手册
static const float CINT_pC[8] = {
    1000.0f,  // 档位0: 
    50.0f,    // 1
    100.0f,   // 2
    150.0f,   // 3
    200.0f,   // 4
    250.0f,   // 5
    300.0f,   // 6
    350.0f    // 7
};

// 各档满量程电流 (A) - 根据积分电容计算: I = Q/t
static const float IFS_A[8] = {
    2.0e-6f,    // 档位0: 2μA
    1.0e-7f,    // 档位1:  100nA
    2.0e-7f,    // 档位2: 200nA
    3.0e-7f,    // 档位3: 300nA
    4.0e-7f,    // 档位4: 400nA
    5.0e-7f,    // 档位5: 500nA
    6.0e-7f,    // 档位6: 600nA
    7.0e-7f     // 档位7: 700nA
};

// 电流单位字符串
static const char* current_units[8] = {
    "μA", "nA", "nA", "nA", "nA", "nA", "nA", "nA"
};

// 电流显示系数（转换为显示单位）
static const float current_scale[8] = {
    1e6f,  
    1e9f,   
    1e9f,   
    1e9f,   
    1e9f,   
    1e9f,   
    1e9f,   
    1e9f    
};

uint8_t current_range = 0;


volatile bool data_ready = false;
volatile uint8_t spi_buf[5];  // 5字节数据，使用volatile确保中断安全
volatile int32_t raw_data = 0; 
volatile bool data_processing = false;  // 防止中断重入

// 硬件SPI
void spi_read_hardware(uint8_t* buffer, size_t len) {
    // 使用硬件SPI读取数据，提高传输速度
    spi_read_blocking(SPI_PORT, 0x00, buffer, len);
}

// —— 中断回调：nDVALID 下降沿 ——  
void irq_handler(uint gpio, uint32_t events) {
    if (events & GPIO_IRQ_EDGE_FALL && !data_processing) {
        data_processing = true;  // 设置处理标志，防止重入
        
        // 减少延迟，立即开始SPI传输
        busy_wait_us(1);  
        
        // 立即拉低CSN并开始SPI传输
        gpio_put(PIN_CSN, 0);  // DXMIT LOW
      
        // 使用硬件SP读取数据
        spi_read_hardware((uint8_t*)spi_buf, 5);
        
        gpio_put(PIN_CSN, 1);  // 立即拉高CSN
        
        // 数据解析：DDC112通道1数据在字节2-4 (20位)
        uint32_t temp = ((uint32_t)(spi_buf[2] & 0x0F) << 16) | 
                       ((uint32_t)spi_buf[3] << 8) | 
                       (uint32_t)spi_buf[4];
        
        if (temp & 0x80000) {  // 检查第20位（符号位）
            raw_data = (int32_t)(temp | 0xFFF00000);  // 符号扩展到32位
        } else {
            raw_data = (int32_t)temp;
        }
        
        data_ready = true;
        data_processing = false;  // 清除处理标志
    }
}

// 初始化 TEST 
void setup_test_pin() {
    gpio_init(PIN_TEST);
    gpio_set_dir(PIN_TEST, GPIO_OUT);
    gpio_set_drive_strength(PIN_TEST, GPIO_DRIVE_STRENGTH_8MA);

    // TEST = LOW (0V): 正常工作
    gpio_put(PIN_TEST, 0);  
    
    Serial.println(F("TEST pin configured: Normal operation mode (LOW)"));
}

void set_test_mode(bool test_mode) {
    gpio_put(PIN_TEST, test_mode ? 1 : 0);
    if (test_mode) {
        Serial.println(F("TEST mode enabled: Internal test signal active"));
    } else {
        Serial.println(F("Normal mode: External signal measurement"));
    }
}

// 初始化 PIO 同步产生 10 MHz 和 1 kHz 方波
void setup_pio_clocks() {
    pio_clear_instruction_memory(PIO_INST);
    pio_restart_sm_mask(PIO_INST, (1u<<SM_10MHZ)|(1u<<SM_1KHZ));
    uint offset = pio_add_program(PIO_INST, &clock_pio);
    uint32_t sys_hz = clock_get_hz(clk_sys);

    for (int pin : {CLK_10MHZ_PIN, CLK_1KHZ_PIN}) {
        gpio_init(pin);
        gpio_set_drive_strength(pin, GPIO_DRIVE_STRENGTH_8MA);
        pio_gpio_init(PIO_INST, pin);
    }

    // SM0 → 10 MHz: clkdiv = sys_hz / (4 * 10e6)
    {
        pio_sm_config c = pio_get_default_sm_config();
        sm_config_set_wrap(&c, offset+1, offset+4);
        sm_config_set_set_pins(&c, CLK_10MHZ_PIN, 1);
        sm_config_set_clkdiv(&c, (float)sys_hz / (4.0f * 10e6f));
        pio_sm_init(PIO_INST, SM_10MHZ, offset, &c);
    }
    
    // SM1 → 1 kHz: clkdiv = sys_hz / (4 * 1e3)
    {
        pio_sm_config c = pio_get_default_sm_config();
        sm_config_set_wrap(&c, offset+1, offset+4);
        sm_config_set_set_pins(&c, CLK_1KHZ_PIN, 1);
        sm_config_set_clkdiv(&c, (float)sys_hz / (4.0f * 1e3f));
        pio_sm_init(PIO_INST, SM_1KHZ, offset, &c);
    }

    pio_set_sm_mask_enabled(PIO_INST, (1u<<SM_10MHZ)|(1u<<SM_1KHZ), true);
}

// 初始化硬件SPI、CSN，以及将 DIN（GPIO19）拉低
void setup_spi_and_din() {
    // 初始化硬件SPI，提高时钟频率
    spi_init(SPI_PORT, 4000000);  // 4MHz
    
    // 配置SPI引脚功能
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);  // RX
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);   // SCK
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);  // TX
    
    // 配置SPI格式：CPOL=1, CPHA=1（模式3）
    spi_set_format(SPI_PORT, 8, SPI_CPOL_1, SPI_CPHA_1, SPI_MSB_FIRST);

    // CSN 引脚初始化（手动控制CS），设置更高驱动强度
    gpio_init(PIN_CSN);
    gpio_set_dir(PIN_CSN, GPIO_OUT);
    gpio_set_drive_strength(PIN_CSN, GPIO_DRIVE_STRENGTH_12MA);  // 提高驱动强度
    gpio_put(PIN_CSN, 1);  // 高 = 未选中

    // 强制将 DIN (MOSI) 保持低电平
    
    // 确保引脚状态稳定
    sleep_ms(10);
    
    Serial.println(F("Hardware SPI initialized (Mode 3, 4MHz) - Optimized for fast data capture"));
}

// 初始化 nDVALID 的下降沿中断
void setup_ndvalid_irq() {
    gpio_init(PIN_nDVALID);
    gpio_set_dir(PIN_nDVALID, GPIO_IN);
    gpio_pull_up(PIN_nDVALID);  // 内部上拉
    
    // 清除任何待处理的中断
    gpio_acknowledge_irq(PIN_nDVALID, GPIO_IRQ_EDGE_FALL);
    
    gpio_set_irq_enabled_with_callback(
        PIN_nDVALID,
        GPIO_IRQ_EDGE_FALL,
        true,
        &irq_handler
    );
}

// 切换量程
void set_range(uint8_t r) {
    if (r > 7) return;
    current_range = r;
    
    if (r == 0) {
        Serial.printf("Range set to %u (External capacitor mode, max %.0f pC, IFS=%.1f %s)\n", 
                      r, CINT_pC[r], IFS_A[r] * current_scale[r], current_units[r]);
    } else {
        Serial.printf("Range set to %u (Internal capacitor %.0f pC, IFS=%.0f %s)\n", 
                      r, CINT_pC[r], IFS_A[r] * current_scale[r], current_units[r]);
    }
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println(F(">> DDC112 Single Channel Current Meter Starting (Hardware SPI) >>"));

    setup_pio_clocks();
    setup_spi_and_din();
    setup_test_pin();
    setup_ndvalid_irq();

    Serial.println(F("Setup complete. Awaiting nDVALID IRQ..."));
    Serial.printf("System clock: %u Hz\n", clock_get_hz(clk_sys));
    Serial.printf("Current range: %u (Capacitor=%.0f pC, IFS=%.1f %s)\n", 
                  current_range, CINT_pC[current_range], 
                  IFS_A[current_range] * current_scale[current_range], 
                  current_units[current_range]);
    
    Serial.println(F("Performing self-test..."));
    set_test_mode(true);
    delay(100);
    set_test_mode(false);
}

void loop() {
    static uint32_t last_print = 0;
    static uint32_t sample_count = 0;
    static int32_t last_valid_data = 0;  // 检测数据变化
    static uint32_t timeout_count = 0;   // 超时计数
    
    // 每500ms打印一次状态（如果没有数据）
    if (!data_ready && (millis() - last_print > 500)) {
        timeout_count++;
        Serial.printf("Waiting for data... (samples: %lu, timeouts: %lu, nDVALID: %d)\n", 
                      sample_count, timeout_count, gpio_get(PIN_nDVALID));
        last_print = millis();
        
        // 如果长时间无数据，检查时序问题
        if (timeout_count > 10) {
            Serial.println("Warning: Long timeout - check DDC112 timing and connections");
            timeout_count = 0;
        }
    }

    if (!data_ready) return;
    
    // 临界区：禁用中断以安全读取数据
    uint32_t irq_status = save_and_disable_interrupts();
    int32_t current_data = raw_data;
    uint8_t buf_copy[5];
    memcpy(buf_copy, (const void*)spi_buf, 5);  // 复制缓冲区数据
    data_ready = false;
    restore_interrupts(irq_status);
    
    sample_count++;
    timeout_count = 0;  // 重置超时计数

    // 数据有效性检查，增加时序验证
    if (current_data == last_valid_data && sample_count > 1) {
        // 连续相同数据可能表示通信问题
        if (sample_count % 20 == 0) {
            Serial.printf("Warning: No data change detected for %lu samples - possible timing issue\n", sample_count);
        }
    }
    last_valid_data = current_data;

    // 计算电流 (A) - 使用实际手册规格
    float ifs = IFS_A[current_range];           // 当前量程的满量程电流
    
    // 20位有符号数的满量程是 ±(2^19-1)
    float full_scale = (float)((1 << 19) - 1);
    float Iamp = ((float)current_data / full_scale) * ifs;
    
    // 转换为合适的显示单位
    float display_current = Iamp * current_scale[current_range];
    const char* unit = current_units[current_range];

    // 打印结果，使用正确的DDC112手册单位
    Serial.printf("I = %.3f %s (raw=%ld, 0x%05lX, Range=%u, Cint=%.0f pC)\n", 
                  display_current, unit, (long)current_data, 
                  (unsigned long)(current_data & 0xFFFFF), current_range,
                  CINT_pC[current_range]);
    
    // 每10个样本打印一次原始字节数据和引脚状态，添加时序信息
    if (sample_count % 10 == 0) {
        Serial.printf("Raw bytes: %02X %02X %02X %02X %02X | nDVALID=%d CSN=%d | SPI: 4MHz\n", 
                      buf_copy[0], buf_copy[1], buf_copy[2], buf_copy[3], buf_copy[4],
                      gpio_get(PIN_nDVALID), gpio_get(PIN_CSN));
    }
    
    // 串口命令处理
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        
        if (cmd.startsWith("test")) {
            if (cmd.endsWith("on")) {
                set_test_mode(true);
            } else if (cmd.endsWith("off")) {
                set_test_mode(false);
            }
        } else if (cmd.startsWith("range")) {
            int r = cmd.substring(5).toInt();
            if (r >= 0 && r <= 7) {
                set_range(r);
            }
        } else if (cmd == "status") {
            Serial.printf("System status:\n");
            Serial.printf("  Samples: %lu\n", sample_count);
            Serial.printf("  Range: %u (Cint=%.0f pC, IFS=%.1f %s)\n", 
                          current_range, CINT_pC[current_range], 
                          IFS_A[current_range] * current_scale[current_range], 
                          current_units[current_range]);
            Serial.printf("  nDVALID: %d\n", gpio_get(PIN_nDVALID));
            Serial.printf("  Data processing: %s\n", data_processing ? "true" : "false");
        } else if (cmd == "ranges") {
            Serial.println("Available ranges:");
            for (int i = 0; i < 8; i++) {
                if (i == 0) {
                    Serial.printf("  Range %d: External capacitor (max %.0f pC, %.1f %s)\n", 
                                  i, CINT_pC[i], IFS_A[i] * current_scale[i], current_units[i]);
                } else {
                    Serial.printf("  Range %d: Internal %.0f pC (%.0f %s full scale)\n", 
                                  i, CINT_pC[i], IFS_A[i] * current_scale[i], current_units[i]);
                }
            }
        }
    }
}