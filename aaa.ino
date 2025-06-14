#include <Arduino.h>
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"

// —— PIO 时钟配置 ——  
#define CLK_10MHZ_PIN 6    // 10 MHz 系统时钟输出
#define CLK_1KHZ_PIN  7    // 1 kHz CONV 脉冲输出
#define PIO_INST      pio0
#define SM_10MHZ      0
#define SM_1KHZ       1

// —— SPI & CSN 引脚 ——  
#define PIN_MISO      16   // DDC112 DOUT → RP2040 MISO
#define PIN_MOSI      19   // DDC112 DIN  ← RP2040 (will be held low)
#define PIN_SCK       18   // RP2040 SCLK → DDC112 DCLK
#define PIN_CSN       17   // RP2040 → DDC112 nDXMIT (CS)，低选中

// —— 控制引脚 ——  
#define PIN_nDVALID   12   // DDC112 nDVALID → RP2040 IRQ
#define PIN_TEST      8    // RP2040 → DDC112 TEST 控制引脚

// —— ADC／积分参数 ——  
#define ADC_BITS   20      // 20位（每通道）
#define INTEG_US   500.0f   // 500 µs 积分时间 → 1 kHz

// 各档满量程积分电荷 (pC)，默认档位 0
static const float QFS_pC[8] = {
    1000.0f, 100.0f, 50.0f, 25.0f,
     12.5f,   6.25f, 3.125f, 1.5625f
};
uint8_t current_range = 0;

// 数据就绪标志 & 数据缓冲
volatile bool data_ready = false;
volatile uint8_t spi_buf[5];  // 5字节数据，使用volatile确保中断安全
volatile int32_t raw_data = 0;  // 改为int32_t，更准确的数据类型
volatile bool data_processing = false;  // 防止中断重入

// 添加SPI时序控制函数
void spi_read_with_clock(uint8_t* buffer, size_t len) {
    // 手动控制SPI时序，确保与DDC112配合
    for (size_t i = 0; i < len; i++) {
        buffer[i] = 0;
        for (int bit = 7; bit >= 0; bit--) {
            // 上升沿读取数据
            gpio_put(PIN_SCK, 1);
            busy_wait_us(1);  // 确保建立时间
            
            if (gpio_get(PIN_MISO)) {
                buffer[i] |= (1 << bit);
            }
            
            // 下降沿
            gpio_put(PIN_SCK, 0);
            busy_wait_us(1);  // 确保保持时间
        }
    }
}

// —— 中断回调：nDVALID 下降沿 ——  
void irq_handler(uint gpio, uint32_t events) {
    if (events & GPIO_IRQ_EDGE_FALL && !data_processing) {
        data_processing = true;  // 设置处理标志，防止重入
        
        // 等待一小段时间确保数据稳定
        busy_wait_us(10);
        
        // SPI 事务：拉低 CSN → 读 5 字节 → 拉高 CSN
        gpio_put(PIN_CSN, 0);  // DXMIT LOW
        busy_wait_us(2);       // 确保CS建立时间
        
        // 使用改进的SPI读取函数
        spi_read_with_clock((uint8_t*)spi_buf, 5);
        
        busy_wait_us(2);       // 确保CS保持时间
        gpio_put(PIN_CSN, 1);  // DXMIT HIGH
        
        // 修正数据解析：DDC112通道1数据在字节2-4 (20位)
        uint32_t temp = ((uint32_t)(spi_buf[2] & 0x0F) << 16) | 
                       ((uint32_t)spi_buf[3] << 8) | 
                       (uint32_t)spi_buf[4];
        
        // 正确的20位有符号数处理
        if (temp & 0x80000) {  // 检查第20位（符号位）
            raw_data = (int32_t)(temp | 0xFFF00000);  // 符号扩展到32位
        } else {
            raw_data = (int32_t)temp;
        }
        
        data_ready = true;
        data_processing = false;  // 清除处理标志
    }
}

// 初始化 TEST 引脚
void setup_test_pin() {
    gpio_init(PIN_TEST);
    gpio_set_dir(PIN_TEST, GPIO_OUT);
    gpio_set_drive_strength(PIN_TEST, GPIO_DRIVE_STRENGTH_8MA);
    
    // 根据DDC112数据手册：
    // TEST = LOW (0V): 正常工作模式
    // TEST = HIGH (VDD): 测试模式，内部产生已知信号用于测试
    gpio_put(PIN_TEST, 0);  // 设置为正常工作模式
    
    Serial.println(F("TEST pin configured: Normal operation mode (LOW)"));
}

