"""AHT10 measurements and digital MQ-2 comparator interpretation."""
import time


class AHT10:
    def __init__(self,bus,address=0x38,sleep=time.sleep,clock=time.monotonic):
        self.bus,self.address,self.sleep,self.clock = bus,address,sleep,clock
        self.bus.write_i2c_block_data(address,0xE1,[0x08,0x00])
        self.sleep(0.04)

    @staticmethod
    def decode(data):
        if len(data) != 6:
            raise ValueError('Incomplete AHT10 reading')
        if data[0] & 0x80:
            raise ValueError('AHT10 measurement still busy')
        if not data[0] & 0x08:
            raise ValueError('AHT10 factory calibration not enabled')
        humidity = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4))*100/1048576
        temperature = (((data[3]&15) << 16) | (data[4] << 8) | data[5])*200/1048576-50
        if not -40 <= temperature <= 85:
            raise ValueError('AHT10 temperature outside specified range')
        return {'temperature_c':temperature,'humidity_percent':humidity}

    def read(self):
        self.bus.write_i2c_block_data(self.address,0xAC,[0x33,0x00])
        self.sleep(0.08)  # The I2C mux lock is released during conversion.
        deadline = self.clock()+0.15
        while True:
            data = self.bus.read_bytes(self.address,6)
            if len(data) != 6:
                raise ValueError('Incomplete AHT10 reading')
            if not data[0] & 0x80:
                return self.decode(data)
            if self.clock() >= deadline:
                raise TimeoutError('AHT10 conversion timed out')
            self.sleep(0.01)


def mq2_state(raw,active_low,elapsed,startup_seconds):
    remaining = max(0.0,startup_seconds-elapsed)
    return {'gas_alarm_raw':bool(raw),'gas_warming_up':remaining>0,
            'gas_warmup_remaining_s':remaining,
            'gas_triggered':None if remaining else (not bool(raw) if active_low else bool(raw))}
