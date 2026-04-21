# hardware.py
import time
import threading
import queue
from decimal import Decimal, ROUND_HALF_UP
import RPi.GPIO as GPIO
import time

try:
    from gpiozero import Button, Servo, OutputDevice
except ImportError:
    Button = Servo = OutputDevice = None


class PulseAcceptor:
    def __init__(
        self,
        app,
        pin,
        name="acceptor",
        startup_delay=2.0,
        pulse_timeout=0.3,
        min_valid_pulses=20,
        debounce=0.01,
    ):
        self.app = app
        self.pin = pin
        self.name = name
        self.startup_delay = startup_delay
        self.pulse_timeout = pulse_timeout
        self.min_valid_pulses = min_valid_pulses

        self.start_time = time.monotonic()
        self.pulse_count = 0
        self.last_pulse_time = 0.0

        self.input = Button(pin, pull_up=True, bounce_time=debounce)
        self.input.when_pressed = self._on_pulse

        # poll finalization from Tk thread
        self.app.after(50, self._poll_finalize)

    def _on_pulse(self):
        now = time.monotonic()

        # ignore startup noise
        if now - self.start_time < self.startup_delay:
            return

        self.pulse_count += 1
        self.last_pulse_time = now

    def _poll_finalize(self):
        now = time.monotonic()

        # pulse train ended
        if self.pulse_count > 0 and (now - self.last_pulse_time) > self.pulse_timeout:
            pulses = self.pulse_count
            self.pulse_count = 0

            if pulses >= self.min_valid_pulses:
                amount = float(pulses)  # 1 pulse = 1 peso
                self.app.log(f"{self.name}: valid pulse train = {pulses} pulses -> ₱{amount:.2f}")
                self.app.queue_cash(amount)
            else:
                self.app.log(f"{self.name}: ignored noise ({pulses} pulses)")

        self.app.after(50, self._poll_finalize)

class RelayController:
    def __init__(self, pins):
        self.pins = pins
        GPIO.setmode(GPIO.BCM)

        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)  # OFF (active LOW)

    def all_on(self):
        for pin in self.pins:
            GPIO.output(pin, GPIO.LOW)

    def all_off(self):
        for pin in self.pins:
            GPIO.output(pin, GPIO.HIGH)

    def pulse(self, pin, duration):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(duration)
        GPIO.output(pin, GPIO.HIGH)

    def cleanup(self):
        self.all_off()
        GPIO.cleanup()

class MachineController:
    def __init__(self):
        self.relays = RelayController([17,18,27,22,5,6,25,8])

    def dispense_cup(self):
        print("Dispensing cup...")
        time.sleep(1)

    def add_liquid(self, seconds):
        print(f"Dispensing liquid for {seconds}s...")
        time.sleep(seconds)

    def dispense_fruit(self, seconds):
        print(f"Dispensing fruit for {seconds}s...")
        time.sleep(seconds)

    def run_blender(self, seconds):
        print(f"Blending for {seconds}s...")
        time.sleep(seconds)

class HardwareManager:
    def __init__(self, app):
        self.app = app

        # Change pins to match your wiring
        self.bill_acceptor = PulseAcceptor(app, pin=17, name="bill")
        self.coin_acceptor = PulseAcceptor(app, pin=27, name="coin")

        # outputs
        self.servo = Servo(18) if Servo else None
        self.blender = OutputDevice(23, initial_value=False) if OutputDevice else None

    def open_gate(self):
        if self.servo:
            self.servo.max()

    def close_gate(self):
        if self.servo:
            self.servo.min()

    def blender_on(self):
        if self.blender:
            self.blender.on()

    def blender_off(self):
        if self.blender:
            self.blender.off()