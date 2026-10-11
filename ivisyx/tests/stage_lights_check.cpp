#include "StageLights.h"
#include <cassert>

int main() {
  assert(selectLightStage(false, true, true, true, true, true) == LightStage::Off);
  assert(selectLightStage(true, true, false, false, false, false) == LightStage::Searching);
  assert(selectLightStage(true, false, true, false, false, false) == LightStage::Listening);
  assert(selectLightStage(true, false, true, true, true, false) == LightStage::Talking);
  assert(selectLightStage(true, false, true, false, true, false) == LightStage::Complete);
  assert(selectLightStage(true, false, true, true, true, true) == LightStage::Glasses);
  assert(selectLightStage(true, false, false, false, false, false) == LightStage::Off);
  auto orange = stageColor(LightStage::Glasses);
  assert(orange.r > orange.g && orange.g > orange.b);
  auto green = stageColor(LightStage::Complete);
  assert(green.g > green.r && green.g > green.b);
}
