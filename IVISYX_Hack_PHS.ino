// ===================================================
//  DROWSINESS GLASSES: IR sensor + buzzer module
//  IR module:     VCC -> 5V, GND -> GND, OUT -> pin 2
//  Buzzer module: VCC -> 5V, GND -> GND, I/O -> pin 8
//  Serial monitor: 9600 baud
// ===================================================

// ---- Pins and hardware settings ----------------------------------
const int  IR_PIN            = 2;
const int  BUZZER_PIN        = 8;
const bool IR_ACTIVE_LOW     = true;    // true: IR OUT is LOW when it detects the eyelid
const bool BUZZER_ACTIVE_LOW = true;    // true: buzzer sounds when pin is LOW (your module)
const bool BUZZER_PASSIVE    = true;   // true only if the buzzer needs tone() to sound
const bool DEBUG             = true;

const unsigned long DEBOUNCE_MS = 20;
const unsigned int  TEST_HZ     = 2000; // used for startup beeps on a passive buzzer

// ---- Alert levels (edit to tune) -----------------------------------
// offMs = 0 means continuous sound. freq is only used if BUZZER_PASSIVE is true.
struct Level {
  unsigned long minClosedMs;   // eyes closed at least this long
  unsigned int  freq;          // Hz (passive buzzer only)
  unsigned int  onMs;          // beep length
  unsigned int  offMs;         // silence between beeps (0 = continuous)
};

const Level LEVELS[] = {
  {  400, 1000, 100, 700 },    // L1: long blink, short beep, long gap
  {  800, 1800, 150, 300 },    // L2: drowsy, faster beeps
  { 1500, 2500, 250, 100 },    // L3: severe, rapid long beeps
  { 3000, 3500,   0,   0 }     // L4: unconscious, continuous alarm
};
const int NUM_LEVELS = sizeof(LEVELS) / sizeof(LEVELS[0]);

// ---- Drowsiness memory ---------------------------------------------
const int           HISTORY_SIZE  = 5;
const unsigned long WINDOW_MS     = 60000UL;  // look back 60 s
const int           TRIGGER_COUNT = 3;        // long closures within the window
const float         DROWSY_SCALE  = 0.5;      // thresholds shrink to 50% when drowsy

unsigned long longClosures[HISTORY_SIZE] = {0};
int historyIdx = 0;

// ---- State -----------------------------------------------------------
bool lastRaw = false;
bool stableClosed = false;
unsigned long rawChangedAt = 0;
unsigned long closedSince = 0;
int lastPrintedLevel = -1;
int lastPin = -1;

bool readIr() {
  bool raw = digitalRead(IR_PIN);
  return IR_ACTIVE_LOW ? !raw : raw;          // true = eyelid detected
}

void buzzer(bool on, unsigned int freq) {
  if (BUZZER_PASSIVE) {
    if (on) tone(BUZZER_PIN, freq);
    else    noTone(BUZZER_PIN);
  } else {
    digitalWrite(BUZZER_PIN, (on == BUZZER_ACTIVE_LOW) ? LOW : HIGH);
  }
}

float drowsyScale(unsigned long now) {
  int count = 0;
  for (int i = 0; i < HISTORY_SIZE; i++) {
    if (longClosures[i] != 0 && now - longClosures[i] <= WINDOW_MS) count++;
  }
  return (count >= TRIGGER_COUNT) ? DROWSY_SCALE : 1.0;
}

void recordLongClosure(unsigned long t) {
  longClosures[historyIdx] = t;
  historyIdx = (historyIdx + 1) % HISTORY_SIZE;
}

int currentLevel(unsigned long closedFor, unsigned long now) {
  float scale = drowsyScale(now);
  int lvl = -1;
  for (int i = 0; i < NUM_LEVELS; i++) {
    if (closedFor >= (unsigned long)(LEVELS[i].minClosedMs * scale)) lvl = i;
  }
  return lvl;                                  // -1 = no alert
}

void updateBuzzer(int lvl, unsigned long now) {
  static int activeLvl = -1;
  static bool on = false;
  static unsigned long phaseStart = 0;

  if (lvl < 0) {
    if (activeLvl >= 0) buzzer(false, 0);
    activeLvl = -1;
    on = false;
    return;
  }

  if (lvl != activeLvl) {                      // new level reached
    activeLvl = lvl;
    on = true;
    phaseStart = now;
    buzzer(true, LEVELS[lvl].freq);
    return;
  }

  if (LEVELS[lvl].offMs == 0) return;          // continuous

  unsigned long dur = on ? LEVELS[lvl].onMs : LEVELS[lvl].offMs;
  if (now - phaseStart >= dur) {
    on = !on;
    phaseStart = now;
    buzzer(on, LEVELS[lvl].freq);
  }
}

void setup() {
  Serial.begin(9600);

  // start silent before enabling the pin as an output
  if (!BUZZER_PASSIVE) digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_LOW ? HIGH : LOW);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(IR_PIN, INPUT);

  // self-test: two beeps, independent of the IR sensor
  for (int i = 0; i < 2; i++) {
    buzzer(true, TEST_HZ);  delay(300);
    buzzer(false, 0);       delay(300);
  }

  lastRaw = readIr();
  stableClosed = lastRaw;
  closedSince = millis();                      // avoids a false level-4 alarm at power-up

  if (DEBUG) {
    Serial.print("Glasses ready. IR raw pin = ");
    Serial.println(digitalRead(IR_PIN));
  }
}

void loop() {
  unsigned long now = millis();

  // ---- show raw IR pin changes (for troubleshooting) ----
  int pin = digitalRead(IR_PIN);
  if (DEBUG && pin != lastPin) {
    Serial.print("IR pin = ");
    Serial.println(pin);
    lastPin = pin;
  }

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
      if (DEBUG) Serial.println("Eyes CLOSED");
    } else {
      unsigned long closedFor = rawChangedAt - closedSince;
      if (closedFor >= LEVELS[0].minClosedMs) recordLongClosure(now);
      if (DEBUG) {
        Serial.print("Eyes OPEN, closed for ");
        Serial.print(closedFor);
        Serial.println(" ms");
      }
    }
  }

  // ---- alert level and buzzer ----
  int lvl = stableClosed ? currentLevel(now - closedSince, now) : -1;
  updateBuzzer(lvl, now);

  if (DEBUG && lvl != lastPrintedLevel) {
    Serial.print("Alert level: ");
    Serial.println(lvl + 1);                   // 0 = none, 1 to 4 = escalating
    lastPrintedLevel = lvl;
  }
}
