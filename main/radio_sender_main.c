#include <stdio.h>
#include <string.h>
#include "driver/uart.h"
#include "driver/i2c.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define TXD_PIN 17
#define RXD_PIN 18

#define SDA_PIN 35
#define SCL_PIN 36

#define I2C_PORT I2C_NUM_0

#define UART_PORT UART_NUM_1
#define RX_BUF_SIZE 1024

void init_i2c(void) {
    i2c_config_t i2c_config = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = SDA_PIN,
        .scl_io_num = SCL_PIN,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 400000
    };

    i2c_param_config(I2C_PORT, &i2c_config);

    i2c_driver_install(I2C_PORT, i2c_config.mode, 0, 0, 0);
}

void init_xbee_uart(void)
{
    const uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    uart_param_config(UART_PORT, &uart_config);

    uart_set_pin(UART_PORT, TXD_PIN, RXD_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    uart_driver_install(UART_PORT, RX_BUF_SIZE * 2, 0, 0, NULL, 0);
}

esp_err_t i2c_read(uint8_t addr, uint8_t* data, size_t size) {
    if (size == 0) return ESP_OK;

    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (addr << 1) | I2C_MASTER_READ, true);

    if (size > 1) {
        i2c_master_read(cmd, data, size - 1, I2C_MASTER_ACK);
    }

    i2c_master_read_byte(cmd, data + size - 1, I2C_MASTER_NACK);

    i2c_master_stop(cmd);

    esp_err_t ret = i2c_master_cmd_begin(I2C_PORT, cmd, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(cmd);

    return ret;
}

void app_main(void)
{
    init_i2c();
    init_xbee_uart();

    uint8_t i2c_data[2];
    const uint8_t GPS_ADDR = 0x42;
    
    ESP_LOGI("main", "running send loop");

    while (1)
    {

        esp_err_t err = i2c_read(GPS_ADDR, i2c_data, 2);

        if (err == ESP_OK)
        {
            ESP_LOGI("I2C", "Read Success: Byte1: 0x%02x, Byte2: 0x%02x", i2c_data[0], i2c_data[1]);
        }
        else
        {
            ESP_LOGE("I2C", "Read Failed: %s", esp_err_to_name(err));
        }

        int n = uart_write_bytes(UART_PORT, i2c_data, sizeof(i2c_data));
        ESP_LOGI("UART", "Sent %d bytes over UART", n);

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}