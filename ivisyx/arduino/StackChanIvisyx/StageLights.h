#pragma once

enum class LightStage { Off, Searching, Listening, Talking, Complete, Glasses };

inline LightStage selectLightStage(bool enabled, bool searching, bool mic,
                                   bool speaking, bool complete, bool glasses) {
  if (!enabled) return LightStage::Off;
  if (glasses) return LightStage::Glasses;
  if (searching) return LightStage::Searching;
  if (speaking) return LightStage::Talking;
  if (complete) return LightStage::Complete;
  if (mic) return LightStage::Listening;
  return LightStage::Off;
}

struct StageColor { unsigned char r, g, b; float period; const char* name; };

inline StageColor stageColor(LightStage stage) {
  switch (stage) {
    case LightStage::Searching: return {230, 190, 0, 300, "searching"};
    case LightStage::Listening: return {0, 180, 230, 600, "listening"};
    case LightStage::Talking: return {220, 25, 150, 220, "talking"};
    case LightStage::Complete: return {0, 220, 45, 850, "complete"};
    case LightStage::Glasses: return {255, 80, 0, 380, "glasses"};
    default: return {0, 0, 0, 600, "off"};
  }
}
