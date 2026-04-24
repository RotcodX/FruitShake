# hardware.py
import time
import threading
import queue
import time
from decimal import Decimal, ROUND_HALF_UP

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
try:
    from gpiozero import Button, Servo, OutputDevice
except ImportError:
    Button = Servo = OutputDevice = None

class MoneyPulseAcceptor:
    def __init__(
        self,
        app,
        pin,
        name,
        timeout,
        debounce,
        bouncetime,
        decoder,
        accept_one_pulse=False,
        debug_cooldown=0.5,
    ):
        self.app = app
        self.pin = pin
        self.name = name
        self.timeout = timeout
        self.debounce = debounce
        self.bouncetime = bouncetime
        self.decoder = decoder
        self.accept_one_pulse = accept_one_pulse
        self.debug_cooldown = debug_cooldown

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.pulse_active = False
        self.last_debug_log = 0.0
        self.first_pulse_time = 0

        self.lock = threading.Lock()

        self.app.log(f"{self.name}: initializing on GPIO {pin}")

        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        try:
            GPIO.remove_event_detect(pin)
        except Exception:
            pass

        try:
            GPIO.add_event_detect(
                pin,
                GPIO.FALLING,
                callback=self._on_pulse,
                bouncetime=bouncetime
            )
            self.app.log(
                f"{self.name}: edge detection enabled on GPIO {pin} "
                f"(timeout={timeout}, debounce={debounce}, bouncetime={bouncetime})"
            )
        except Exception as e:
            self.app.log(f"{self.name}: failed to enable edge detection on GPIO {pin}: {e}")
            raise

        self.app.after(10, self._poll_finalize)

    def _on_pulse(self, channel):
        now = time.monotonic()

        with self.lock:
            # debounce
            if self.last_pulse_time and (now - self.last_pulse_time) < self.debounce:
                return

            # initialize first pulse
            if self.pulse_count == 0:
                self.first_pulse_time = now
                self.app.log(f"{self.name}: signal detected")

            # hard cap (prevents runaway)
            if self.pulse_count > 120:
                return

            self.pulse_count += 1
            self.last_pulse_time = now
            self.pulse_active = True

            # controlled debug
            if now - self.last_debug_log >= self.debug_cooldown:
                self.app.log(f"{self.name}: reading pulses... ({self.pulse_count})")
                self.last_debug_log = now

    def _poll_finalize(self):
        now = time.monotonic()

        # ── STEP 1: safely read shared values (short lock only)
        with self.lock:
            pulse_active = self.pulse_active
            last_time = self.last_pulse_time
            pulses = self.pulse_count
            first_time = getattr(self, "first_pulse_time", 0)

        # ── STEP 2: determine if we should finalize
        should_finalize = (
            pulse_active
            and last_time
            and (now - last_time) > self.timeout
        )

        # ── STEP 3: force finalize if pulse count too high
        if pulses >= 60:
            self.app.log(f"{self.name}: force finalize ({pulses} pulses)")
            should_finalize = True
        if first_time and (now - first_time) > 1.2:
            self.app.log(f"{self.name}: forced by max window")
            should_finalize = True

        # ── STEP 4: force finalize if time window exceeded
        MAX_WINDOW = 1.2
        if first_time and (now - first_time) > MAX_WINDOW:
            self.app.log(f"{self.name}: forced by max window ({pulses} pulses)")
            should_finalize = True

        # ── STEP 5: if not ready, reschedule and exit
        if not should_finalize:
            self.app.after(100, self._poll_finalize)
            return

        # ── STEP 6: reset values safely
        with self.lock:
            pulses = self.pulse_count
            self.pulse_count = 0
            self.last_pulse_time = 0.0
            self.pulse_active = False
            self.first_pulse_time = 0

        # ── STEP 7: processing log
        self.app.log(f"{self.name}: FINALIZING with {pulses} pulses")

        # ── STEP 8: decode
        value = self.decoder(pulses)

        if value > 0:
            if pulses == 1 and not self.accept_one_pulse:
                self.app.log(f"{self.name}: rejected 1-pulse value for stability")
            else:
                self.app.log(f"{self.name}: {pulses} pulse(s) -> ₱{value}")
                self.app.queue_cash(value)
        else:
            self.app.log(f"{self.name}: invalid pulse count {pulses}, ignored")

        # ── STEP 9: ALWAYS reschedule
        self.app.after(10, self._poll_finalize)

def decode_coin(pulses):
    if 1 <= pulses <= 3:
        return 1
    if 4 <= pulses <= 7:
        return 5
    if 8 <= pulses <= 13:
        return 10
    return 0


def decode_bill(pulses):
    if 18 <= pulses <= 30:
        return 20
    if 45 <= pulses <= 70:
        return 50
    if 90 <= pulses <= 130:
        return 100
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
        self.relays = RelayController([23, 18, 27, 22, 5, 6, 25, 8])

    def dispense_cup(self, seconds):
        print("Dispensing cup.")
        self.relays.pulse(23, seconds)

    def add_liquid(self, seconds):
        print(f"Dispensing liquid for {seconds}s.")
        self.relays.pulse(18, seconds)

    def dispense_fruit(self, seconds):
        print(f"Dispensing fruit for {seconds}s.")
        self.relays.pulse(27, seconds)

    def run_blender(self, seconds):
        print(f"Blending for {seconds}s.")
        self.relays.pulse(22, seconds)

    def cleanup(self):
        self.relays.cleanup()

class HardwareManager:
    def __init__(self, app):
        self.app = app

        self.coin_acceptor = MoneyPulseAcceptor(
            app,
            pin=17,
            name="coin",
            timeout=0.4,
            debounce=0.06,
            bouncetime=20,
            decoder=decode_coin,
            accept_one_pulse=False,
        )

        self.bill_acceptor = MoneyPulseAcceptor(
            app,
            pin=24,
            name="bill",
            timeout=0.8,
            debounce=0.05,
            bouncetime=30,
            decoder=decode_bill,
            accept_one_pulse=False,
        )

        # outputs
        self.servo = None
        # self.blender = OutputDevice(23, initial_value=False) if OutputDevice else None # Enable this again when blender gpio is changed

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