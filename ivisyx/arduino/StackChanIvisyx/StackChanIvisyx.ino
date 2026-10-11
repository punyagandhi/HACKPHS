/* ivisyx audio status and half-duplex 16 kHz PCM audio over USB. */

#include <M5CoreS3.h>
#include <img_converters.h>
#include <M5StackChan.h>
#include <drivers/PY32IOExpander/PY32IOExpander.hpp>
#include <cmath>
#include <drivers/SCServo_lib/src/SCSCL.h>
#include <Preferences.h>
#include "StageLights.h"

String lineBuffer;
String expression = "neutral";
bool discardLine = false;
String displayedStatus;
String displayMessage = "Pilot support ready";
int checklistStep = -1;
bool displayDirty = true;
String remoteActivity;
uint32_t activityUntil = 0;
m5::PY32IOExpander_Class sideLights;
bool lightsReady = false;
bool lightsOn = false;
bool stageLightsEnabled = true;
uint32_t lastLightUpdate = 0;
uint32_t lightUpdates = 0;
static constexpr size_t audioSamples = 4000;
static constexpr uint32_t audioRate = 16000;
int16_t audioBuffer[audioSamples];
int16_t playbackBuffers[2][audioSamples];
uint8_t playbackIndex = 0;
bool micActive = false;
bool speakerActive = false;
bool cameraActive = false;
uint32_t recordedSamples = 0;
uint32_t playedSamples = 0;
uint8_t previewBuffer[20000];
size_t previewLength = 0;
uint32_t previewUpdated = 0;
bool previewStale = true;
int presentationScore = -1;
bool demoArmed = false;
uint32_t buttonPresses = 0;
uint32_t demoHeartbeat = 0;
SCSCL pitchBus;
bool pitchBusReady = false;
String motionResult = "idle";
int pitchCurrent = -1, pitchTarget = -1, pitchLimit = -1, pitchTorqueAck = -1, pitchWriteAck = -1;
int searchOrigin = -1, searchMinimum = -1, searchMaximum = -1;
bool searchActive = false;
int startingYaw = -1, startingPitch = -1;
bool returnAttempted = false;
String returnResult = "idle";

bool returnToStartingPosition() {
  if (!demoArmed || !pitchBusReady || startingYaw < 0 || startingPitch < 0 ||
      startingYaw > 1000 || startingPitch > 1000) return false;
  int yawMin = pitchBus.readWord(1, SCSCL_MIN_ANGLE_LIMIT_L);
  int yawMax = pitchBus.readWord(1, SCSCL_MAX_ANGLE_LIMIT_L);
  int pitchMin = pitchBus.readWord(2, SCSCL_MIN_ANGLE_LIMIT_L);
  int pitchMax = pitchBus.readWord(2, SCSCL_MAX_ANGLE_LIMIT_L);
  if (yawMin < 0 || pitchMin < 0 || yawMax <= yawMin || pitchMax <= pitchMin ||
      startingYaw < yawMin || startingYaw > yawMax ||
      startingPitch < pitchMin || startingPitch > pitchMax) return false;
  searchActive = false;
  if (pitchBus.EnableTorque(1, 1) != 1 || pitchBus.EnableTorque(2, 1) != 1 ||
      pitchBus.WritePos(1, startingYaw, 1200, 0) != 1 ||
      pitchBus.WritePos(2, startingPitch, 1200, 0) != 1) {
    pitchBus.EnableTorque(1, 0); pitchBus.EnableTorque(2, 0); return false;
  }
  demoHeartbeat = millis();
  return true;
}

void stopMotorPower() {
  searchActive = false;
  if (pitchBusReady) {
    pitchBus.EnableTorque(1, 0);
    pitchBus.EnableTorque(2, 0);
  }
  if (lightsReady) sideLights.digitalWrite(0, false);
}

bool holdSearchYaw() {
  if (!pitchBusReady) return false;
  int current = pitchBus.ReadPos(1);
  if (current < searchMinimum || current > searchMaximum) {
    pitchBus.EnableTorque(1, 0); searchActive = false; return false;
  }
  return pitchBus.WritePos(1, current, 20, 0) == 1;
}

