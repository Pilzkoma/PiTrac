// teensy_strobe.ino — IR strobe controller firmware for Jetson LM
//
// Architecture: Jetson computes the pulse-train intervals (ms) for fast
// (driver/iron swing) and slow (putter) modes from PiTrac's existing
// BuildPulseTrain math, then pushes them once at startup via USB serial.
// A GPIO pulse from the Jetson on FIRE_PIN kicks off the configured pulse
// train; this firmware generates the LED-gate waveform with sub-microsecond
// precision via Teensy 4.0's hardware-timer-backed delayMicroseconds().
//
// Wire protocol (text, line-terminated, 115200 baud — baud ignored on
// Teensy native USB but works in any terminal):
//   PULSES_FAST,3.5,2.8,2.1,1.5,0   → OK | ERR <reason>
//   PULSES_SLOW,15,12,10,8,0        → OK | ERR <reason>
//   ON_BITS,4                       → OK
//   BAUD,38400                      → OK    (computes on_pulse_us = on_bits/baud*1e6)
//   MODE,FAST | MODE,SLOW           → OK
//   READY?                          → READY | WAITING_SETUP
//   STATUS                          → multi-field state dump
//   TEST_FIRE                       → FIRED  (manual fire without Jetson GPIO)
//   RUN[,max_ms]                    → OK | ERR <reason>   continuous strobe
//   STOP                            → OK <pulses fired>
//   TRIG_ARM | TRIG_DISARM          → OK    camera trigger lines driven / released
//   SHOT,<mask>,<delay_us>,<pulse_us> → OK | ERR <reason>  trigger cameras, flash
//
// Camera trigger (added 2026-11-12). The B0332 boards (UC-844) have a trigger
// input at pad F: ~3 kOhm pull-up to 3.3 V, a frame per RISING edge once the
// camera is in trigger mode (UVC exposure_auto_priority=1). CAM1_TRIG / CAM2_TRIG
// drive those pads directly. Disarmed they are inputs (high impedance) and the
// cameras behave as if nothing were connected; armed they idle HIGH. SHOT pulls
// the lines in <mask> (bit 0 = cam1, bit 1 = cam2) LOW for TRIG_LOW_US and
// releases them HIGH - that rising edge is t0 - then fires one flash of
// <pulse_us> (0 = no flash) at t0 + <delay_us>, timed on the cycle counter.
// Interrupts stay on, so USB service can add a few microseconds. Purpose first:
// measure when each camera actually exposes after its edge
// (sp1_vision/trigger_sweep.py). SHOT is refused while RUN is active.
//
// Continuous strobe (added 2026-11-11). The UVC cameras free-run without a
// trigger input and deliver frames 11-20 ms late, so reacting to a hit is
// impossible; instead the strobe runs continuously while armed, both cameras
// expose nearly the whole frame period, and the shot is found afterwards in a
// ring buffer (sp1_vision/strobe_runs/README.md). RUN repeats the ACTIVE
// mode's interval list cyclically - each entry is ON for on_pulse_us, then off
// for the interval - until STOP or max_ms (default 60 s, cap 10 min). A
// trailing 0 (the end marker of a one-shot train) is ignored; other zero
// intervals are refused, as is a duty cycle above MAX_RUN_DUTY. While running,
// the FIRE pin and TEST_FIRE are ignored and the status LED is off.
// Timing is polled in loop(): the pulse width is a blocking
// delayMicroseconds (exact), the schedule accumulates without drift, and the
// serial handling between pulses costs at most a few microseconds of jitter
// on the start of a pulse.
//
// Flash via Arduino IDE + Teensyduino add-on. Pin map below.

#include <Arduino.h>

constexpr uint8_t FIRE_PIN   = 2;   // input from Jetson GPIO (RISING edge)
constexpr uint8_t LED_GATE   = 3;   // output to MOSFET gate
constexpr uint8_t STATUS_LED = 13;  // onboard LED — slow blink = waiting setup, solid = ready
constexpr uint8_t CAM1_TRIG  = 4;   // to pad F of camera 1 (G to GND)
constexpr uint8_t CAM2_TRIG  = 5;   // to pad F of camera 2

