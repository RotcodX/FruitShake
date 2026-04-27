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
        process_delay=0.2,
        shared_processing_lock=None,
        
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
        self.process_delay = process_delay
        self.shared_processing_lock = shared_processing_lock

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.last_interrupt_time = 0.0
        self.pulse_active = False
        self.last_debug_log = 0.0
        self.first_pulse_time = 0.0
        self.processing_until = 0.0

        self.debug_status_interval = 3.0
        self.last_status_log = 0.0

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

        self.app.after(100, self._poll_finalize)

    def _shared_processing_active(self):
        if self.shared_processing_lock is None:
            return False
        return bool(self.shared_processing_lock.get("active", False))

    def _set_shared_processing(self, active):
        if self.shared_processing_lock is not None:
            self.shared_processing_lock["active"] = bool(active)

    def _on_pulse(self, channel):
        now = time.monotonic()

        # Ignore pulses while another acceptor is being processed.
        if self._shared_processing_active():
            return

        # Ignore pulses during this acceptor's short reset delay.
        if now < self.processing_until:
            return

        with self.lock:
            if self.last_interrupt_time and (now - self.last_interrupt_time) < self.debounce:
                return

            if self.pulse_count == 0:
                self.first_pulse_time = now
                self.app.log(f"{self.name}: signal detected")

            self.pulse_count += 1
            self.last_pulse_time = now
            self.last_interrupt_time = now
            self.pulse_active = True

            if now - self.last_debug_log >= self.debug_cooldown:
                self.app.log(f"{self.name}: reading pulses... ({self.pulse_count})")
                self.last_debug_log = now

    def _debug_status(self, now):
        if now - self.last_status_log < self.debug_status_interval:
            return

        with self.lock:
            pulses = self.pulse_count
            active = self.pulse_active
            last_time = self.last_pulse_time
            first_time = self.first_pulse_time

        age_since_last = (now - last_time) if last_time else 0
        age_since_first = (now - first_time) if first_time else 0

        self.app.log(
            f"{self.name}: STATUS active={active}, "
            f"pulses={pulses}, "
            f"since_last={age_since_last:.2f}s, "
            f"since_first={age_since_first:.2f}s"
        )

        self.last_status_log = now

    def _poll_finalize(self):
        now = time.monotonic()

        self._debug_status(now)

        with self.lock:
            pulse_active = self.pulse_active
            last_time = self.last_pulse_time
            pulses = self.pulse_count

        should_finalize = (
            pulse_active
            and last_time
            and (now - last_time) > self.timeout
            and not self._shared_processing_active()
        )

        if not should_finalize:
            self.app.after(100, self._poll_finalize)
            return

        self._set_shared_processing(True)

        with self.lock:
            pulses = self.pulse_count
            self.pulse_count = 0
            self.last_pulse_time = 0.0
            self.last_interrupt_time = 0.0
            self.pulse_active = False
            self.first_pulse_time = 0.0
            self.last_debug_log = 0.0
            self.processing_until = time.monotonic() + self.process_delay

        self.app.log(f"{self.name}: FINALIZING with {pulses} pulses")

        value = self.decoder(pulses)

        if value > 0:
            if pulses == 1 and not self.accept_one_pulse:
                self.app.log(f"{self.name}: rejected 1-pulse value for stability")
            else:
                self.app.log(f"{self.name}: {pulses} pulse(s) -> ₱{value}")
                self.app.queue_cash(value)
        else:
            self.app.log(f"{self.name}: invalid pulse count {pulses}, ignored")

        def unlock_processing():
            self._set_shared_processing(False)

        self.app.after(int(self.process_delay * 1000), unlock_processing)
        self.app.after(100, self._poll_finalize)
 
def decode_coin(pulses):
    if 1 <= pulses <= 3:
        return 0 # 1 peso coin pulses are ignored and just adds nothing to payment
    if 4 <= pulses <= 7:
        return 5
    if 8 <= pulses <= 13:
        return 10
    return 0

def decode_bill(pulses):
    if 15 <= pulses <= 35:
        return 20
    if 36 <= pulses <= 80:
        return 50
    if 81 <= pulses <= 170:
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
        self.relays = RelayController([23, 24, 27, 22, 5, 6, 25, 8])

    def dispense_cup(self, seconds):
        print("Dispensing cup.")
        self.relays.pulse(23, seconds)

    def add_liquid(self, seconds):
        print(f"Dispensing liquid for {seconds}s.")
        self.relays.pulse(24, seconds)

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

        # Shared lock so coin and bill do not process at the exact same time.
        self.money_processing_lock = {"active": False}

        self.coin_acceptor = MoneyPulseAcceptor(
            app,
            pin=17,
            name="coin",
            timeout=0.7,
            debounce=0.03,
            bouncetime=5,
            decoder=decode_coin,
            accept_one_pulse=False,  # keep False until ₱1 is stable
            debug_cooldown=0.5,
            process_delay=0.2,
            shared_processing_lock=self.money_processing_lock,
        )

        self.bill_acceptor = MoneyPulseAcceptor(
            app,
            pin=24,  # keep your current bill GPIO unless you rewired to GPIO 18
            name="bill",
            timeout=4.0,
            debounce=0.1,
            bouncetime=15,
            decoder=decode_bill,
            accept_one_pulse=False,
            debug_cooldown=0.5,
            process_delay=0.5,
            shared_processing_lock=None,
        )

        # outputs
        self.servo = None
