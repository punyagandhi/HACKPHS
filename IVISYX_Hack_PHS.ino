// ===================================================
//  DROWSINESS GLASSES: IR sensor + low-level-trigger active buzzer module
//  IR module:  VCC -> 5V, GND -> GND, OUT -> pin 2
//  Buzzer module: VCC -> 5V, GND -> GND, I/O -> pin 8
// ===================================================

const int  IR_PIN              = 2;
const int  BUZZER_PIN          = 8;
const bool IR_ACTIVE_LOW       = true;   // false if your IR module outputs HIGH on detect
const bool BUZZER_ACTIVE_LOW   = true;   // your module: LOW = sound
const bool DEBUG               = true;   // Serial at 9600

const unsigned long DEBOUNCE_MS = 20;

// ---- Alert levels (edit to tune) -----------------------------------
// offMs = 0 means continuous sound.
struct Level {
  unsigned long minClosedMs;   // eyes closed at least this long
  unsigned int  onMs;          // beep length
  unsigned int  offMs;         // silence between beeps (0 = continuous)
};

const Level LEVELS[] = {
  {  400,  100, 700 },    // L1: long blink, short beep, long gap
  {  800,  150, 300 },    // L2: drowsy, faster beeps
  { 1500,  250, 100 },    // L3: severe, rapid long beeps
  { 3000,    0,   0 }     // L4: unconscious, continuous alarm
};
const int NUM_LEVELS = sizeof(LEVELS) / sizeof(LEVELS[0]);

// ---- Drowsiness memory ---------------------------------------------
const int           HISTORY_SIZE  = 5;
const unsigned long WINDOW_MS     = 60000UL;
const int           TRIGGER_COUNT = 3;      // long closures within window
const float         DROWSY_SCALE  = 0.5;    // thresholds shrink to 50%

unsigned long longClosures[HISTORY_SIZE] = {0};
int historyIdx = 0;

// ---- State -----------------------------------------------------------
bool lastRaw = false;
bool stableClosed = false;
unsigned long rawChangedAt = 0;
unsigned long closedSince = 0;
int lastPrintedLevel = -1;

bool readIr() {
  bool raw = digitalRead(IR_PIN);
  return IR_ACTIVE_LOW ? !raw : raw;        // true = eyelid detected
}

void buzzer(bool on) {
  digitalWrite(BUZZER_PIN, (on == BUZZER_ACTIVE_LOW) ? LOW : HIGH);
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
  return lvl;                                // -1 = no alert
}

void updateBuzzer(int lvl, unsigned long now) {
  static int activeLvl = -1;
  static bool on = false;
  static unsigned long phaseStart = 0;

  if (lvl < 0) {
    if (activeLvl >= 0) buzzer(false);
    activeLvl = -1;
    on = false;
    return;
  }

  if (lvl != activeLvl) {                    // new level reached
    activeLvl = lvl;
    on = true;
    phaseStart = now;
    buzzer(true);
    return;
  }

  if (LEVELS[lvl].offMs == 0) return;        // continuous

  unsigned long dur = on ? LEVELS[lvl].onMs : LEVELS[lvl].offMs;
  if (now - phaseStart >= dur) {
    on = !on;
    phaseStart = now;
    buzzer(on);
  }
}

void setup() {
  Serial.begin(9600);
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_LOW ? HIGH : LOW);  // start silent
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(IR_PIN, INPUT);
  lastRaw = readIr();
  stableClosed = lastRaw;
  if (DEBUG) Serial.println("Glasses ready");
}

void loop() {
  unsigned long now = millis();

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

  int lvl = stableClosed ? currentLevel(now - closedSince, now) : -1;
  updateBuzzer(lvl, now);

  if (DEBUG && lvl != lastPrintedLevel) {
    Serial.print("Alert level: ");
    Serial.println(lvl + 1);                 // 0 = none, 1 to 4 = escalating
    lastPrintedLevel = lvl;
  }
}