constexpr uint32_t TRIG_LOW_US        = 10;      // camera needs >= 2 us
constexpr uint32_t SHOT_MAX_DELAY_US  = 100000;
constexpr uint32_t SHOT_MAX_PULSE_US  = 1000;
constexpr uint32_t SHOT_MIN_SPACING_US = 5000;   // LED protection between SHOTs

constexpr size_t MAX_INTERVALS    = 64;
constexpr size_t SERIAL_BUF_SIZE  = 512;
constexpr uint32_t BOOT_WAIT_MS   = 1000;
constexpr uint32_t BLINK_PERIOD_MS = 500;

constexpr uint32_t RUN_DEFAULT_MAX_MS = 60000;
constexpr uint32_t RUN_CAP_MAX_MS     = 600000;
constexpr float    MAX_RUN_DUTY       = 0.25f;   // CCTV illuminators, rated continuous

enum class State : uint8_t { WAITING_SETUP, READY, FIRING, RUNNING };
enum class Mode  : uint8_t { FAST, SLOW };

volatile State current_state = State::WAITING_SETUP;
Mode  active_mode = Mode::FAST;

float  pulse_intervals_fast_ms[MAX_INTERVALS];
size_t num_pulse_intervals_fast = 0;
bool   fast_received = false;

float  pulse_intervals_slow_ms[MAX_INTERVALS];
size_t num_pulse_intervals_slow = 0;
bool   slow_received = false;

uint16_t on_bits      = 0;
uint32_t baud_rate    = 0;
uint32_t on_pulse_us  = 0;
bool     on_bits_received = false;
bool     baud_received    = false;

char   serial_buf[SERIAL_BUF_SIZE];
size_t serial_buf_pos = 0;

uint32_t last_blink_ms = 0;

// Continuous strobe state (RUN / STOP).
const float* run_intervals = nullptr;
size_t   run_n          = 0;
size_t   run_idx        = 0;
uint32_t run_next_us    = 0;
uint32_t run_started_ms = 0;
uint32_t run_max_ms     = RUN_DEFAULT_MAX_MS;
uint32_t run_pulses     = 0;

// Camera trigger state (TRIG_ARM / SHOT).
bool     trig_armed     = false;
bool     shot_fired     = false;
uint32_t last_shot_us   = 0;

// Forward decls
void armTrigger(bool on);
void shot(char* args);
void runStep();
void startRun(char* args);
void stopRun();
void onFire();
void executePulseTrain();
void handleLine(char* line);
void handlePulses(char* args, float* dst, size_t* count_dst, bool* received_flag);
bool parseFloatList(char* args, float* dst, size_t max_count, size_t* out_count);
void recomputeOnPulseUs();
void updateState();
void sendOk();
void sendErr(const char* reason);

void setup() {
    pinMode(FIRE_PIN,   INPUT);
    pinMode(LED_GATE,   OUTPUT);
    pinMode(STATUS_LED, OUTPUT);
    pinMode(CAM1_TRIG,  INPUT);     // disarmed: released, the camera's pull-up holds F
    pinMode(CAM2_TRIG,  INPUT);
    digitalWriteFast(LED_GATE,   LOW);
    digitalWriteFast(STATUS_LED, LOW);

    Serial.begin(115200);
    uint32_t t0 = millis();
    while (!Serial && (millis() - t0) < BOOT_WAIT_MS) { /* spin */ }
    Serial.println("BOOT teensy_strobe firmware v0.2 (camera trigger)");

    attachInterrupt(digitalPinToInterrupt(FIRE_PIN), onFire, RISING);
}

void loop() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            serial_buf[serial_buf_pos] = '\0';
            if (serial_buf_pos > 0) {
                handleLine(serial_buf);
            }
            serial_buf_pos = 0;
        } else if (serial_buf_pos < SERIAL_BUF_SIZE - 1) {
            serial_buf[serial_buf_pos++] = c;
        } else {
            sendErr("line too long");
            serial_buf_pos = 0;
        }
    }

    if (current_state == State::RUNNING) {
        runStep();
        return;
    }

    const uint32_t now = millis();
    if (current_state == State::WAITING_SETUP) {
        if (now - last_blink_ms >= BLINK_PERIOD_MS) {
            digitalToggleFast(STATUS_LED);
            last_blink_ms = now;
        }
    } else if (current_state == State::READY) {
        digitalWriteFast(STATUS_LED, HIGH);
    }
    // FIRING is short-lived — handled inline in executePulseTrain
}