bool tiltUp45() {
  if (!lightsReady) return false;
  sideLights.setDirection(0, true);
  sideLights.setPullMode(0, true);
  sideLights.setDriveMode(0, false);
  sideLights.digitalWrite(0, true);
  delay(500);
  if (!pitchBusReady) pitchBusReady = pitchBus.begin(UART_NUM_1, 1000000, 6, 7);
  if (!pitchBusReady) { sideLights.digitalWrite(0, false); return false; }
  pitchBus.IOTimeOut = 50;
  pitchBus.EnableTorque(1, 0); // Keep yaw stationary; only pitch is requested.
  int current = pitchBus.ReadPos(2);
  for (int attempt = 0; current < 0 && attempt < 4; ++attempt) {
    delay(100);
    current = pitchBus.ReadPos(2);
  }
  pitchCurrent = current;
  int yaw = pitchBus.ReadPos(1);
  if (yaw < 0 || yaw > 1000) { sideLights.digitalWrite(0, false); return false; }
  startingYaw = yaw;
  startingPitch = current;
  Preferences preferences;
  preferences.begin("servo", true);
  int zero = preferences.getInt("zero_pos_2", 620);
  preferences.end();
  int target = zero + 144; // Manufacturer mapping: 45 degrees = 144 position units.
  pitchTarget = target;
  pitchLimit = pitchBus.readWord(2, SCSCL_MAX_ANGLE_LIMIT_L);
  if (current < 0 || current > 1000 || zero < 0 || target > 1000) {
    sideLights.digitalWrite(0, false); return false;
  }
  pitchTorqueAck = pitchBus.EnableTorque(2, 1);
  pitchWriteAck = pitchTorqueAck == 1 ? pitchBus.WritePos(2, target, 1200, 0) : -1;
  if (pitchTorqueAck != 1 || pitchWriteAck != 1) {
    pitchBus.EnableTorque(2, 0); sideLights.digitalWrite(0, false); return false;
  }
  return true;
}

bool talking() {
  return CoreS3.Speaker.isPlaying() ||
         (remoteActivity == "speaking" && static_cast<int32_t>(activityUntil - millis()) > 0);
}

LightStage currentLightStage() {
  bool glasses = displayMessage.indexOf("Put on") >= 0 && displayMessage.indexOf("glasses") >= 0;
  return selectLightStage(stageLightsEnabled, displayMessage == "Looking for your face",
                          micActive, talking(), displayMessage == "Pilot support ready" && !micActive, glasses);
}

void pumpLights() {
  LightStage stage = currentLightStage();
  StageColor color = stageColor(stage);
  bool active = stage != LightStage::Off;
  if (!lightsReady || (!active && !lightsOn) || (active && millis() - lastLightUpdate < 50)) return;
  lastLightUpdate = millis();
  for (int i = 0; i < 6; ++i) {
    float wave = active ? 0.25f + 0.75f * (0.5f + 0.5f * sinf(millis() / color.period - i * 0.5f)) : 0;
    uint8_t r = static_cast<uint8_t>(color.r * wave);
    uint8_t g = static_cast<uint8_t>(color.g * wave);
    uint8_t b = static_cast<uint8_t>(color.b * wave);
    sideLights.setLedColor(i, r, g, b);
    sideLights.setLedColor(11 - i, r, g, b);
  }
  sideLights.refreshLeds();
  lightsOn = active;
  ++lightUpdates;
}