// 设置TEST引脚状态的函数
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

// 初始化 SPI、CSN，以及将 DIN（GPIO19）拉低
void setup_spi_and_din() {
    // 将SPI引脚设置为GPIO模式，手动控制时序
    gpio_init(PIN_MISO);
    gpio_set_dir(PIN_MISO, GPIO_IN);
    gpio_pull_down(PIN_MISO);  // 下拉，确保空闲时为低
    
    gpio_init(PIN_SCK);
    gpio_set_dir(PIN_SCK, GPIO_OUT);
    gpio_set_drive_strength(PIN_SCK, GPIO_DRIVE_STRENGTH_8MA);
    gpio_put(PIN_SCK, 0);  // 时钟空闲为低 (CPOL=0)

    // CSN 引脚初始化
    gpio_init(PIN_CSN);
    gpio_set_dir(PIN_CSN, GPIO_OUT);
    gpio_set_drive_strength(PIN_CSN, GPIO_DRIVE_STRENGTH_8MA);
    gpio_put(PIN_CSN, 1);  // 高 = 未选中

    // 强制将 DIN (MOSI) 拉为低电平
    gpio_init(PIN_MOSI);
    gpio_set_dir(PIN_MOSI, GPIO_OUT);
    gpio_put(PIN_MOSI, 0);
    
    // 确保引脚状态稳定
    sleep_ms(10);
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

// 切换量程（可在运行时调用）
void set_range(uint8_t r) {
    if (r > 7) return;
    current_range = r;
    Serial.printf("Range set to %u (QFS=%.4f pC)\n", r, QFS_pC[r]);
}

void setup() {
    Serial.begin(115200);
    delay(500);  // 增加延时确保串口稳定
    Serial.println(F(">> DDC112 Single Channel Current Meter Starting >>"));

    setup_pio_clocks();
    setup_spi_and_din();
    setup_test_pin();      // 添加TEST引脚初始化
    setup_ndvalid_irq();

    Serial.println(F("Setup complete. Awaiting nDVALID IRQ..."));
    Serial.printf("System clock: %u Hz\n", clock_get_hz(clk_sys));
    Serial.printf("Current range: %u (QFS=%.4f pC)\n", current_range, QFS_pC[current_range]);
    
    // 可选：启动时进行自检
    Serial.println(F("Performing self-test..."));
    set_test_mode(true);   // 启用测试模式
    delay(100);            // 等待几个积分周期
    set_test_mode(false);  // 回到正常模式
}

void loop() {
    static uint32_t last_print = 0;
    static uint32_t sample_count = 0;
    static int32_t last_valid_data = 0;  // 用于检测数据变化
    
    // 每500ms打印一次状态（如果没有数据）
    if (!data_ready && (millis() - last_print > 500)) {
        Serial.printf("Waiting for data... (samples: %lu, nDVALID: %d)\n", 
                      sample_count, gpio_get(PIN_nDVALID));
        last_print = millis();
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

    // 数据有效性检查
    if (current_data == last_valid_data && sample_count > 1) {
        // 连续相同数据可能表示通信问题
        if (sample_count % 20 == 0) {
            Serial.printf("Warning: No data change detected for %lu samples\n", sample_count);
        }
    }
    last_valid_data = current_data;

    // 计算电流 (A) - 修正计算公式
    float qfs = QFS_pC[current_range] * 1e-12f;    // pC → C
    float ifs = qfs / (INTEG_US * 1e-6f);          // C/s → A
    
    // 20位有符号数的满量程是 ±(2^19-1)
    float full_scale = (float)((1 << 19) - 1);
    float Iamp = ((float)current_data / full_scale) * ifs;

    // 打印结果，增加更多调试信息
    Serial.printf("I = %.9f A (raw=%ld, 0x%05lX, FS=%.3e)\n", 
                  Iamp, (long)current_data, (unsigned long)(current_data & 0xFFFFF), ifs);
    
    // 每10个样本打印一次原始字节数据和引脚状态
    if (sample_count % 10 == 0) {
        Serial.printf("Raw bytes: %02X %02X %02X %02X %02X | nDVALID=%d CSN=%d\n", 
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
            Serial.printf("  Range: %u (%.4f pC)\n", current_range, QFS_pC[current_range]);
            Serial.printf("  nDVALID: %d\n", gpio_get(PIN_nDVALID));
            Serial.printf("  Data processing: %s\n", data_processing ? "true" : "false");
        }
    }
}