// ISR — entry from Jetson GPIO trigger. Detaches itself for the duration of
// the pulse train so a glitch can't double-fire.
void onFire() {
    if (current_state != State::READY) return;
    detachInterrupt(digitalPinToInterrupt(FIRE_PIN));
    current_state = State::FIRING;
    executePulseTrain();
    current_state = State::READY;
    attachInterrupt(digitalPinToInterrupt(FIRE_PIN), onFire, RISING);
}

void executePulseTrain() {
    const float* intervals = (active_mode == Mode::FAST)
                              ? pulse_intervals_fast_ms
                              : pulse_intervals_slow_ms;
    const size_t n = (active_mode == Mode::FAST)
                      ? num_pulse_intervals_fast
                      : num_pulse_intervals_slow;
    if (n == 0 || on_pulse_us == 0) return;

    digitalWriteFast(STATUS_LED, LOW);
    for (size_t i = 0; i < n; ++i) {
        digitalWriteFast(LED_GATE, HIGH);
        delayMicroseconds(on_pulse_us);
        digitalWriteFast(LED_GATE, LOW);
        const uint32_t off_us = (uint32_t)(intervals[i] * 1000.0f);
        if (off_us > 0) {
            delayMicroseconds(off_us);
        }
    }
    digitalWriteFast(LED_GATE,   LOW);
    digitalWriteFast(STATUS_LED, HIGH);
}

void handleLine(char* line) {
    char* comma = strchr(line, ',');
    char* args  = nullptr;
    if (comma) {
        *comma = '\0';
        args = comma + 1;
    }

    if (strcmp(line, "PULSES_FAST") == 0) {
        handlePulses(args, pulse_intervals_fast_ms,
                     &num_pulse_intervals_fast, &fast_received);
    } else if (strcmp(line, "PULSES_SLOW") == 0) {
        handlePulses(args, pulse_intervals_slow_ms,
                     &num_pulse_intervals_slow, &slow_received);
    } else if (strcmp(line, "ON_BITS") == 0) {
        if (!args) { sendErr("ON_BITS missing arg"); return; }
        long v = atol(args);
        if (v < 1 || v > 64) { sendErr("ON_BITS out of range 1..64"); return; }
        on_bits = (uint16_t)v;
        on_bits_received = true;
        recomputeOnPulseUs();
        sendOk();
    } else if (strcmp(line, "BAUD") == 0) {
        if (!args) { sendErr("BAUD missing arg"); return; }
        long v = atol(args);
        if (v < 1) { sendErr("BAUD must be > 0"); return; }
        baud_rate = (uint32_t)v;
        baud_received = true;
        recomputeOnPulseUs();
        sendOk();
    } else if (strcmp(line, "MODE") == 0) {
        if (!args) { sendErr("MODE missing arg"); return; }
        if      (strcmp(args, "FAST") == 0) active_mode = Mode::FAST;
        else if (strcmp(args, "SLOW") == 0) active_mode = Mode::SLOW;
        else { sendErr("MODE must be FAST or SLOW"); return; }
        sendOk();
    } else if (strcmp(line, "READY?") == 0) {
        Serial.println(current_state == State::WAITING_SETUP ? "WAITING_SETUP" : "READY");
    } else if (strcmp(line, "TEST_FIRE") == 0) {
        if (current_state != State::READY) { sendErr("not READY"); return; }
        // Inline (no ISR) so the user can drive this from a serial terminal
        // without the Jetson present.
        detachInterrupt(digitalPinToInterrupt(FIRE_PIN));
        current_state = State::FIRING;
        executePulseTrain();
        current_state = State::READY;
        attachInterrupt(digitalPinToInterrupt(FIRE_PIN), onFire, RISING);
        Serial.println("FIRED");
    } else if (strcmp(line, "RUN") == 0) {
        startRun(args);
    } else if (strcmp(line, "STOP") == 0) {
        const uint32_t fired = run_pulses;
        stopRun();
        Serial.print("OK ");
        Serial.println(fired);
    } else if (strcmp(line, "STATUS") == 0) {
        Serial.print("STATE=");
        switch (current_state) {
            case State::WAITING_SETUP: Serial.print("WAITING_SETUP"); break;
            case State::READY:         Serial.print("READY");         break;
            case State::FIRING:        Serial.print("FIRING");        break;
            case State::RUNNING:       Serial.print("RUNNING");       break;
        }
        Serial.print(" MODE=");        Serial.print(active_mode == Mode::FAST ? "FAST" : "SLOW");
        Serial.print(" ON_BITS=");     Serial.print(on_bits);
        Serial.print(" BAUD=");        Serial.print(baud_rate);
        Serial.print(" ON_PULSE_US="); Serial.print(on_pulse_us);
        Serial.print(" N_FAST=");      Serial.print(num_pulse_intervals_fast);
        Serial.print(" N_SLOW=");      Serial.print(num_pulse_intervals_slow);
        Serial.print(" TRIG=");        Serial.print(trig_armed ? "ARMED" : "OFF");
        Serial.print(" RUN_PULSES=");  Serial.println(run_pulses);
    } else if (strcmp(line, "TRIG_ARM") == 0) {
        armTrigger(true);
        sendOk();
    } else if (strcmp(line, "TRIG_DISARM") == 0) {
        armTrigger(false);
        sendOk();
    } else if (strcmp(line, "SHOT") == 0) {
        shot(args);
    } else {
        sendErr("unknown command");
    }
}

