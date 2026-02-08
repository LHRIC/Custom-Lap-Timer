idf_component_register(
    SRCS 
        "src/radio_sender_main.c"
        "src/minmea.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_driver_uart esp_driver_i2c
)