// ===================================================
//  DROWSINESS GLASSES: 5 levels, one pitch, faster beeps, long final ring
//  IR module:      VCC -> 5V, GND -> GND, OUT -> pin 2
//  Passive buzzer: VCC -> 5V, GND -> GND, I/O -> pin 8
//  Serial monitor: 9600 baud
// ===================================================

// ---- Hardware ------------------------------------------------------
const int  IR_PIN        = 2;
const int  BUZZER_PIN    = 8;
const bool IR_ACTIVE_LOW = true;    // true: IR OUT is LOW when it detects the eyelid
const bool DEBUG         = true;

// ---- Timing ----------------------------------------------------------
const unsigned long DEBOUNCE_MS      = 30;
const unsigned long BLINK_MAX_MS     = 500;    // closure shorter than this = normal blink
const int           WINDOW_S         = 30;     // rolling window: seconds to look back
const unsigned long WARMUP_MS        = 10000;  // no score-based alerts for the first 10 s
const unsigned long HOLD_MS          = 10000;  // min time at a level before stepping down on its own
const unsigned long UNCONSCIOUS_MS   = 3000;   // one closure this long = level 5
const int           NORMAL_BLINKS_TO_STOP = 2; // normal blinks in a row that silence the alarm

// ---- Levels (edit these) ---------------------------------------------
// Levels 1-4 come from "% of the window your eyes were closed".
// Level 5 comes from one very long closure.
const int LEVEL_PCT[4] = { 12, 20, 30, 40 };       // % closed needed for L1..L4

const unsigned int BEEP_HZ    = 2500;              // the same pitch for every level
const unsigned int BEEP_ON_MS = 150;               // every beep is this long
//                                      L1    L2   L3   L4
const unsigned int LEVEL_OFF_MS[4] = { 1500, 900, 450, 200 };   // gap between beeps: shorter = faster
// L5: continuous ring

// ---- State -----------------------------------------------------------
bool lastRaw = false;
bool stableClosed = false;
unsigned long rawChangedAt = 0;
unsigned long closedSince = 0;

unsigned int bucket[WINDOW_S];       // closed milliseconds in each 1-second slot
unsigned long lastSec = 0;
unsigned long lastTick = 0;

int level = 0;                       // 0 = none, 1-5
unsigned long levelSetAt = 0;
int normalBlinks = 0;

bool readIr() {
  bool raw = digitalRead(IR_PIN);
  return IR_ACTIVE_LOW ? !raw : raw;           // true = eyelid detected
}

// Track how long the eyes were closed in each second of the window
void updateWindow(unsigned long now) {
  unsigned long sec = now / 1000;
  while (lastSec < sec) {                      // clear slots for seconds that passed
    lastSec++;
    bucket[lastSec % WINDOW_S] = 0;
  }
  if (stableClosed) bucket[sec % WINDOW_S] += (unsigned int)(now - lastTick);
  lastTick = now;
}

int closedPercent(unsigned long now) {
  unsigned long total = 0;
  for (int i = 0; i < WINDOW_S; i++) total += bucket[i];
  unsigned long span = (now < WINDOW_S * 1000UL) ? now : WINDOW_S * 1000UL;
  if (span < 1000) return 0;
  return (int)(total * 100UL / span);
}

int targetLevel(int pct) {
  int lvl = 0;
  for (int i = 0; i < 4; i++) {
    if (pct >= LEVEL_PCT[i]) lvl = i + 1;
  }
  return lvl;
}

// Stop the alarm and reset the drowsiness score
void clearAlarm(unsigned long now) {
  level = 0;
  levelSetAt = now;
  normalBlinks = 0;
  memset(bucket, 0, sizeof(bucket));
}

void updateLevel(unsigned long now, int pct) {
  int target = (now >= WARMUP_MS) ? targetLevel(pct) : 0;

  // Unconscious override: one very long closure
  if (stableClosed && (now - closedSince) >= UNCONSCIOUS_MS) target = 5;

  // Eyes reopened after level 5: drop to level 4 (normal blinking will clear it)
  if (level == 5 && !stableClosed) {
    level = 4;
    levelSetAt = now;
  }

  if (target > level) {                        // rise immediately
    level = target;
    levelSetAt = now;
  } else if (target < level && (now - levelSetAt) >= HOLD_MS) {
    level--;                                   // fall one level at a time
    levelSetAt = now;
  }
}

// Called once each time the eyes reopen
void onEyesOpened(unsigned long closedFor, unsigned long now) {
  bool normal = (closedFor < BLINK_MAX_MS);

  if (DEBUG) {
    Serial.print("Blink: closed for ");
    Serial.print(closedFor);
    Serial.println(normal ? " ms (normal)" : " ms (slow)");
  }

  if (level == 0 || !normal) {                 // a slow blink restarts the count
    normalBlinks = 0;
    return;
  }

  normalBlinks++;
  if (normalBlinks >= NORMAL_BLINKS_TO_STOP) {
    clearAlarm(now);
    if (DEBUG) Serial.println("Normal blinking: alarm stopped");
  }
}

void updateBuzzer(unsigned long now) {
  static int activeLvl = 0;
  static bool on = false;
  static unsigned long phaseStart = 0;

  if (level == 0) {
    if (activeLvl != 0) {
      noTone(BUZZER_PIN);
      activeLvl = 0;
      on = false;
    }
    return;
  }

  if (level != activeLvl) {                    // just entered a new level
    activeLvl = level;
    on = true;
    phaseStart = now;
    tone(BUZZER_PIN, BEEP_HZ);
    return;
  }

  if (level == 5) return;                      // long continuous ring

  unsigned long dur = on ? BEEP_ON_MS : LEVEL_OFF_MS[level - 1];
  if (now - phaseStart >= dur) {
    on = !on;
    phaseStart = now;
    if (on) tone(BUZZER_PIN, BEEP_HZ);
    else    noTone(BUZZER_PIN);
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(IR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  tone(BUZZER_PIN, BEEP_HZ, 150);              // short startup beep

  lastRaw = readIr();
  stableClosed = lastRaw;
  unsigned long now = millis();
  closedSince = now;
  lastTick = now;
  lastSec = now / 1000;
  if (DEBUG) Serial.println("Glasses ready");
}

void loop() {
  unsigned long now = millis();

  // ---- debounced eyelid detection ----
  bool raw = readIr();
  if (raw != lastRaw) {
    lastRaw = raw;
    rawChangedAt = now;
  }
  if (raw != stableClosed && now - rawChangedAt >= DEBOUNCE_MS) {
    stableClosed = raw;
    if (stableClosed) {
      closedSince = rawChangedAt;
    } else {
      onEyesOpened(rawChangedAt - closedSince, now);
    }
  }

  // ---- drowsiness score, level, buzzer ----
  updateWindow(now);
  int pct = closedPercent(now);
  updateLevel(now, pct);
  updateBuzzer(now);

  // ---- once-per-second status ----
  static unsigned long lastPrint = 0;
  if (DEBUG && now - lastPrint >= 1000) {
    lastPrint = now;
    Serial.print("closed% = ");
    Serial.print(pct);
    Serial.print("   level = ");
    Serial.println(level);
  }
}