void handlePulses(char* args, float* dst, size_t* count_dst, bool* received_flag) {
    if (!args) { sendErr("missing intervals"); return; }
    size_t count = 0;
    if (!parseFloatList(args, dst, MAX_INTERVALS, &count)) {
        sendErr("interval parse failed");
        return;
    }
    if (count == 0) { sendErr("empty interval list"); return; }
    *count_dst     = count;
    *received_flag = true;
    updateState();
    sendOk();
}

bool parseFloatList(char* args, float* dst, size_t max_count, size_t* out_count) {
    size_t n = 0;
    char*  p = args;
    while (*p && n < max_count) {
        char* end;
        float v = strtof(p, &end);
        if (end == p) return false;
        dst[n++] = v;
        p = end;
        if (*p == ',') { p++; continue; }
        if (*p == '\0') break;
        return false;
    }
    *out_count = n;
    return true;
}

void recomputeOnPulseUs() {
    if (on_bits_received && baud_received && baud_rate > 0) {
        on_pulse_us = (uint32_t)(((uint64_t)on_bits * 1000000ULL) / baud_rate);
    }
    updateState();
}

void updateState() {
    if (current_state == State::FIRING) return;
    const bool ready = on_bits_received && baud_received
                       && (fast_received || slow_received) && on_pulse_us > 0;
    current_state = ready ? State::READY : State::WAITING_SETUP;
}

// --- continuous strobe -----------------------------------------------------

void startRun(char* args) {
    if (current_state == State::RUNNING) { sendErr("already running"); return; }
    if (current_state != State::READY)   { sendErr("not READY"); return; }
    const float* iv = (active_mode == Mode::FAST) ? pulse_intervals_fast_ms
                                                  : pulse_intervals_slow_ms;
    size_t n = (active_mode == Mode::FAST) ? num_pulse_intervals_fast
                                           : num_pulse_intervals_slow;
    if (n > 0 && iv[n - 1] == 0.0f) n--;          // one-shot end marker
    if (n == 0) { sendErr("no intervals"); return; }
    float on_total_us = 0.0f, cycle_us = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        if (iv[i] <= 0.0f) { sendErr("zero interval in a RUN pattern"); return; }
        on_total_us += (float)on_pulse_us;
        cycle_us    += (float)on_pulse_us + iv[i] * 1000.0f;
    }
    if (on_total_us / cycle_us > MAX_RUN_DUTY) { sendErr("duty cycle above limit"); return; }

    uint32_t max_ms = RUN_DEFAULT_MAX_MS;
    if (args) {
        long v = atol(args);
        if (v < 1) { sendErr("RUN max_ms must be > 0"); return; }
        max_ms = (uint32_t)v;
    }
    if (max_ms > RUN_CAP_MAX_MS) max_ms = RUN_CAP_MAX_MS;

    run_intervals  = iv;
    run_n          = n;
    run_idx        = 0;
    run_pulses     = 0;
    run_max_ms     = max_ms;
    run_started_ms = millis();
    run_next_us    = micros();
    detachInterrupt(digitalPinToInterrupt(FIRE_PIN));
    digitalWriteFast(STATUS_LED, LOW);
    current_state = State::RUNNING;
    sendOk();
}

