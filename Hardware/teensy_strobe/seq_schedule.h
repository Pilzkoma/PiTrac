// seq_schedule.h - parse and compile the SEQ command's per-period schedule.
//
// Pure C++11, no Arduino headers and no heap, so it is unit-tested on the
// host (host_test/test_seq_schedule.cpp) and included unchanged by teensy_strobe.ino.
//
//   SEQ,<t_us>:<event>,<t_us>:<event>,...
//
// events, in time order:
//   E1 / E2      rising trigger edge on camera 1 / 2 at t; the line is
//                pulled low SEQ_TRIG_LOW_US before it (the camera needs
//                >= 2 us low). At most one edge per camera per schedule.
//   F<pulse_us>  flash (LED gate high) from t for pulse_us,
//                1..SEQ_MAX_PULSE_US; flashes may neither overlap nor touch.
//
// Compiled into pin transitions sorted by time. All times are shifted by
// SEQ_TRIG_LOW_US so that an edge at t = 0 has its low transition at 0:
// transition time = t + SEQ_TRIG_LOW_US (edge, flash start), t (low), etc.
// Ties keep the order in which they were generated.
// On any error seq_parse returns a message and leaves *out untouched.

#ifndef SEQ_SCHEDULE_H
#define SEQ_SCHEDULE_H

#include <stdint.h>
#include <stdlib.h>

constexpr int      SEQ_MAX_EVENTS   = 16;
constexpr uint32_t SEQ_TRIG_LOW_US  = 10;
constexpr uint32_t SEQ_MAX_PULSE_US = 1000;
constexpr uint32_t SEQ_MAX_T_US     = 100000;

constexpr uint8_t SEQ_LINE_CAM1 = 0;
constexpr uint8_t SEQ_LINE_CAM2 = 1;
constexpr uint8_t SEQ_LINE_LED  = 2;

struct SeqTransition {
    uint32_t t_us;
    uint8_t  line;    // SEQ_LINE_*
    uint8_t  level;   // 0 low, 1 high
};

struct SeqSchedule {
    SeqTransition tr[2 * SEQ_MAX_EVENTS];
    uint8_t  n;          // transitions in tr
    uint8_t  events;     // events parsed
    uint32_t end_us;     // time of the last transition
    uint32_t flash_us;   // sum of flash lengths (duty check)
};

inline const char* seq_parse(const char* args, SeqSchedule* out) {
    if (args == nullptr || *args == '\0') return "SEQ needs <t_us>:<event>,...";
    SeqSchedule s = {};
    const char* p = args;
    bool cam_used[2] = {false, false};
    bool have_prev = false;
    uint32_t prev_t = 0;
    uint32_t last_flash_end = 0;
    bool any_flash = false;

    while (true) {
        if (s.events >= SEQ_MAX_EVENTS) return "more than 16 events";
        if (*p < '0' || *p > '9') return "event needs a time";
        char* end;
        const unsigned long t = strtoul(p, &end, 10);
        if (t > SEQ_MAX_T_US) return "event time above 100000 us";
        if (*end != ':') return "event needs <t_us>:<event>";
        p = end + 1;
        if (have_prev && t < prev_t) return "events not in time order";
        const uint32_t ts = (uint32_t)t + SEQ_TRIG_LOW_US;   // shifted time

        if (*p == 'E') {
            const char c = p[1];
            if (c != '1' && c != '2') return "edge must be E1 or E2";
            const int cam = c - '1';
            if (cam_used[cam]) return "one edge per camera per schedule";
            cam_used[cam] = true;
            const uint8_t line = cam == 0 ? SEQ_LINE_CAM1 : SEQ_LINE_CAM2;
            s.tr[s.n++] = {ts - SEQ_TRIG_LOW_US, line, 0};
            s.tr[s.n++] = {ts, line, 1};
            p += 2;
        } else if (*p == 'F') {
            if (p[1] < '0' || p[1] > '9') return "flash needs F<pulse_us>";
            const unsigned long pulse = strtoul(p + 1, &end, 10);
            if (pulse < 1 || pulse > SEQ_MAX_PULSE_US) return "flash 1..1000 us";
            if (any_flash && ts <= last_flash_end) return "flashes overlap";
            any_flash = true;
            last_flash_end = ts + (uint32_t)pulse;
            s.tr[s.n++] = {ts, SEQ_LINE_LED, 1};
            s.tr[s.n++] = {last_flash_end, SEQ_LINE_LED, 0};
            s.flash_us += (uint32_t)pulse;
            p = end;
        } else {
            return "event must be E1, E2 or F<us>";
        }
        s.events++;
        have_prev = true;
        prev_t = (uint32_t)t;

        if (*p == '\0') break;
        if (*p != ',') return "junk after event";
        ++p;
        if (*p == '\0') return "trailing comma";
    }

    // Stable insertion sort by time.
    for (int i = 1; i < s.n; ++i) {
        const SeqTransition x = s.tr[i];
        int j = i - 1;
        while (j >= 0 && s.tr[j].t_us > x.t_us) {
            s.tr[j + 1] = s.tr[j];
            --j;
        }
        s.tr[j + 1] = x;
    }
    s.end_us = s.tr[s.n - 1].t_us;
    *out = s;
    return nullptr;
}

#endif  // SEQ_SCHEDULE_H
