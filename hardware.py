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

DEBUG_CASH_PULSES = False

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
        debug_cooldown=3,
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
        self.enabled = False
        self.last_completed_pulses = 0 # Preserve the most recently completed pulse batch for the UI.
        self.last_decoded_value = None

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.last_interrupt_time = 0.0
        self.pulse_active = False
        self.last_debug_log = 0.0
        self.first_pulse_time = 0.0
        self.processing_until = 0.0

        self.debug_status_interval = 5.0
        self.last_status_log = 0.0

        self.lock = threading.Lock()

        # Track whether GPIO edge detection is currently registered.
        self._edge_detection_enabled = False

        # Track the scheduled pulse-finalization callback.
        self._poll_job = None

        self.app.log(
            f"{self.name}: initializing on GPIO {pin} "
            "(pulse reading initially disabled)"
        )

        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Make sure no previous event detection is registered.
        try:
            GPIO.remove_event_detect(pin)
        except Exception:
            pass

    def _shared_processing_active(self):
        if self.shared_processing_lock is None:
            return False
        return bool(self.shared_processing_lock.get("active", False))

    def _set_shared_processing(self, active):
        if self.shared_processing_lock is not None:
            self.shared_processing_lock["active"] = bool(active)

    def _schedule_poll_finalize(self):
        """Schedule pulse finalization only while this acceptor is enabled."""
        if self.enabled and self._poll_job is None:
            self._poll_job = self.app.after(
                100,
                self._poll_finalize
            )

    def set_enabled(self, enabled):
        """Enable or disable GPIO pulse detection and processing."""
        enabled = bool(enabled)

        with self.lock:
            state_changed = self.enabled != enabled
            self.enabled = enabled

            if state_changed:
                # Clear any unfinished or previous reading.
                self.pulse_count = 0
                self.last_pulse_time = 0.0
                self.last_interrupt_time = 0.0
                self.pulse_active = False
                self.first_pulse_time = 0.0
                self.last_debug_log = 0.0
                self.last_status_log = 0.0
                self.processing_until = 0.0

                self.last_completed_pulses = 0
                self.last_decoded_value = None

        if enabled:
            # Register GPIO pulse detection only when needed.
            if not self._edge_detection_enabled:
                try:
                    GPIO.add_event_detect(
                        self.pin,
                        GPIO.FALLING,
                        callback=self._on_pulse,
                        bouncetime=self.bouncetime
                    )

                    self._edge_detection_enabled = True

                except Exception:
                    with self.lock:
                        self.enabled = False
                    raise

            # Start the finalization loop.
            self._schedule_poll_finalize()

        else:
            # Stop receiving GPIO callbacks.
            if self._edge_detection_enabled:
                try:
                    GPIO.remove_event_detect(self.pin)

                except Exception as e:
                    self.app.log(
                        f"{self.name}: failed to remove GPIO event detection: {e}"
                    )

                finally:
                    self._edge_detection_enabled = False

            # Cancel any scheduled finalization callback.
            if self._poll_job is not None:
                try:
                    self.app.after_cancel(self._poll_job)
                except Exception:
                    pass

                self._poll_job = None

        # Only log actual state changes.
        if state_changed:
            self.app.log(
                f"{self.name}: pulse reading "
                f"{'ENABLED' if enabled else 'DISABLED'}"
            )

    def _on_pulse(self, channel):
        now = time.monotonic()

        """ print(
            f"{self.name}: RAW pulse GPIO={self.pin} "
            f"time={now:.3f}"
        ) """
        
        # Ignore pulses while another acceptor is being processed.
        if self._shared_processing_active():
            return

        # Ignore pulses during this acceptor's short reset delay.
        if now < self.processing_until:
            return

        with self.lock:
            if not self.enabled:
                return

            if self.last_interrupt_time and (
                now - self.last_interrupt_time
            ) < self.debounce:
                return

            if self.pulse_count == 0:
                self.first_pulse_time = now
                self.app.after(
                    0,
                    lambda: self.app.set_cash_indicator(True)
                )
                print(
                    f"{self.name} (BCM GPIO {self.pin}): "
                    f"first pulse detected"
                )

            self.pulse_count += 1
            self.last_pulse_time = now
            self.last_interrupt_time = now
            self.pulse_active = True

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

        """ self.app.log(
            f"{self.name}: STATUS active={active}, "
            f"pulses={pulses}, "
            f"since_last={age_since_last:.2f}s, "
            f"since_first={age_since_first:.2f}s"
        ) """

        self.last_status_log = now

    def _poll_finalize(self):
        self._poll_job = None

        now = time.monotonic()

        with self.lock:
            enabled = self.enabled
            pulse_active = self.pulse_active
            last_time = self.last_pulse_time
            pulses = self.pulse_count

        # Do not perform debugging or finalization while disabled.
        if not enabled:
            return

        # Optional pulse debugging.
        # Uncomment temporarily when investigating acceptor behavior.
        # self._debug_status(now)

        should_finalize = (
            pulse_active
            and last_time
            and (now - last_time) > self.timeout
        )

        if not should_finalize:
            self._schedule_poll_finalize()
            return
        
        self._set_shared_processing(True)

        with self.lock:
            pulses = self.pulse_count
            first_pulse_time = self.first_pulse_time
            self.pulse_count = 0
            self.last_pulse_time = 0.0
            self.last_interrupt_time = 0.0
            self.pulse_active = False
            
            self.first_pulse_time = 0.0
            self.last_debug_log = 0.0
            self.processing_until = time.monotonic() + self.process_delay

        batch_duration = (
            time.monotonic() - first_pulse_time
            if first_pulse_time
            else 0.0
        )

        quiet_duration = (
            time.monotonic() - last_time
            if last_time
            else 0.0
        )

        if DEBUG_CASH_PULSES:
            print(
                f"{self.name} (BCM GPIO {self.pin}): "
                f"FINALIZING with {pulses} pulses | "
                f"batch duration: {batch_duration:.2f}s | "
                f"quiet duration: {quiet_duration:.2f}s"
            )

        value = self.decoder(pulses)

        with self.lock:
            self.last_completed_pulses = pulses
            self.last_decoded_value = value

        if value > 0:
            if pulses == 1 and not self.accept_one_pulse:
                print(f"{self.name}: rejected 1-pulse value for stability")
                self.app.after(0, lambda: self.app.set_cash_indicator(False))
            else:
                print(f"{self.name}: {pulses} pulse(s) -> ₱{value}")
                # Maintenance Mode may inspect pulses without accepting payment.
                if getattr(self.app, "accept_cash_input", False):
                    self.app.queue_cash(value)
                else:
                    print(
                        f"{self.name}: preview only - "
                        f"{pulses} pulses -> ₱{value}"
                    )
                self.app.after(0, lambda: self.app.set_cash_indicator(False))
        else:
            print(f"{self.name}: invalid pulse count {pulses}, ignored")

        def unlock_processing():
            self._set_shared_processing(False)

        self.app.after(int(self.process_delay * 1000), unlock_processing)
        self._schedule_poll_finalize()
 
