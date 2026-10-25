"""Serialize each bus transaction with its TCA9548A channel selection.

Selection is not held across sensor conversion delays: each operation reselects
its own channel and disconnects it before allowing another reader to proceed.
"""
import threading


class I2CRouter:
    def __init__(self, mux=None, factory=None):
        self.mux = mux or {}
        self.factory = factory
        self.buses = {}
        self.lock = threading.RLock()

    def route(self, bus=1, channel=None):
        if channel is not None:
            if not self.mux.get('enabled'):
                raise ValueError('A mux channel requires i2c_mux.enabled=true')
            if bus != self.mux.get('bus',1):
                raise ValueError('Sensor bus must match the multiplexer bus')
            if type(channel) is not int or not 0 <= channel <= 7:
                raise ValueError('TCA9548A channel must be 0..7')
        return RoutedBus(self,bus,channel)

    def call(self, bus, channel, operation, *args):
        with self.lock:
            if bus not in self.buses:
                factory = self.factory
                if factory is None:
                    from smbus2 import SMBus
                    factory = SMBus
                self.buses[bus] = factory(bus)
            device = self.buses[bus]
            switched = self.mux.get('enabled') and bus == self.mux.get('bus',1)
            address = self.mux.get('address',0x70)
            if switched:
                device.write_byte(address,0 if channel is None else 1 << channel)
            try:
                if operation == 'read_bytes':
                    from smbus2 import i2c_msg
                    message = i2c_msg.read(*args)
                    device.i2c_rdwr(message)
                    return bytes(message)
                return getattr(device,operation)(*args)
            finally:
                if switched:
                    device.write_byte(address,0)

    def close(self):
        with self.lock:
            for bus in self.buses.values():
                bus.close()
            self.buses.clear()


class RoutedBus:
    def __init__(self,router,bus,channel):
        self.router,self.bus,self.channel = router,bus,channel
    def read_byte_data(self,*args):
        return self.router.call(self.bus,self.channel,'read_byte_data',*args)
    def read_i2c_block_data(self,*args):
        return self.router.call(self.bus,self.channel,'read_i2c_block_data',*args)
    def write_byte_data(self,*args):
        return self.router.call(self.bus,self.channel,'write_byte_data',*args)
    def write_i2c_block_data(self,*args):
        return self.router.call(self.bus,self.channel,'write_i2c_block_data',*args)
    def read_bytes(self,*args):
        return self.router.call(self.bus,self.channel,'read_bytes',*args)
    def close(self):
        # Sensor failures must not close a shared physical bus used by the IMU.
        pass
