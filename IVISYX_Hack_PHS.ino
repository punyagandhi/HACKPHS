// ===================================================
//  DROWSINESS GLASSES: beeps get faster the longer the eyelid stays closed
//  IR module:      VCC -> 5V, GND -> GND, OUT -> pin 2
//  Passive buzzer: VCC -> 5V, GND -> GND, I/O -> pin 8
//  Serial monitor: 9600 baud
// ===================================================

// ---- Hardware ------------------------------------------------------
const int  IR_PIN        = 2;
const int  BUZZER_PIN    = 8;
const bool IR_ACTIVE_LOW = true;    // true: IR OUT is LOW when it detects the eyelid
const bool DEBUG         = true;

// ---- Timing (edit these) ---------------------------------------------
const unsigned long DEBOUNCE_MS = 50;     // ignore IR flicker shorter than this

const unsigned long START_MS = 2000;      // eyelid closed this long: slow beeps start
const unsigned long RING_MS  = 7000;      // eyelid closed this long: one long ring
// Suggested real-use values: START_MS = 500, RING_MS = 3000

const unsigned int  BEEP_HZ        = 2500;   // one pitch for the whole alarm
const unsigned int  BEEP_ON_MS     = 80;     // each beep's length
const unsigned long SLOWEST_GAP_MS = 700;    // gap between beeps when they start
const unsigned long FASTEST_GAP_MS = 60;     // gap just before the ring

// ---- State -----------------------------------------------------------
bool lastRaw = false;
bool stableClosed = false;
unsigned long rawChangedAt = 0;
unsigned long closedSince = 0;

bool readIr() {
  bool raw = digitalRead(IR_PIN);
  return IR_ACTIVE_LOW ? !raw : raw;           // true = eyelid detected
}

// Gap between beeps shrinks in a straight line from START_MS to RING_MS
unsigned long gapFor(unsigned long closedFor) {
  if (closedFor <= START_MS) return SLOWEST_GAP_MS;
  if (closedFor >= RING_MS)  return FASTEST_GAP_MS;
  unsigned long span = RING_MS - START_MS;
  unsigned long diff = (SLOWEST_GAP_MS - FASTEST_GAP_MS) * (closedFor - START_MS) / span;
  return SLOWEST_GAP_MS - diff;
}

void updateBuzzer(bool closed, unsigned long closedFor, unsigned long now) {
  static bool active = false, on = false, cont = false;
  static unsigned long phaseStart = 0;

  // Eyes open, or closed for less than START_MS (normal blink): silent
  if (!closed || closedFor < START_MS) {
    if (active) {
      noTone(BUZZER_PIN);
      active = false; on = false; cont = false;
    }
    return;
  }

  // Long closure: one continuous ring
  if (closedFor >= RING_MS) {
    if (!cont) {
      tone(BUZZER_PIN, BEEP_HZ);
      cont = true; active = true; on = true;
    }
    return;
  }

  // In between: beeps that keep getting faster
  if (!active) {
    active = true; on = true; phaseStart = now;
    tone(BUZZER_PIN, BEEP_HZ);
    return;
  }

  unsigned long dur = on ? BEEP_ON_MS : gapFor(closedFor);
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

  tone(BUZZER_PIN, 2000, 150);                 // short startup beep

  lastRaw = readIr();
  stableClosed = lastRaw;
  closedSince = millis();
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
    } else if (DEBUG) {
      Serial.print("Eyes open. Closed for ");
      Serial.print(rawChangedAt - closedSince);
      Serial.println(" ms");
    }
  }

  // ---- buzzer ----
  unsigned long closedFor = stableClosed ? (now - closedSince) : 0;
  updateBuzzer(stableClosed, closedFor, now);

  // ---- status while the eyelid is closed ----
  static unsigned long lastPrint = 0;
  if (DEBUG && stableClosed && now - lastPrint >= 500) {
    lastPrint = now;
    Serial.print("Closed for ");
    Serial.print(closedFor);
    Serial.print(" ms: ");
    if (closedFor < START_MS)      Serial.println("silent");
    else if (closedFor >= RING_MS) Serial.println("RING");
    else {
      Serial.print("beeping, gap ");
      Serial.print(gapFor(closedFor));
      Serial.println(" ms");
    }
  }
}