def decode_coin(pulses):
    if 1 <= pulses <= 3:
        return 0 # 1 peso coin pulses are ignored and just adds nothing to payment
    if 4 <= pulses <= 8:
        return 5
    if 9 <= pulses <= 13:
        return 10
    return 0

def decode_bill(pulses):
    if 15 <= pulses <= 45:
        return 20
    if 46 <= pulses <= 95:
        return 50
    if 96 <= pulses <= 240:
        return 100
    return 0

class RelayController:
    def __init__(self, pins):
        self.pins = pins
        GPIO.setmode(GPIO.BCM)

        for pin in self.pins:
            GPIO.setup(
                pin,
                GPIO.OUT,
                initial=GPIO.HIGH
            )  # 1 / HIGH = OFF (active LOW relay)

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

    def on(self, pin):
        GPIO.output(pin, GPIO.LOW)

    def off(self, pin):
        GPIO.output(pin, GPIO.HIGH)

    def cleanup(self):
        self.all_off()
        self.servo1.value = None
        self.servo2.value = None
        self.servo3.value = None
        self.servo4.value = None
        time.sleep(2)
        GPIO.cleanup()

class MachineController:
    def __init__(self, hardware):
        self.hardware = hardware
        self.relays = RelayController([23, 24, 27, 22, 5, 6, 25, 8])

        # Servo tuning
        self.servo_run_value = 1.0

        # Calibrated neutral value for each continuous-rotation servo.
        # Start at 0.00, then adjust each one individually if necessary.
        self.servo_stop_values = {
            "servo1": 0.00,
            "servo2": 0.00,
            "servo3": 0.00,
            "servo4": 0.00,
        }
        
    # 1
    def dispense_cup(self, seconds):
        print("Dispensing cup.")
        self.relays.pulse(23, seconds)

    # 2
    def dispense_fruit(self, seconds):
        print(f"Dispensing fruit for {seconds}s.")
        self.relays.pulse(24, seconds)

    # 3
    def dispense_ice(self, seconds):
        print(f"Dispensing ice for {seconds}s.")
        self.relays.pulse(27, seconds)

    # 4
    def add_liquid(self, seconds):
        print(f"Dispensing liquid for {seconds}s.")
        self.relays.pulse(22, seconds)

    # 5
    def dispense_addons(self, seconds):
        print(f"Dispensing Add-Ons for {seconds}s.")
        self.run_servo_for_time(self.hardware.servo1,seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo1"])

    # 6
    def run_blender(self, seconds):
        print(f"Blending for {seconds}s.")
        self.run_servo_for_time(self.hardware.servo2, seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo2"])

    # 7
    def dispense_order(self, seconds):
        print(f"Dispensing order for {seconds}s.")
        self.run_servo_for_time(self.hardware.servo3, seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo3"])

    # 8
    def cleaning(self, seconds):
        print(f"Cleaning up for {seconds}s.")
        self.run_servo_for_time(self.hardware.servo4, seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo4"])

    def cleanup(self):
        # Stop and close each servo using its own neutral setting.
        for name, servo in (
            ("servo1", self.hardware.servo1),
            ("servo2", self.hardware.servo2),
            ("servo3", self.hardware.servo3),
            ("servo4", self.hardware.servo4),
        ):
            try:
                servo.value = self.servo_stop_values[name]
                time.sleep(0.2)
            except Exception as e:
                print(f"Could not stop {name}: {e}")

            try:
                servo.close()
            except Exception as e:
                print(f"Could not close {name}: {e}")

        # Switch relays off and clean up GPIO.
        self.relays.cleanup()

    def run_servo_for_time(self, servo, seconds, direction=None):
        if direction is None:
            direction = self.servo_run_value

        # Detach any previous control signal before starting.
        servo.value = None

        try:
            # Start the servo.
            servo.value = direction
            print(f"Servo running for {seconds} seconds.")

            time.sleep(seconds)

        finally:
            # Stop attempt 1: briefly command the midpoint.
            print("Servo stop attempt 1: sending neutral command.")

            try:
                servo.value = self.servo_stop_value
                time.sleep(0.2)

            finally:
                # Stop attempt 2: detach the control signal.
                servo.value = None
                print("Servo stop attempt 2: control signal detached.")

    # Maintenance Mode tests

    def allon(self):
        print(f"Maintenance: All relays on")
        self.relays.all_on()

    def alloff(self):
        print(f"Maintenance: All relays off")
        self.relays.all_off()

    def test_pump1(self, seconds):
        print(f"Maintenance: Pump 1 for {seconds}s")
        self.relays.pulse(23, seconds)

    def test_pump2(self, seconds):
        print(f"Maintenance: Pump 2 for {seconds}s")
        self.relays.pulse(24, seconds)

    def test_pump3(self, seconds):
        print(f"Maintenance: Pump 3 for {seconds}s")
        self.relays.pulse(27, seconds)

    def test_pump4(self, seconds):
        print(f"Maintenance: Pump 4 for {seconds}s")
        self.relays.pulse(22, seconds)

    def test_servo1(self, seconds):
        print(f"Maintenance: Servo 1 for {seconds}s")
        self.run_servo_for_time(self.hardware.servo1,seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo1"])

    def test_servo2(self, seconds):
        print(f"Maintenance: Servo 2 for {seconds}s")
        self.run_servo_for_time(self.hardware.servo2,seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo2"])

    def test_servo3(self, seconds):
        print(f"Maintenance: Servo 3 for {seconds}s")
        self.run_servo_for_time(self.hardware.servo3,seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo3"])

    def test_servo4(self, seconds):
        print(f"Maintenance: Servo 4 for {seconds}s")
        self.run_servo_for_time(self.hardware.servo4, seconds, direction=self.servo_run_value, stop_value=self.servo_stop_values["servo4"])

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
            debug_cooldown=5,
            process_delay=0.2,
            shared_processing_lock=None,
        )

        self.bill_acceptor = MoneyPulseAcceptor(
            app,
            pin=18,  # keep your current bill GPIO unless you rewired to GPIO 18
            name="bill",
            timeout=4.0,
            debounce=0.1,
            bouncetime=15,
            decoder=decode_bill,
            accept_one_pulse=False,
            debug_cooldown=5,
            process_delay=0.5,
            shared_processing_lock=None,
        )

        # Servo
        self.servo1 = Servo(12,
            min_pulse_width=0.001,
            max_pulse_width=0.002
        )
        self.servo2 = Servo(13,
            min_pulse_width=0.001,
            max_pulse_width=0.002
        )
        self.servo3 = Servo(19,
            min_pulse_width=0.001,
            max_pulse_width=0.002
        )
        self.servo4 = Servo(26,
            min_pulse_width=0.001,
            max_pulse_width=0.002
        )

        self.servo1.value = None
        self.servo2.value = None
        self.servo3.value = None
        self.servo4.value = None