bool beginSharedCamera() {
  // Reuse the live internal bus so the camera does not take I2C away from side LEDs.
  camera_config_t cfg = {};
  cfg.pin_pwdn = -1; cfg.pin_reset = -1; cfg.pin_xclk = -1;
  cfg.pin_sccb_sda = -1; cfg.pin_sccb_scl = -1;
  cfg.sccb_i2c_port = M5.In_I2C.getPort();
  cfg.pin_d7 = 47; cfg.pin_d6 = 48; cfg.pin_d5 = 16; cfg.pin_d4 = 15;
  cfg.pin_d3 = 42; cfg.pin_d2 = 41; cfg.pin_d1 = 40; cfg.pin_d0 = 39;
  cfg.pin_vsync = 46; cfg.pin_href = 38; cfg.pin_pclk = 45;
  cfg.xclk_freq_hz = 20000000;
  cfg.ledc_timer = LEDC_TIMER_0; cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.pixel_format = PIXFORMAT_RGB565; cfg.frame_size = FRAMESIZE_QVGA;
  cfg.fb_count = 2; cfg.fb_location = CAMERA_FB_IN_PSRAM;
  cfg.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  return esp_camera_init(&cfg) == ESP_OK;
}

void pumpDisplay() {
  M5.update();
  if (demoArmed && millis() - demoHeartbeat > 15000) {
    demoArmed = false;
    stageLightsEnabled = false;
    stopMotorPower();
  }
  if (demoArmed && motionResult == "idle" && M5.BtnPWR.wasClicked()) {
    ++buttonPresses;
    motionResult = tiltUp45() ? "commanded" : "failed";
    displayDirty = true;
  }
  pumpLights();
  bool stale = !previewLength || millis() - previewUpdated > 2000;
  if (stale != previewStale) { previewStale = stale; displayDirty = true; }
  bool remoteMic = remoteActivity == "macmic" && static_cast<int32_t>(activityUntil - millis()) > 0;
  String status = talking() ? "SPEAKING" : micActive ? "MIC ON" : remoteMic ? "MAC MIC ON" : "MIC OFF";
  if (status != displayedStatus || displayDirty) {
    CoreS3.Display.fillScreen(BLACK);
    CoreS3.Display.setTextSize(1);
    CoreS3.Display.setTextColor(WHITE, BLACK);
    CoreS3.Display.drawString("ivisyx", 10, 6);
    CoreS3.Display.setTextColor(talking() ? GREEN : CYAN, BLACK);
    CoreS3.Display.drawRightString(status, 310, 6);
    CoreS3.Display.drawFastHLine(10, 30, 300, 0x4208);
    CoreS3.Display.setTextColor(0x9CF3, BLACK);
    CoreS3.Display.drawString("PILOT SUPPORT", 10, 36);
    CoreS3.Display.setTextColor(CYAN, BLACK);
    CoreS3.Display.drawString(displayMessage == "Looking for your face" ? "SEARCHING" : "VOICE SESSION", 10, 72);
    if (previewLength) CoreS3.Display.drawJpg(previewBuffer, previewLength, 166, 62);
    CoreS3.Display.setTextColor(previewStale ? YELLOW : GREEN, BLACK);
    CoreS3.Display.drawString(previewStale ? "EYES: PAUSED" : "EYE TRACKING", 166, 170);
    if (presentationScore >= 0) {
      CoreS3.Display.setTextColor(YELLOW, BLACK);
      CoreS3.Display.drawString("TEST " + String(presentationScore) + "/100", 10, 148);
      CoreS3.Display.drawString("MODERATE", 10, 168);
    }
    CoreS3.Display.drawFastHLine(10, 190, 300, 0x4208);
    CoreS3.Display.setTextColor(YELLOW, BLACK);
    String remaining = displayMessage;
    for (int row = 0; row < 2 && remaining.length(); ++row) {
      int count = remaining.length();
      while (count > 0 && CoreS3.Display.textWidth(remaining.substring(0, count)) > 296) --count;
      if (count < remaining.length()) {
        int space = remaining.lastIndexOf(' ', count);
        if (space > 0) count = space;
      }
      CoreS3.Display.drawString(remaining.substring(0, count), 12, 198 + row * 18);
      remaining = remaining.substring(count);
      remaining.trim();
    }
    displayedStatus = status;
    displayDirty = false;
  }
  delay(1);
}

void idleAudio() {
  if (micActive) {
    CoreS3.Mic.end();
    micActive = false;
  }
  if (speakerActive) {
    CoreS3.Speaker.end();
    speakerActive = false;
  }
}

