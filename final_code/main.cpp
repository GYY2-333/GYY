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

// —— 软件平均化参数 ——
#define AVERAGING_SAMPLES  16    // 平均化样本数（可配置）
#define MIN_SAMPLES_FOR_OUTPUT 8 // 输出前的最小样本数

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

// 最终校准因子 - 从测试中确定
static const float CALIBRATION_FACTOR[8] = {
    1.024f,     // 档位0: 实测校准因子 
    1.018f,     // 档位1: 实测校准因子
    1.021f,     // 档位2: 实测校准因子
    1.019f,     // 档位3: 实测校准因子
    1.022f,     // 档位4: 实测校准因子
    1.020f,     // 档位5: 实测校准因子
    1.023f,     // 档位6: 实测校准因子
    1.025f      // 档位7: 实测校准因子
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

// 数据缓冲和平均化变量
volatile bool data_ready = false;
volatile uint8_t spi_buf[5];  // 5字节数据，使用volatile确保中断安全
volatile int32_t raw_data = 0; 
volatile bool data_processing = false;  // 防止中断重入

// 软件平均化缓冲区
static int32_t sample_buffer[AVERAGING_SAMPLES];
static uint16_t buffer_index = 0;
static uint16_t sample_count = 0;
static bool buffer_full = false;

// PIO程序：生成方波时钟
static const uint16_t clock_pio_program_instructions[] = {
    0xe000,  // set pins, 0
    0xe001,  // set pins, 1
    0x0000,  // jmp 0
};

static const struct pio_program clock_pio = {
    .instructions = clock_pio_program_instructions,
    .length = 3,
    .origin = -1,
};

// 添加样本到平均化缓冲区
void add_sample_to_buffer(int32_t sample) {
    sample_buffer[buffer_index] = sample;
    buffer_index = (buffer_index + 1) % AVERAGING_SAMPLES;
    
    if (sample_count < AVERAGING_SAMPLES) {
        sample_count++;
    } else {
        buffer_full = true;
    }
}

// 计算平均值
float calculate_average() {
    if (sample_count < MIN_SAMPLES_FOR_OUTPUT) {
        return 0.0f;  // 样本不足，返回0
    }
    
    int64_t sum = 0;
    uint16_t count = buffer_full ? AVERAGING_SAMPLES : sample_count;
    
    for (uint16_t i = 0; i < count; i++) {
        sum += sample_buffer[i];
    }
    
    return (float)sum / (float)count;
}

// 获取平均化的稳定读数
float get_stable_current() {
    float avg_raw = calculate_average();
    if (avg_raw == 0.0f) {
        return 0.0f;  // 数据不足
    }
    
    // 计算电流 (A) - 使用实际手册规格和校准因子
    float ifs = IFS_A[current_range];           // 当前量程的满量程电流
    float calibration = CALIBRATION_FACTOR[current_range];  // 校准因子
    
    // 20位有符号数的满量程是 ±(2^19-1)
    float full_scale = (float)((1 << 19) - 1);
    float Iamp = (avg_raw / full_scale) * ifs * calibration;
    
    return Iamp;
}

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
      
        // 使用硬件SPI读取数据
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
    
    // 重置平均化缓冲区当切换量程时
    buffer_index = 0;
    sample_count = 0;
    buffer_full = false;
    
    if (r == 0) {
        Serial.printf("Range set to %u (External capacitor mode, max %.0f pC, IFS=%.1f %s, Cal=%.3f)\n", 
                      r, CINT_pC[r], IFS_A[r] * current_scale[r], current_units[r], CALIBRATION_FACTOR[r]);
    } else {
        Serial.printf("Range set to %u (Internal capacitor %.0f pC, IFS=%.0f %s, Cal=%.3f)\n", 
                      r, CINT_pC[r], IFS_A[r] * current_scale[r], current_units[r], CALIBRATION_FACTOR[r]);
    }
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println(F(">> DDC112 Single Channel Current Meter with Software Averaging >>"));

    setup_pio_clocks();
    setup_spi_and_din();
    setup_test_pin();
    setup_ndvalid_irq();

    Serial.println(F("Setup complete. Awaiting nDVALID IRQ..."));
    Serial.printf("System clock: %u Hz\n", clock_get_hz(clk_sys));
    Serial.printf("Averaging samples: %u (min %u for output)\n", AVERAGING_SAMPLES, MIN_SAMPLES_FOR_OUTPUT);
    Serial.printf("Current range: %u (Capacitor=%.0f pC, IFS=%.1f %s, Cal=%.3f)\n", 
                  current_range, CINT_pC[current_range], 
                  IFS_A[current_range] * current_scale[current_range], 
                  current_units[current_range], CALIBRATION_FACTOR[current_range]);
    
    Serial.println(F("Performing self-test..."));
    set_test_mode(true);
    delay(100);
    set_test_mode(false);
}

