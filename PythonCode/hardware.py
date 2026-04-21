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

class CoinAcceptor:
    def __init__(
        self,
        app,
        pin,
        name="coin",
        pulse_timeout=0.5,   # 500 ms
        noise_filter=0.025   # 25 ms
    ):
        self.app = app
        self.pin = pin
        self.name = name

        self.pulse_timeout = pulse_timeout
        self.noise_filter = noise_filter

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.last_interrupt = 0.0
        self.pulse_active = False

        # GPIO setup
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # interrupt equivalent
        GPIO.add_event_detect(pin, GPIO.FALLING, callback=self._on_pulse, bouncetime=1)

        # polling loop (like Arduino loop)
        self.app.after(50, self._poll_finalize)

    def _on_pulse(self, channel):
        now = time.monotonic()

        # noise filter (same as Arduino)
        if (now - self.last_interrupt) < self.noise_filter:
            return

        self.pulse_count += 1
        self.last_pulse_time = now
        self.pulse_active = True
        self.last_interrupt = now

    def _poll_finalize(self):
        now = time.monotonic()

        if self.pulse_active and (now - self.last_pulse_time) > self.pulse_timeout:
            pulses = self.pulse_count

            coin_value = self.decode_coin(pulses)

            self.app.log(f"{self.name}: pulses={pulses} → value={coin_value}")

            if coin_value > 0:
                self.app.queue_cash(coin_value)

            # reset
            self.pulse_count = 0
            self.pulse_active = False

        self.app.after(50, self._poll_finalize)

    def decode_coin(self, pulses):
        # 1 peso
        if 1 <= pulses <= 2:
            return 1

        # 5 peso
        if 3 <= pulses <= 6:
            return 5

        # 10 peso
        if 7 <= pulses <= 12:
            return 10

        return 0

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