void captureAudio() {
  if (cameraActive) {
    Serial.println("ERR close camera mode before using audio");
    return;
  }
  if (speakerActive) {
    uint32_t started = millis();
    while (CoreS3.Speaker.isPlaying()) {
      if (millis() - started > 2000) { idleAudio(); Serial.println("ERR playback drain timeout"); return; }
      pumpDisplay();
    }
    CoreS3.Speaker.end();
    speakerActive = false;
  }
  if (!micActive) {
    micActive = CoreS3.Mic.begin();
  }
  if (!micActive || !CoreS3.Mic.record(audioBuffer, audioSamples, audioRate)) {
    Serial.println("ERR microphone start failed");
    return;
  }
  uint32_t started = millis();
  while (CoreS3.Mic.isRecording()) {
    if (millis() - started > 2000) {
      idleAudio();
      Serial.println("ERR microphone timeout");
      return;
    }
    pumpDisplay();
  }
  recordedSamples += audioSamples;
  Serial.printf("pcm:%u\n", static_cast<unsigned>(sizeof(audioBuffer)));
  Serial.write(reinterpret_cast<uint8_t*>(audioBuffer), sizeof(audioBuffer));
  Serial.flush();
}

void playAudio(const String& argument, bool queued = false) {
  if (cameraActive) {
    Serial.println("ERR close camera mode before using audio");
    return;
  }
  char* end = nullptr;
  unsigned long length = strtoul(argument.c_str(), &end, 10);
  if (!argument.length() || *end != '\0' || length == 0 ||
      length > sizeof(audioBuffer) || length % 2 != 0) {
    Serial.println("ERR invalid playback size");
    return;
  }
  if (micActive) {
    CoreS3.Mic.end();
    micActive = false;
  }
  if (!speakerActive) {
    speakerActive = CoreS3.Speaker.begin();
  }
  if (!speakerActive) {
    Serial.println("ERR speaker start failed");
    return;
  }
  if (queued) {
    uint32_t started = millis();
    while (CoreS3.Speaker.isPlaying(0) >= 2) {
      if (millis() - started > 2000) { idleAudio(); Serial.println("ERR playback queue timeout"); return; }
      pumpDisplay();
    }
  }
  int16_t* buffer = queued ? playbackBuffers[playbackIndex] : audioBuffer;
  Serial.println(queued ? "ready:playq" : "ready:play");
  if (Serial.readBytes(reinterpret_cast<uint8_t*>(buffer), length) != length) {
    idleAudio();
    Serial.println("ERR playback receive timeout");
    return;
  }
  if (!CoreS3.Speaker.playRaw(buffer, length / 2, audioRate, false, 1, 0)) {
    Serial.println("ERR playback start failed");
    return;
  }
  if (queued) {
    playbackIndex ^= 1;
    playedSamples += length / 2;
    Serial.println("ok:playq"); return;
  }
  uint32_t started = millis();
  while (CoreS3.Speaker.isPlaying()) {
    if (millis() - started > 2000) {
      idleAudio();
      Serial.println("ERR playback timeout");
      return;
    }
    pumpDisplay();
  }
  playedSamples += length / 2;
  Serial.println("ok:play");
}

