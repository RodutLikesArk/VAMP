"""Picamera2 MJPEG; optional and independent from the control loop."""
import io
import threading


class Frames(io.BufferedIOBase):
    def __init__(self):
        super().__init__()
        self.condition = threading.Condition()
        self.frame = None
        self.sequence = 0

    def write(self, data):
        with self.condition:
            self.frame = bytes(data)
            self.sequence += 1
            self.condition.notify_all()
        return len(data)


class Camera:
    def __init__(self, config, simulate):
        self.frames = Frames()
        self.camera = None
        self.error = 'Camera disabled in simulation' if simulate else 'Camera disabled in config'
        if simulate or not config['enabled']:
            return
        try:
            from picamera2 import Picamera2
            from picamera2.encoders import JpegEncoder
            from picamera2.outputs import FileOutput
            self.camera = Picamera2()
            video = self.camera.create_video_configuration(main={'size': (config['width'], config['height'])}, controls={'FrameRate': config['fps']})
            self.camera.configure(video)
            self.camera.start_recording(JpegEncoder(), FileOutput(self.frames))
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            self.close()

    def close(self):
        if self.camera:
            try:
                self.camera.stop_recording()
            except Exception:
                pass
            self.camera.close()
            self.camera = None