void runStep() {
    if (millis() - run_started_ms >= run_max_ms) { stopRun(); return; }
    if ((int32_t)(micros() - run_next_us) < 0) return;
    digitalWriteFast(LED_GATE, HIGH);
    delayMicroseconds(on_pulse_us);
    digitalWriteFast(LED_GATE, LOW);
    run_pulses++;
    run_next_us += on_pulse_us + (uint32_t)(run_intervals[run_idx] * 1000.0f);
    run_idx = (run_idx + 1) % run_n;
}

void stopRun() {
    if (current_state != State::RUNNING) return;
    digitalWriteFast(LED_GATE, LOW);
    current_state = State::READY;
    updateState();
    attachInterrupt(digitalPinToInterrupt(FIRE_PIN), onFire, RISING);
}

// --- camera trigger --------------------------------------------------------

void armTrigger(bool on) {
    if (on) {
        // Data register HIGH before the pin becomes an output, so arming never
        // drives a LOW glitch onto F (a LOW-HIGH would trigger a frame).
        digitalWriteFast(CAM1_TRIG, HIGH);
        digitalWriteFast(CAM2_TRIG, HIGH);
        pinMode(CAM1_TRIG, OUTPUT);
        pinMode(CAM2_TRIG, OUTPUT);
        digitalWriteFast(CAM1_TRIG, HIGH);
        digitalWriteFast(CAM2_TRIG, HIGH);
    } else {
        pinMode(CAM1_TRIG, INPUT);
        pinMode(CAM2_TRIG, INPUT);
    }
    trig_armed = on;
}

static bool nextLong(char** p, long* out) {
    if (!*p || !**p) return false;
    char* end;
    *out = strtol(*p, &end, 10);
    if (end == *p) return false;
    *p = (*end == ',') ? end + 1 : end;
    return true;
}

void shot(char* args) {
    if (current_state == State::RUNNING) { sendErr("RUN active"); return; }
    if (!trig_armed) { sendErr("not armed"); return; }
    long mask, delay_us, pulse_us;
    char* p = args;
    if (!nextLong(&p, &mask) || !nextLong(&p, &delay_us) || !nextLong(&p, &pulse_us)) {
        sendErr("SHOT needs mask,delay_us,pulse_us"); return;
    }
    if (mask < 1 || mask > 3) { sendErr("mask must be 1..3"); return; }
    if (delay_us < 0 || delay_us > (long)SHOT_MAX_DELAY_US) { sendErr("delay out of range"); return; }
    if (pulse_us < 0 || pulse_us > (long)SHOT_MAX_PULSE_US) { sendErr("pulse out of range"); return; }
    if (shot_fired && (micros() - last_shot_us) < SHOT_MIN_SPACING_US) {
        sendErr("too soon after last SHOT"); return;
    }

    const uint32_t cycles_per_us = F_CPU_ACTUAL / 1000000;
    detachInterrupt(digitalPinToInterrupt(FIRE_PIN));

    if (mask & 1) digitalWriteFast(CAM1_TRIG, LOW);
    if (mask & 2) digitalWriteFast(CAM2_TRIG, LOW);
    delayMicroseconds(TRIG_LOW_US);
    digitalWriteFast(CAM1_TRIG, HIGH);
    digitalWriteFast(CAM2_TRIG, HIGH);
    const uint32_t c0 = ARM_DWT_CYCCNT;            // t0: the rising edge

    if (pulse_us > 0) {
        const uint32_t wait = (uint32_t)delay_us * cycles_per_us;
        while ((ARM_DWT_CYCCNT - c0) < wait) { /* spin */ }
        digitalWriteFast(LED_GATE, HIGH);
        delayMicroseconds((uint32_t)pulse_us);
        digitalWriteFast(LED_GATE, LOW);
    }

    last_shot_us = micros();
    shot_fired = true;
    if (current_state != State::RUNNING) {
        attachInterrupt(digitalPinToInterrupt(FIRE_PIN), onFire, RISING);
    }
    sendOk();
}

void sendOk()  { Serial.println("OK"); }
void sendErr(const char* reason) {
    Serial.print("ERR ");
    Serial.println(reason);
}