void handleLine(const String& line) {
  if (line == "demo:arm" || line == "demo:disarm") {
    demoArmed = line == "demo:arm";
    stageLightsEnabled = demoArmed;
    demoHeartbeat = millis();
    if (!demoArmed) {
      stopMotorPower();
    } else {
      presentationScore = -1; motionResult = "idle";
      startingYaw = startingPitch = -1; returnAttempted = false; returnResult = "idle";
    }
    displayDirty = true;
    Serial.println("ok:" + line); return;
  }
  if (line == "demo:status") {
    demoHeartbeat = millis();
    if (demoArmed && motionResult == "commanded") pitchCurrent = pitchBus.ReadPos(2);
    Serial.printf("demo:presses=%lu motion=%s current=%d target=%d limit=%d torque=%d write=%d\n",
                  static_cast<unsigned long>(buttonPresses), motionResult.c_str(), pitchCurrent, pitchTarget, pitchLimit, pitchTorqueAck, pitchWriteAck); return;
  }
  if (line == "demo:tilt" && demoArmed) {
    ++buttonPresses;
    motionResult = tiltUp45() ? "commanded" : "failed";
    Serial.println("ok:demo:tilt"); return;
  }
  if (line == "home:status") {
    int yaw = pitchBusReady && demoArmed ? pitchBus.ReadPos(1) : -1;
    int pitch = pitchBusReady && demoArmed ? pitchBus.ReadPos(2) : -1;
    Serial.printf("home:start_yaw=%d start_pitch=%d yaw=%d pitch=%d return=%s\n",
                  startingYaw, startingPitch, yaw, pitch, returnResult.c_str()); return;
  }
  if (line == "seek:start") {
    if (!demoArmed || !pitchBusReady || motionResult != "commanded") {
      Serial.println("ERR search requires armed tilt"); return;
    }
    searchOrigin = pitchBus.ReadPos(1);
    searchMinimum = pitchBus.readWord(1, SCSCL_MIN_ANGLE_LIMIT_L);
    searchMaximum = pitchBus.readWord(1, SCSCL_MAX_ANGLE_LIMIT_L);
    // Do not change servo mode or EEPROM limits to make a sweep possible.
    if (searchMaximum >= 1000 && searchMaximum <= 1023) searchMaximum = 1000;
    if (searchMinimum < 0 || searchMaximum > 1000 || searchMaximum <= searchMinimum ||
        searchOrigin - 39 < searchMinimum || searchOrigin + 39 > searchMaximum ||
        pitchBus.EnableTorque(1, 1) != 1) {
      pitchBus.EnableTorque(1, 0);
      Serial.printf("ERR yaw search unavailable current=%d min=%d max=%d\n", searchOrigin, searchMinimum, searchMaximum); return;
    }
    searchActive = true; demoHeartbeat = millis();
    Serial.println("ok:seek:start"); return;
  }
  if (line.startsWith("seek:yaw:")) {
    String value = line.substring(9);
    char* end = nullptr;
    long degrees = strtol(value.c_str(), &end, 10);
    if (!demoArmed || !searchActive || !value.length() || *end || degrees < -12 || degrees > 12) {
      Serial.println("ERR invalid or inactive yaw search"); return;
    }
    int target = searchOrigin + degrees * 16 / 5;
    if (target < searchMinimum || target > searchMaximum || pitchBus.WritePos(1, target, 600, 0) != 1) {
      pitchBus.EnableTorque(1, 0); searchActive = false; Serial.println("ERR yaw movement failed"); return;
    }
    demoHeartbeat = millis(); Serial.println("ok:" + line); return;
  }
  if (line == "seek:hold" || line == "seek:cancel") {
    if (!demoArmed || !searchActive || !holdSearchYaw()) {
      pitchBus.EnableTorque(1, 0); searchActive = false;
      Serial.println("ERR cannot hold yaw search"); return;
    }
    if (line == "seek:cancel") {
      pitchBus.EnableTorque(1, 0); searchActive = false;
    }
    demoHeartbeat = millis(); Serial.println("ok:" + line); return;
  }
  if (line.startsWith("score:test:")) {
    String value = line.substring(11);
    char* end = nullptr;
    long score = strtol(value.c_str(), &end, 10);
    if (!value.length() || *end || score < 0 || score > 100) { Serial.println("ERR invalid test score"); return; }
    presentationScore = score; displayDirty = true;
    Serial.println("ok:" + line); return;
  }
  if (line.startsWith("preview:")) {
    String value = line.substring(8);
    char* end = nullptr;
    unsigned long size = strtoul(value.c_str(), &end, 10);
    if (!value.length() || *end || size < 4 || size > sizeof(previewBuffer)) { Serial.println("ERR invalid preview size"); return; }
    Serial.println("ready:preview");
    previewLength = 0;
    if (Serial.readBytes(previewBuffer, size) != size || previewBuffer[0] != 0xff || previewBuffer[1] != 0xd8 ||
        previewBuffer[size-2] != 0xff || previewBuffer[size-1] != 0xd9) {
      displayDirty = true; Serial.println("ERR invalid preview JPEG"); return;
    }
    previewLength = size; previewUpdated = millis(); displayDirty = true;
    pumpDisplay(); Serial.println("ok:preview"); return;
  }
  if (line.startsWith("checklist:")) {
    String value = line.substring(10);
    if (value != "-1" && value != "0" && value != "1" && value != "2") {
      Serial.println("ERR invalid checklist step"); return;
    }
    checklistStep = value.toInt();
    if (checklistStep == -1) presentationScore = -1;
    displayDirty = true;
    Serial.println("ok:" + line); return;
  }
  if (line.startsWith("message:")) {
    if (line.length() > 128) { Serial.println("ERR message too long"); return; }
    displayMessage = line.substring(8); displayDirty = true;
    if (demoArmed && !returnAttempted && displayMessage.indexOf("Put on") >= 0 &&
        displayMessage.indexOf("glasses") >= 0) {
      returnAttempted = true;
      returnResult = returnToStartingPosition() ? "commanded" : "failed";
    }
    Serial.println("ok:message"); return;
  }
  if (line.startsWith("activity:")) {
    String value = line.substring(9);
    if (value != "speaking" && value != "macmic" && value != "off") {
      Serial.println("ERR invalid activity"); return;
    }
    remoteActivity = value; activityUntil = millis() + 3000;
    Serial.println("ok:" + line); return;
  }
  if (line == "lights:status") {
    Serial.printf("lights:ready:%u active:%u updates:%lu stage:%s bus_power:%u version:%u config:%u\n",
                  lightsReady, currentLightStage() != LightStage::Off, static_cast<unsigned long>(lightUpdates), stageColor(currentLightStage()).name,
                  M5.Power.getExtOutput(), sideLights.readVersion(), sideLights.readRegister8(0x24));
    return;
  }
  if (line == "camera:on") {
    uint32_t started = millis();
    while (CoreS3.Speaker.isPlaying()) {
      if (millis() - started > 2000) { Serial.println("ERR camera waiting for playback"); return; }
      pumpDisplay();
    }
    idleAudio();
    if (!cameraActive) {
      cameraActive = beginSharedCamera();
    }
    if (!cameraActive) {
      M5.In_I2C.begin();
      Serial.println("ERR camera start failed");
      return;
    }
    Serial.println("ok:camera:on");
    return;
  }
  if (line == "camera:off") {
    if (cameraActive) {
      esp_camera_deinit();
      cameraActive = false;
    }
    Serial.println("ok:camera:off");
    return;
  }
  if (line == "frame") {
    if (!cameraActive || !CoreS3.Camera.get()) {
      Serial.println("ERR camera frame unavailable");
      return;
    }
    uint8_t* jpeg = nullptr;
    size_t length = 0;
    bool converted = frame2jpg(CoreS3.Camera.fb, 80, &jpeg, &length);
    CoreS3.Camera.free();
    if (!converted || !jpeg || !length || length > 200000) {
      free(jpeg);
      Serial.println("ERR camera JPEG conversion failed");
      return;
    }
    Serial.printf("jpeg:%u\n", static_cast<unsigned>(length));
    // USB writes can be partial when the host is busy with inference/audio.
    size_t sent = 0;
    uint32_t started = millis();
    while (sent < length && millis() - started < 5000) {
      size_t chunk = length - sent;
      if (chunk > 1024) chunk = 1024;
      sent += Serial.write(jpeg + sent, chunk);
      pumpDisplay();
    }
    Serial.flush();
    free(jpeg);
    return;
  }
  if (line == "speaker:diag") {
    uint8_t amplifier[2] = {0, 0};
    uint8_t power = 0;
    bool ampRead = M5.In_I2C.readRegister(0x36, 0x04, amplifier, 2, 400000);
    bool powerRead = M5.In_I2C.readRegister(0x58, 0x02, &power, 1, 400000);
    auto config = CoreS3.Speaker.config();
    Serial.printf("speaker:volume:%u rate:%lu bck:%d ws:%d data:%d amp_read:%u amp:%02x%02x power_read:%u power:%02x\n",
                  CoreS3.Speaker.getVolume(), static_cast<unsigned long>(config.sample_rate),
                  config.pin_bck, config.pin_ws, config.pin_data_out,
                  ampRead, amplifier[0], amplifier[1], powerRead, power);
    return;
  }
  if (line == "tone") {
    if (cameraActive) {
      Serial.println("ERR close camera mode before using audio");
      return;
    }
    idleAudio();
    speakerActive = CoreS3.Speaker.begin();
    if (!speakerActive) {
      Serial.println("ERR speaker start failed");
      return;
    }
    CoreS3.Speaker.tone(880, 1500);
    while (CoreS3.Speaker.isPlaying()) {
      pumpDisplay();
    }
    Serial.println("ok:tone");
    return;
  }
  if (line == "audio") {
    stageLightsEnabled = true;
    Serial.println("audio:pcm_16000:8000:v2");
    return;
  }
  if (line == "mic") {
    captureAudio();
    return;
  }
  if (line.startsWith("play:")) {
    playAudio(line.substring(5));
    return;
  }
  if (line.startsWith("playq:")) {
    playAudio(line.substring(6), true);
    return;
  }
  if (line == "idle") {
    stageLightsEnabled = false;
    idleAudio();
    Serial.println("ok:idle");
    return;
  }
  if (line == "drain") {
    uint32_t started = millis();
    while (CoreS3.Speaker.isPlaying()) {
      if (millis() - started > 2000) { Serial.println("ERR playback drain timeout"); return; }
      pumpDisplay();
    }
    Serial.println("ok:drain"); return;
  }
  if (line.startsWith("expr:")) {
    expression = line.substring(5);
    Serial.print("ok:");
    Serial.println(line);
    return;
  }
  if (line == "status") {
    Serial.printf("display:status expr:%s audio:%s mic_samples:%lu speaker_samples:%lu checklist:%d message:%s\n",
                  expression.c_str(),
                  CoreS3.Speaker.isPlaying() ? "playing" : micActive ? "listening" : "idle",
                  static_cast<unsigned long>(recordedSamples),
                  static_cast<unsigned long>(playedSamples), checklistStep, displayMessage.c_str());
    return;
  }
  Serial.print("unknown:");
  Serial.println(line);
}

