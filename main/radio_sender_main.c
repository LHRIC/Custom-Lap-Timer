#include <stdio.h>
#include <string.h>
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define TXD_PIN 17
#define RXD_PIN 18
#define UART_PORT UART_NUM_1
#define RX_BUF_SIZE 1024

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
    uart_driver_install(UART_PORT, RX_BUF_SIZE * 2, 0, 0, NULL, 0);

    uart_param_config(UART_PORT, &uart_config);

    uart_set_pin(UART_PORT, TXD_PIN, RXD_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
}

void app_main(void)
{
    init_xbee_uart();
    char *data = "test message\n";

    ESP_LOGI("main", "running send loop");

    while (1)
    {
        int n = uart_write_bytes(UART_PORT, data, strlen(data));
        ESP_LOGI("main", "Sent %d bytes over UART", n);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}