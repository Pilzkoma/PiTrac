// Host test for seq_schedule.h (no Arduino needed). Lives outside the sketch
// folder on purpose: arduino-cli compiles every .cpp next to the .ino, and this
// file's main() then replaced the firmware's. On the Jetson, from the repo root:
//     g++ -std=c++11 -Wall -Wextra -o /tmp/tseq Hardware/teensy_strobe/host_test/test_seq_schedule.cpp && /tmp/tseq
// Prints ALL OK, or the first failing check and exits 1.

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../seq_schedule.h"

static int g_checks = 0;

#define CHECK(cond)                                                         \
    do {                                                                    \
        ++g_checks;                                                         \
        if (!(cond)) {                                                      \
            std::printf("FAIL line %d: %s\n", __LINE__, #cond);             \
            std::exit(1);                                                   \
        }                                                                   \
    } while (0)

static void expect_tr(const SeqSchedule& s, int i, uint32_t t, uint8_t line, uint8_t level) {
    CHECK(s.tr[i].t_us == t);
    CHECK(s.tr[i].line == line);
    CHECK(s.tr[i].level == level);
}

static void test_default_offset_schedule() {
    SeqSchedule s;
    CHECK(seq_parse("0:E1,900:F100,1000:E2,1900:F100", &s) == nullptr);
    CHECK(s.n == 8);
    // cam1 low at 0, its rising edge at 10 (= its t 0 + TRIG_LOW_US)
    expect_tr(s, 0, 0, SEQ_LINE_CAM1, 0);
    expect_tr(s, 1, 10, SEQ_LINE_CAM1, 1);
    expect_tr(s, 2, 910, SEQ_LINE_LED, 1);
    // cam2 low at 1000 and the LED off at 1010 / cam2 high at 1010:
    // equal times keep schedule order, which is fine either way
    expect_tr(s, 3, 1000, SEQ_LINE_CAM2, 0);
    CHECK(s.tr[4].t_us == 1010 && s.tr[5].t_us == 1010);
    CHECK((s.tr[4].line == SEQ_LINE_LED && s.tr[4].level == 0
           && s.tr[5].line == SEQ_LINE_CAM2 && s.tr[5].level == 1)
          || (s.tr[5].line == SEQ_LINE_LED && s.tr[5].level == 0
              && s.tr[4].line == SEQ_LINE_CAM2 && s.tr[4].level == 1));
    expect_tr(s, 6, 1910, SEQ_LINE_LED, 1);
    expect_tr(s, 7, 2010, SEQ_LINE_LED, 0);
    CHECK(s.end_us == 2010);
    CHECK(s.flash_us == 200);
}

static void test_transitions_sorted_even_when_events_are_not_listed_in_time() {
    SeqSchedule s;
    // events must be given in time order; this one is unsorted -> refused
    CHECK(seq_parse("1000:E2,0:E1", &s) != nullptr);
}

static void test_refusals_leave_the_old_schedule() {
    SeqSchedule s;
    CHECK(seq_parse("0:E1,900:F100", &s) == nullptr);
    const SeqSchedule before = s;
    const char* bad[] = {
        "0:E1,0:E1",                // two edges on cam1
        "0:E2,5000:E2",             // two edges on cam2
        "0:F100,50:F100",           // flashes overlap
        "0:F100,100:F100",          // touching counts as one long pulse
        "0:F0",                     // empty flash
        "0:F1001",                  // longer than SEQ_MAX_PULSE_US
        "900F100",                  // no colon
        "x:E1",                     // no time
        "0:E3",                     // no such camera
        "0:G1",                     // no such event
        "0:E1,",                    // trailing comma
        "",                         // empty
        "0:E1 ",                    // trailing junk
        "-5:E1",                    // negative time
    };
    for (const char* b : bad) {
        const char* err = seq_parse(b, &s);
        if (err == nullptr) std::printf("accepted: \"%s\"\n", b);
        CHECK(err != nullptr);
        CHECK(std::strlen(err) > 0);
        CHECK(std::memcmp(&s, &before, sizeof s) == 0);
    }
    CHECK(seq_parse(nullptr, &s) != nullptr);
}

static void test_too_many_events() {
    SeqSchedule s;
    char buf[512] = "";
    // 17 flashes, 200 us apart
    for (int i = 0; i < SEQ_MAX_EVENTS + 1; ++i) {
        char tok[32];
        std::snprintf(tok, sizeof tok, "%s%d:F10", i ? "," : "", i * 200);
        std::strcat(buf, tok);
    }
    CHECK(seq_parse(buf, &s) != nullptr);
    // 16 is fine
    *std::strrchr(buf, ',') = '\0';
    CHECK(seq_parse(buf, &s) == nullptr);
    CHECK(s.n == 2 * SEQ_MAX_EVENTS);
    CHECK(s.flash_us == 160);
}

static void test_flash_only_and_edge_only() {
    SeqSchedule s;
    CHECK(seq_parse("0:E1,1000:E2", &s) == nullptr);   // dark shot: no flash
    CHECK(s.n == 4);
    CHECK(s.flash_us == 0);
    CHECK(s.end_us == 1010);
    CHECK(seq_parse("1500:F50", &s) == nullptr);
    CHECK(s.n == 2);
    expect_tr(s, 0, 1510, SEQ_LINE_LED, 1);
    expect_tr(s, 1, 1560, SEQ_LINE_LED, 0);
}

static void test_flash_during_a_low_pulse_is_ordered_by_time() {
    SeqSchedule s;
    // cam2 edge at 1000 means low at 1000..1010 (shifted); a flash at 995
    // starts at 1005 shifted - between them
    CHECK(seq_parse("995:F20,1000:E2", &s) == nullptr);
    expect_tr(s, 0, 1000, SEQ_LINE_CAM2, 0);
    expect_tr(s, 1, 1005, SEQ_LINE_LED, 1);
    expect_tr(s, 2, 1010, SEQ_LINE_CAM2, 1);
    expect_tr(s, 3, 1025, SEQ_LINE_LED, 0);
}

static void test_flashes_need_an_off_time_at_least_as_long_as_the_pulse_before() {
    SeqSchedule s;
    // final review 2026-11-21: 1 us gaps made 16 x 1000 us flashes one ~16 ms pulse
    CHECK(seq_parse("0:F1000,1001:F1000", &s) != nullptr);
    CHECK(seq_parse("0:F100,150:F100", &s) != nullptr);        // 50 us off after 100 us on
    CHECK(seq_parse("0:F100,200:F100", &s) == nullptr);        // 100 us off: ok
    CHECK(seq_parse("0:F20,60:F20", &s) == nullptr);           // short pulses: SEQ_MIN_FLASH_GAP_US
    CHECK(seq_parse("0:F20,59:F20", &s) != nullptr);
}

static void test_seq_shot_spacing_grows_with_the_flash_time() {
    SeqSchedule s;
    CHECK(seq_parse("0:E1,900:F100,1000:E2,1900:F100", &s) == nullptr);
    CHECK(seq_min_spacing_us(s, 5000, 0.25f) == 5000);         // 200 us on: SHOT's 5 ms
    char buf[512] = "";
    for (int i = 0; i < 8; ++i) {                              // 8 x 1000 us on
        char tok[32];
        std::snprintf(tok, sizeof tok, "%s%d:F1000", i ? "," : "", i * 2000);
        std::strcat(buf, tok);
    }
    CHECK(seq_parse(buf, &s) == nullptr);
    CHECK(s.flash_us == 8000);
    // duty over (schedule + spacing) <= 0.25: spacing >= 8000 / 0.25 - end
    const uint32_t sp = seq_min_spacing_us(s, 5000, 0.25f);
    CHECK((float)s.flash_us / (float)(s.end_us + sp) <= 0.25f + 1e-6f);
    CHECK(sp > 5000);
}

int main() {
    test_flashes_need_an_off_time_at_least_as_long_as_the_pulse_before();
    test_seq_shot_spacing_grows_with_the_flash_time();
    test_default_offset_schedule();
    test_transitions_sorted_even_when_events_are_not_listed_in_time();
    test_refusals_leave_the_old_schedule();
    test_too_many_events();
    test_flash_only_and_edge_only();
    test_flash_during_a_low_pulse_is_ordered_by_time();
    std::printf("ALL OK (%d checks)\n", g_checks);
    return 0;
}