void setup() {
  // Native USB defaults to a 256-byte RX queue, which drops PCM bursts.
  Serial.setRxBufferSize(16384);
  Serial.setTxBufferSize(16384);
  auto cfg = M5.config();
  CoreS3.begin(cfg);
  Serial.begin(115200);
  Serial.setTimeout(3000);
  CoreS3.Speaker.end();
  CoreS3.Mic.end();
  CoreS3.Speaker.setVolume(255);
  M5.Power.setExtOutput(true);
  for (int attempt = 0; attempt < 6 && !lightsReady; ++attempt) {
    lightsReady = sideLights.begin();
    if (!lightsReady) delay(200);
  }
  if (lightsReady) {
    sideLights.setDirection(13, true);
    sideLights.setPullMode(13, true);
    sideLights.setDriveMode(13, false);
    sideLights.digitalWrite(13, true);
    sideLights.setLedCount(12);
    lightsOn = true;
    pumpLights();
  }
  CoreS3.Display.fillScreen(BLACK);
  CoreS3.Display.setFont(&fonts::Font2);
  CoreS3.Display.setTextSize(1);
  CoreS3.Display.setTextDatum(top_left);
  lineBuffer.reserve(2064);
  pumpDisplay();
  Serial.println("ivisyx status and audio bridge ready");
}

void loop() {
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      if (!discardLine) {
        handleLine(lineBuffer);
      } else {
        Serial.println("unknown:command too long");
      }
      lineBuffer = "";
      discardLine = false;
    } else if (c != '\r' && !discardLine) {
      if (lineBuffer.length() < 2064) {
        lineBuffer += c;
      } else {
        discardLine = true;
      }
    }
  }

  pumpDisplay();
}
