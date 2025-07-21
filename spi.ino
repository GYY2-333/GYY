#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

#define SPI_PORT spi0
#define SPI_SCK_PIN 18
#define SPI_RX_PIN 16
#define SPI_TX_PIN 19      
#define CS_PIN 17          
#define NDVALID_PIN 12

#define RANGE0_PIN 11
#define RANGE1_PIN 10
#define RANGE2_PIN 9

// --- Averaging Filter Settings ---
#define NUM_SAMPLES 1000 
float samples[NUM_SAMPLES];
int sample_index = 0;

volatile uint32_t raw_in1 = 0;
volatile bool read_ok = false;

// --- PIO and ISR setup ---
const uint16_t pio_program_instructions[] = { 0xe001, 0xe000 };
const struct pio_program pio_prog = {
    .instructions = pio_program_instructions,
    .length = 2,
    .origin = -1,
};

void nDVALID_isr(uint gpio, uint32_t events) {
    uint8_t a, b, c, d, e;
    gpio_put(CS_PIN, 0);
    spi_read_blocking(SPI_PORT, 0x00, &a, 1);
    spi_read_blocking(SPI_PORT, 0x00, &b, 1);
    spi_read_blocking(SPI_PORT, 0x00, &c, 1);
    spi_read_blocking(SPI_PORT, 0x00, &d, 1);
    spi_read_blocking(SPI_PORT, 0x00, &e, 1);
    gpio_put(CS_PIN, 1);
    raw_in1 = ((c & 0x0F) << 16) | (d << 8) | e;
    read_ok = true;
    gpio_acknowledge_irq(gpio, events);
}

int32_t sign_extend_20_bit(uint32_t raw_value) {
    const uint32_t sign_bit = 1 << 19;
    if (raw_value & sign_bit) {
        return raw_value | 0xFFF00000;
    }
    return raw_value;
}

// ---  Multi-Point Calibration Function  ---
float multi_point_calibration(float raw_measured_val) {
    // 四点校准
    const float cal_points[][2] = {
        {0.00545f,  0.0f},      // Point 1: New Zero Point
        {0.14757f,  0.105f},    // Point 2: Low Range
        {0.32109f,  0.203f},    // Point 3: Mid Range
        {0.50512f,  0.301f}     // Point 4: High Range
    };
    const int num_cal_points = 4;

    
    float offset_corrected_val = raw_measured_val - cal_points[0][0];

    if (offset_corrected_val < 0) {
        return 0.0f;
    }

   
    for (int i = 1; i < num_cal_points - 1; i++) {
    
        float seg_low_raw = cal_points[i][0] - cal_points[0][0];     // 计算当前区间的下限（已校正零点偏移）
        float seg_high_raw = cal_points[i+1][0] - cal_points[0][0];   // 计算当前区间的上限（已校正零点偏移）
        
        // 判断经过偏移校正后的值是否落在此区间内
        if (offset_corrected_val >= seg_low_raw && offset_corrected_val <= seg_high_raw) {
            float i_low = cal_points[i][1];     // 获取区间下限对应的理想值
            float i_high = cal_points[i+1][1];  // 获取区间上限对应的理想值

            if (seg_high_raw == seg_low_raw) return i_low; // 避免除以零

            // 使用线性插值公式计算最终校准值
            return i_low + (offset_corrected_val - seg_low_raw) * (i_high - i_low) / (seg_high_raw - seg_low_raw);
        }
    }
    
    // 处理超出主要校准范围的值（外插）
    if (offset_corrected_val > (cal_points[num_cal_points-1][0] - cal_points[0][0])) {
        // 使用最后两个校准点构成的线段进行外插
        float seg_low_raw = cal_points[num_cal_points-2][0] - cal_points[0][0];
        float seg_high_raw = cal_points[num_cal_points-1][0] - cal_points[0][0];
        float i_low = cal_points[num_cal_points-2][1];
        float i_high = cal_points[num_cal_points-1][1];
        if (seg_high_raw == seg_low_raw) return i_high; // 避免除以零
        return i_low + (offset_corrected_val - seg_low_raw) * (i_high - i_low) / (seg_high_raw - seg_low_raw);
    }

    // 在正常操作中不应到达此处。如果到达，则返回经过偏移校正的值。
    return offset_corrected_val; 
}


