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
//
// Flash via Arduino IDE + Teensyduino add-on. Pin map below.

#include <Arduino.h>

constexpr uint8_t FIRE_PIN   = 2;   // input from Jetson GPIO (RISING edge)
constexpr uint8_t LED_GATE   = 3;   // output to MOSFET gate
constexpr uint8_t STATUS_LED = 13;  // onboard LED — slow blink = waiting setup, solid = ready

constexpr size_t MAX_INTERVALS    = 64;
constexpr size_t SERIAL_BUF_SIZE  = 512;
constexpr uint32_t BOOT_WAIT_MS   = 1000;
constexpr uint32_t BLINK_PERIOD_MS = 500;

enum class State : uint8_t { WAITING_SETUP, READY, FIRING };
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

// Forward decls
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
    digitalWriteFast(LED_GATE,   LOW);
    digitalWriteFast(STATUS_LED, LOW);

    Serial.begin(115200);
    uint32_t t0 = millis();
    while (!Serial && (millis() - t0) < BOOT_WAIT_MS) { /* spin */ }
    Serial.println("BOOT teensy_strobe firmware v0.1");

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
    } else if (strcmp(line, "STATUS") == 0) {
        Serial.print("STATE=");
        switch (current_state) {
            case State::WAITING_SETUP: Serial.print("WAITING_SETUP"); break;
            case State::READY:         Serial.print("READY");         break;
            case State::FIRING:        Serial.print("FIRING");        break;
        }
        Serial.print(" MODE=");        Serial.print(active_mode == Mode::FAST ? "FAST" : "SLOW");
        Serial.print(" ON_BITS=");     Serial.print(on_bits);
        Serial.print(" BAUD=");        Serial.print(baud_rate);
        Serial.print(" ON_PULSE_US="); Serial.print(on_pulse_us);
        Serial.print(" N_FAST=");      Serial.print(num_pulse_intervals_fast);
        Serial.print(" N_SLOW=");      Serial.println(num_pulse_intervals_slow);
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

void sendOk()  { Serial.println("OK"); }
void sendErr(const char* reason) {
    Serial.print("ERR ");
    Serial.println(reason);
}
