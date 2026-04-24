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
    ):
        self.app = app
        self.pin = pin
        self.name = name
        self.timeout = timeout
        self.debounce = debounce
        self.bouncetime = bouncetime
        self.decoder = decoder
        self.accept_one_pulse = accept_one_pulse

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.pulse_active = False
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

        # If too much time passed → treat as new signal
        if self.pulse_active and (now - self.last_pulse_time) > 0.2:
            self.pulse_count = 0

        with self.lock:
            if self.last_pulse_time and (now - self.last_pulse_time) < self.debounce:
                return

            self.pulse_count += 1
            self.last_pulse_time = now
            self.pulse_active = True

    def _poll_finalize(self):
        now = time.monotonic()
        if hasattr(self, "cooldown_until") and time.monotonic() < self.cooldown_until:
            return

        with self.lock:
            should_finalize = (
                self.pulse_active
                and self.last_pulse_time
                and (now - self.last_pulse_time) > self.timeout
            )

            if not should_finalize:
                self.app.after(10, self._poll_finalize)
                return

            pulses = self.pulse_count

            self.pulse_count = 0
            self.last_pulse_time = 0.0
            self.pulse_active = False
        """ 
        # Reject weird tiny pulse trains (noise bursts)
        if pulses < 2:
            self.app.log(f"{self.name}: ignored noise ({pulses} pulse)")
            return
        """
        value = self.decoder(pulses)

        if value > 0:
            if pulses == 1 and not self.accept_one_pulse:
                self.app.log(f"{self.name}: rejected 1-pulse value for stability")
            else:
                self.app.log(f"{self.name}: {pulses} pulse(s) -> ₱{value}")
                self.app.queue_cash(value)
        else:
            self.app.log(f"{self.name}: invalid pulse count {pulses}, ignored")

        self.app.after(10, self._poll_finalize)
        self.cooldown_until = time.monotonic() + 1.0

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
            timeout=0.7,
            debounce=0.06,
            bouncetime=50,
            decoder=decode_coin,
            accept_one_pulse=False,  # set True later if ₱1 becomes stable
        )

        self.bill_acceptor = MoneyPulseAcceptor(
            app,
            pin=24,
            name="bill",
            timeout=1.0,
            debounce=0.08,
            bouncetime=50,
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