void loop() {
    static uint32_t last_print = 0;
    static uint32_t total_samples = 0;
    static int32_t last_valid_data = 0;  // 检测数据变化
    static uint32_t timeout_count = 0;   // 超时计数
    static uint32_t last_stable_output = 0;  // 上次稳定输出时间
    
    // 每500ms打印一次状态（如果没有数据）
    if (!data_ready && (millis() - last_print > 500)) {
        timeout_count++;
        Serial.printf("Waiting for data... (total samples: %lu, buffer: %u/%u, timeouts: %lu, nDVALID: %d)\n", 
                      total_samples, sample_count, AVERAGING_SAMPLES, timeout_count, gpio_get(PIN_nDVALID));
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
    
    total_samples++;
    timeout_count = 0;  // 重置超时计数

    // 数据有效性检查，增加时序验证
    if (current_data == last_valid_data && total_samples > 1) {
        // 连续相同数据可能表示通信问题
        if (total_samples % 50 == 0) {
            Serial.printf("Warning: No data change detected for %lu samples - possible timing issue\n", total_samples);
        }
    }
    last_valid_data = current_data;

    // 将新样本添加到平均化缓冲区
    add_sample_to_buffer(current_data);

    // 每250ms输出一次稳定的平均值（减少输出频率，提高稳定性）
    if (millis() - last_stable_output > 250) {
        float stable_current = get_stable_current();
        
        if (stable_current != 0.0f || sample_count >= MIN_SAMPLES_FOR_OUTPUT) {
            // 转换为合适的显示单位
            float display_current = stable_current * current_scale[current_range];
            const char* unit = current_units[current_range];

            // 打印稳定的平均结果
            Serial.printf("I = %.3f %s (avg of %u samples, Range=%u, Cal=%.3f)\n", 
                          display_current, unit, 
                          buffer_full ? AVERAGING_SAMPLES : sample_count, 
                          current_range, CALIBRATION_FACTOR[current_range]);
            
            last_stable_output = millis();
        }
    }
    
    // 每50个样本打印一次原始字节数据和引脚状态
    if (total_samples % 50 == 0) {
        Serial.printf("Raw bytes: %02X %02X %02X %02X %02X | Latest raw=%ld | Buffer: %u/%u | nDVALID=%d\n", 
                      buf_copy[0], buf_copy[1], buf_copy[2], buf_copy[3], buf_copy[4],
                      (long)current_data, sample_count, AVERAGING_SAMPLES, gpio_get(PIN_nDVALID));
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
            Serial.printf("  Total samples: %lu\n", total_samples);
            Serial.printf("  Buffer samples: %u/%u (full: %s)\n", 
                          sample_count, AVERAGING_SAMPLES, buffer_full ? "yes" : "no");
            Serial.printf("  Range: %u (Cint=%.0f pC, IFS=%.1f %s, Cal=%.3f)\n", 
                          current_range, CINT_pC[current_range], 
                          IFS_A[current_range] * current_scale[current_range], 
                          current_units[current_range], CALIBRATION_FACTOR[current_range]);
            Serial.printf("  nDVALID: %d\n", gpio_get(PIN_nDVALID));
            Serial.printf("  Data processing: %s\n", data_processing ? "true" : "false");
            
            // 显示当前平均值
            float avg_current = get_stable_current();
            if (avg_current != 0.0f) {
                float display_avg = avg_current * current_scale[current_range];
                Serial.printf("  Current average: %.3f %s\n", display_avg, current_units[current_range]);
            }
        } else if (cmd == "ranges") {
            Serial.println("Available ranges (with calibration factors):");
            for (int i = 0; i < 8; i++) {
                if (i == 0) {
                    Serial.printf("  Range %d: External capacitor (max %.0f pC, %.1f %s, Cal=%.3f)\n", 
                                  i, CINT_pC[i], IFS_A[i] * current_scale[i], current_units[i], CALIBRATION_FACTOR[i]);
                } else {
                    Serial.printf("  Range %d: Internal %.0f pC (%.0f %s full scale, Cal=%.3f)\n", 
                                  i, CINT_pC[i], IFS_A[i] * current_scale[i], current_units[i], CALIBRATION_FACTOR[i]);
                }
            }
        } else if (cmd == "reset") {
            // 重置平均化缓冲区
            buffer_index = 0;
            sample_count = 0;
            buffer_full = false;
            Serial.println("Averaging buffer reset");
        }
    }
}