void setup() {
  Serial.begin(115200); // 串口通信波特率115200
  
 
   const int PIN = 1;      
  pinMode(1, OUTPUT);      // 设置引脚1为输出
  digitalWrite(1, HIGH);  
 

  set_sys_clock_khz(125000, true); // 设置系统时钟为125MHz
  
  // --- 采集模式设置 ---
  const uint PIN_GPIO8 = 8;
  gpio_init(PIN_GPIO8);               // 初始化GPIO 8
  gpio_set_dir(PIN_GPIO8, GPIO_OUT);  
  gpio_put(PIN_GPIO8, 0);             // 设置为低电平

  // --- SPI 初始化 ---
  spi_init(SPI_PORT, 10 * 1000 * 1000); // 初始化SPI0，时钟频率为10MHz
  spi_set_format(SPI_PORT, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
  
  gpio_set_function(SPI_SCK_PIN, GPIO_FUNC_SPI);
  gpio_set_function(SPI_RX_PIN, GPIO_FUNC_SPI);
  gpio_set_function(SPI_TX_PIN, GPIO_FUNC_SPI);
  
  gpio_init(CS_PIN);
  gpio_set_dir(CS_PIN, GPIO_OUT);
  gpio_put(CS_PIN, 1); 

  gpio_init(RANGE0_PIN); gpio_set_dir(RANGE0_PIN, GPIO_OUT);
  gpio_init(RANGE1_PIN); gpio_set_dir(RANGE1_PIN, GPIO_OUT);
  gpio_init(RANGE2_PIN); gpio_set_dir(RANGE2_PIN, GPIO_OUT);
  
  gpio_put(RANGE0_PIN, 1);
  gpio_put(RANGE1_PIN, 1);
  gpio_put(RANGE2_PIN, 1);

  gpio_init(NDVALID_PIN);
  gpio_set_dir(NDVALID_PIN, GPIO_IN);
  gpio_set_irq_enabled_with_callback(NDVALID_PIN, GPIO_IRQ_EDGE_FALL, true, &nDVALID_isr);

  PIO pio = pio0;
  uint offset = pio_add_program(pio, &pio_prog);
  
  const int pin_10mhz = 6;
  const int freq_10mhz = 10000000;
  uint sm_10mhz = pio_claim_unused_sm(pio, true);
  pio_sm_config c_10mhz = pio_get_default_sm_config();
  sm_config_set_set_pins(&c_10mhz, pin_10mhz, 1);
  sm_config_set_wrap(&c_10mhz, offset, offset + pio_prog.length - 1);
  float div_10mhz = (float)clock_get_hz(clk_sys) / (freq_10mhz * 2);
  sm_config_set_clkdiv(&c_10mhz, div_10mhz);
  pio_gpio_init(pio, pin_10mhz);
  pio_sm_set_consecutive_pindirs(pio, sm_10mhz, pin_10mhz, 1, true);
  pio_sm_init(pio, sm_10mhz, offset, &c_10mhz);

  const int pin_1khz = 7;
  const int freq_1khz = 1000;
  uint sm_1khz = pio_claim_unused_sm(pio, true);
  pio_sm_config c_1khz = pio_get_default_sm_config();
  sm_config_set_set_pins(&c_1khz, pin_1khz, 1);
  sm_config_set_wrap(&c_1khz, offset, offset + pio_prog.length - 1);
  float div_1khz = (float)clock_get_hz(clk_sys) / (freq_1khz * 2);
  sm_config_set_clkdiv(&c_1khz, div_1khz);
  pio_gpio_init(pio, pin_1khz);
  pio_sm_set_consecutive_pindirs(pio, sm_1khz, pin_1khz, 1, true);
  pio_sm_init(pio, sm_1khz, offset, &c_1khz);
  
  uint mask = (1u << sm_10mhz) | (1u << sm_1khz);
  pio_set_sm_mask_enabled(pio, mask, true);
}


void loop() {
  if (read_ok) {
    int32_t signed_in1 = sign_extend_20_bit(raw_in1);
    
   
    const float FULL_SCALE_CHARGE_pC = 350.0; 
    const float denominator = 524288.0;      
    const float t_INT_us = 500.0;            
    float current1_uA_raw = (float)signed_in1 / denominator * FULL_SCALE_CHARGE_pC / t_INT_us;


    samples[sample_index] = current1_uA_raw;
    sample_index++;


    if (sample_index >= NUM_SAMPLES) {
        float sum = 0;
        for (int i = 0; i < NUM_SAMPLES; i++) {
            sum += samples[i];
        }
        float average_raw_current = sum / NUM_SAMPLES;


        float final_corrected_current = multi_point_calibration(average_raw_current);

        Serial.print("Final Corrected Current: ");
        Serial.print(final_corrected_current, 7); 
        Serial.println(" uA");
        
        sample_index = 0; 
    }
    
    read_ok = false;
  }
}