# ivisyx MVP

## Power-Button Presentation

Run `run_presentation.py` in PyCharm; stop all other robot launchers first.
Keep the robot on a stable surface with clearance above its head. Short-click
the power button, not a long hold. The head receives a slow 45-degree upward
pitch command, then makes a small yaw search, at most 12 degrees either side
of its starting position. Two consecutive face detections stop the search
and start the conversation. The Mac must remain connected and running.
If no face is found within 14 seconds, the robot stops searching and stays
silent; face the camera and short-click power again to retry. Servo failures
stop the launch rather than starting speech with an unconfirmed face.
A received command is not proof of
the physical angle; confirm the tilt visually. M5Stack recommends the base
USB-C port when motors are used.

The yaw search requires the updated firmware and valid position-mode servo
limits. It never changes servo mode, calibration, or EEPROM limits. Keep the
robot on a stable surface with clearance for both tilt and the small sweep.
This is startup acquisition only, not continuous face following. During the
checklist and drowsiness question, the head stays still and camera updates pause.

For a camera/servo-only startup check, with all other robot programs stopped:

```bash
PYTHONPATH=src .venv/bin/python -m ivisyx.face_search_smoke_test
```

This commands the tilt and bounded search immediately, without a button press
or ElevenLabs connection. It saves no images or audio and releases motor power
on exit. Physical angle and audible quality still require human confirmation.

ivisyx begins a single-question pilot-support preflight check-in:

1. Have you reviewed your aircraft's approved preflight checklist?

After your confirmation, ivisyx says
"Preflight checklist complete." Python then sends a scripted 50/100 event:
"Moderate drowsiness detected. Are you feeling drowsy?"
The agent waits for your answer. If you affirm drowsiness, it says
"Please put on your ivisyx glasses. Follow your approved fatigue procedures."
If you deny drowsiness, it acknowledges the test without recommending glasses.
An unclear answer prompts the question again, not a glasses instruction.
The display marks this score TEST. It is not derived from the camera and is
never used by the live eyelid monitor. Glasses do not treat fatigue or certify
readiness to fly. The single-question check-in is not an aircraft checklist.

The screen shows the checklist item beside a 144x108 camera thumbnail with green
tracked-eye points. Updates are limited to roughly one per second and pause
during speech; stale images are labeled EYES: PAUSED. The reminder stays below.
In presentation mode the thumbnail also pauses through the single-question
conversation and drowsiness question to keep microphone capture continuous,
and resumes after the agent acknowledges your answer.
Audio uses only Stack-chan's microphone and speaker. Motor power is released
on exit or after loss of the application's button-status heartbeat.

Paste `agent_prompt.txt` into ElevenLabs and change its separate First Message
to: "I'm ivisyx. Shall we begin your preflight check-in?" If you configured the
`update_robot_display` client tool, use checklist_step -1 (idle), 0 (question),
or 2 (complete). Step 1 is retained for protocol compatibility but is unused.
The local client does not update your ElevenLabs dashboard configuration.
If the agent still says the old demo greeting, ensure the new configuration
is published on the branch serving live traffic, not merely saved in a draft.

## Eyelid Drowsiness Demonstration

Run `run_drowsiness.py` in PyCharm with the project `.venv`. Stop other ivisyx
launchers first. It uses **only the CoreS3 camera, microphone, and speaker**.
The Mac processes tracking and connects to ElevenLabs, but its microphone and
speakers are not opened. Camera frames alternate with microphone packets because
the firmware uses separate camera/audio modes. Camera capture pauses during
replies. No firmware upload is needed for this change.

This interleaved mode is experimental: camera sampling and microphone capture
have gaps, which can reduce speech recognition and prevent eyelid alerts. Gaps
over 0.5 seconds invalidate continuous closure measurements rather than inventing
tracking data. Use `run_cores3.py` for the most reliable voice-only demo.

Face the robot with both eyes naturally open for three seconds to calibrate.
The Mac window shows only eyelid points/contours, continuous closure duration,
the rolling 60-second closure-time proxy, observation coverage, and agent status.
Press C to recalibrate after changing camera position. Close the window to stop.

Demo alert conditions are both eyes closed for at least 2 seconds, or at least
20% closure time with 30 seconds of valid observations and 80% coverage.
These are engineering demo thresholds, **not validated fatigue thresholds**.
Closure means both eye aspect ratios below 65% of their open-eye baselines.
The first 0.5 seconds of each closure is excluded from the rolling metric to
reduce short-blink contribution. Missing faces, tiny/occluded eyes, invalid
geometry, and gaps over 0.5 seconds break continuous closure; missing time is
not counted as open or closed. Poor viewing angles can still produce errors.
Calibration requires naturally open eyes; calibrating while squinting or closed
can invalidate the result. This does not identify a person or track actual sleep.

Each eligible alert sends a short derived-metric message to the configured
ElevenLabs agent, asking for a brief readiness check-in. No images or landmark
coordinates are transmitted. Alerts are limited to once per 60 seconds; failed
sends retry only while the condition remains present. Normal conversation can
continue through Stack-chan. This is an experimental prototype, not a diagnosis, validated
fatigue monitor, or operational flight-safety system.

Research basis:
- [Soukupova and Cech: Eye Aspect Ratio](https://cmp.felk.cvut.cz/ftp/articles/cech/Soukupova-CVWW-2016.pdf)
- [FHWA: PERCLOS research](https://www.govinfo.gov/content/pkg/GOVPUB-TD2-PURL-gpo6571/pdf/GOVPUB-TD2-PURL-gpo6571.pdf)
- [ElevenLabs contextual updates and user messages](https://elevenlabs.io/docs/eleven-agents/customization/events/client-to-server-events)

True PERCLOS measures time with at least 80% eyelid closure over the pupil.
Our landmark/EAR proxy does **not** measure that pupil coverage, so the UI
deliberately does not label its result as PERCLOS80. A contextual update alone
does not prompt speech; an alert uses the SDK's `send_user_message` so the agent
can respond immediately. It is a sensor message, not a spoken user transcription.

Offline camera/metric check without ElevenLabs:
```bash
.venv/bin/python run_face_tracking.py --drowsiness --headless --seconds 15
```

## CoreS3 Face-Point Demo On Mac

Run `run_face_tracking.py` in PyCharm using this project's `.venv` interpreter.
Stop `run_cores3.py` and any Arduino serial monitor first: only one program can
own the robot's USB port. This first milestone runs vision separately from voice.
The Mac window shows the actual CoreS3 camera image, tracked face points, yellow
eye contours, tracking status, and measured frame rate. No laptop webcam is used.
Close the window or press Escape to release the camera, then run `run_cores3.py`
for the original agent conversation again. The robot shows audio status, the single-question preflight check-in, and a reminder area.

Vision setup (already installed on this Mac):

```bash
.venv/bin/python -m pip install -r requirements-vision.txt
mkdir -p models
curl -fL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o models/face_landmarker.task
.venv/bin/python run_face_tracking.py
```

Video is processed locally using [Google's MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python); normal runs
do not record images or contact ElevenLabs. Camera frames are requested over USB
as bounded JPEG packets. If tracking is absent, face the robot in good light.
`--rotate 180` can correct an upside-down mounting. `--seconds 15 --headless`
runs a bounded transport and inference check. `--snapshot /absolute/path.png`
explicitly saves the final annotated frame locally; it is off by default.
This milestone demonstrates facial landmarks, not calibrated eyelid closure,
head direction, fatigue detection, or a flight-safety system.

ivisyx is a one-day hackathon MVP for an ElevenLabs conversational voice assistant connected to an M5Stack CoreS3 Stack-chan.

The current robot audio path is:

```text
CoreS3 microphones -> USB -> Python/ElevenLabs -> USB -> CoreS3 speaker
                               |
Microphone and playback activity -> CoreS3 status display
```

The Mac runs ElevenLabs and holds the environment configuration. The CoreS3 captures and plays 16 kHz signed 16-bit mono audio. Its screen displays audio status above a single-question preflight check-in and a reminder area. Launchers do not fall back to Mac audio if the robot is unavailable.

## 1. Open in PyCharm

1. Open PyCharm.
2. Choose **Open**.
3. Select the existing project folder. Its original folder path is retained to preserve the configured Python interpreter.
4. In **Settings > Python Interpreter**, select an existing local interpreter: `.venv/bin/python` inside this folder. The environment and dependencies have already been installed on this Mac.
5. Use Python 3.10 or newer.
6. Open `run_ivisyx.py`, right-click it, and choose **Run 'run_ivisyx'**.

For robot microphone/speaker audio, open `run_cores3.py` instead and run it with the same interpreter. Close Arduino Serial Monitor and other applications using the USB serial port first.

Your agent ID is already saved in `.env`. Keep that file when opening this project. Allow microphone access if macOS prompts for it. If needed, enable PyCharm under **System Settings > Privacy & Security > Microphone** and restart PyCharm.

## 2. Install dependencies

In PyCharm's Terminal:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

If PyAudio fails on macOS, install PortAudio first:

```bash
brew install portaudio
.venv/bin/python -m pip install -r requirements.txt
```

## 3. Configure secrets safely

For a fresh checkout only, copy the example file. Do not overwrite the configured `.env` on this Mac:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
AGENT_ID=your_agent_id
ELEVENLABS_API_KEY=your_api_key_if_your_agent_is_private
STACKCHAN_PORT=
STACKCHAN_BAUD=115200
```

Never hardcode the API key in Python. `.env` is ignored by Git.

## 4. Configure the ElevenLabs agent

Use agent `agent_5801m4k7sc11f9htwjbpcw7bnm4x` in ElevenLabs. Set its name to **ivisyx** and its system
prompt to the contents of `agent_prompt.txt`. That prompt includes concise replies,
the single-question preflight check-in, and handling for `ivisyx simulation sensor event:`
alerts. Set the separate First Message field to:

```text
I'm ivisyx. Shall we begin your preflight check-in?
```

The agent ID and local environment settings remain unchanged. The original
project directory path is retained to keep PyCharm's interpreter working.

For both audio interfaces, configure input and output audio as **PCM 16 kHz** in the agent settings. If the agent is private, add your API key directly to the local `.env` file. Do not paste it into chat.

### Checklist, reminders, and speech lights

The screen starts with "Pilot support ready" and an unstarted checklist. Say
"start checklist" to begin. The exact preset questions in `agent_prompt.txt`
advance the highlighted item; the completion phrase marks both items done.
This phrase-based fallback requires no extra ElevenLabs tool setup.

For explicit screen updates, add a **client tool** named `update_robot_display`
to the ElevenLabs agent, with these optional parameters:

- `checklist_step`: integer, -1 for not started, 0 for the question, 2 for complete.
- `message`: string, a short reminder, or an empty string to clear it.

Description: "Update the robot's single-question preflight check-in and short reminder."
Enable waiting for the tool response. Python registers the matching handler
locally; it does not create the tool in the ElevenLabs dashboard. Paste the
updated prompt into the agent to enable its tool instructions.

Both six-LED side bars use a mirrored cyan/pink wave during actual speaker
playback, then switch off. The screen says MIC ON during robot microphone
capture; CoreS3 audio uses the actual speaker playback state. Servos are only
commanded by the armed presentation launcher. The firmware enables the body's 5 V output for the LED bars.

## 5. Run the Robot Voice MVP

```bash
.venv/bin/python run_ivisyx.py
```

Say:

```text
Hello ivisyx, can you hear me?
```

Press `Ctrl+C` to end the session. The script prints the ElevenLabs conversation ID when the session closes.
Both `run_ivisyx.py` and `run_cores3.py` use Stack-chan's microphone and speaker.
The robot must be connected; there is no Mac audio fallback.

## 6. Connect Stack-chan over USB

The local `.env` contains the detected CoreS3 port `/dev/cu.usbmodem1101`. The firmware shows audio status, a single-question check-in, reminders, and an annotated camera thumbnail when tracking runs. Conversation transcripts remain on the Mac. The new thumbnail layout requires a physical visual check.

1. Open `arduino/StackChanIvisyx/StackChanIvisyx.ino` in Arduino IDE.
2. Install/select the M5Stack CoreS3 board support and the `M5Unified`, `M5GFX`, `M5CoreS3`, and `M5StackChan` libraries. Use USB Mode **Hardware CDC and JTAG**, with USB CDC On Boot **Enabled**.
3. Upload the sketch to CoreS3.
4. Plug CoreS3 into your Mac.
5. If auto-detection does not work, find the port:

```bash
ls /dev/cu.*
```

Then set it in `.env`:

```bash
STACKCHAN_PORT=/dev/cu.usbmodemXXXX
```

Test robot expressions:

```bash
PYTHONPATH=src .venv/bin/python -m ivisyx.serial_smoke_test
```

The test requires a firmware acknowledgement for each expression and reports rejected commands or missing replies as errors. It ends by verifying the neutral expression.

Then run the voice assistant again. The screen shows audio activity, single-question check-in progress, and a reminder. Tracking launchers add the annotated eye-camera thumbnail. Expression commands remain compatible but do not change the screen. The `status` serial command reports display mode, audio activity, checklist step, reminder, and audio sample counters. `lights:status` reports LED controller and power diagnostics. The presentation launcher explicitly arms the button-triggered pitch motion. Uploading replaces the board's current application.

## 7. Run with CoreS3 audio

The USB audio firmware is already uploaded on this Mac. In PyCharm, run `run_cores3.py`, or use the project Terminal:

```bash
.venv/bin/python run_cores3.py
```

Verified on October 10, 2026: local microphone capture returned nonzero samples; direct speaker tones were confirmed audible; ElevenLabs recognized microphone input and returned reply audio; firmware reported completed reply playback. Spoken reply clarity still requires a physical listening check.

Speak toward the robot's microphones. A first greeting depends on your agent settings; if it stays quiet, say "Hello ivisyx". Audio is sent to ElevenLabs during the session. Press Ctrl+C in the Terminal to end it.

The screen shows microphone or speaking status during audio capture and playback. The CoreS3 audio hardware is half duplex: the microphone pauses during agent playback and resumes one second after the last audio packet. You cannot speak over an agent reply to interrupt it through the robot microphone. Playback volume is set to the maximum, 255/255, in the firmware. Native USB buffers are enlarged to prevent dropped PCM packets.

For a local transport check without contacting ElevenLabs:

```bash
PYTHONPATH=src .venv/bin/python -m ivisyx.audio_smoke_test
```

This records one second in memory, reports sample levels, plays a half-second tone, and shuts down audio. It does not save a recording. A transport acknowledgement does not establish that sound was audible; confirm the sound physically.

## 8. Run tests

These tests require the installed dependencies but do not contact ElevenLabs or require audio hardware or Stack-chan:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

## Troubleshooting

If the serial device disappears, reconnect the USB data cable and power on the robot, then check `STACKCHAN_PORT`. Close Serial Monitor before running Python. If audio commands are rejected, upload the current sketch rather than an older camera-only build. If the session stays quiet, say "Hello ivisyx"; your agent may not send an initial greeting. Keep the room quiet for the first speech test because background speech can trigger the service's turn detection.

The live microphone pauses while replies play, and short gaps between reply packets send silence rather than reopening it. Stop an old run before starting another. `run_ivisyx.py` also uses robot audio; no launcher falls back to Mac audio.

## USB Audio Protocol

Control commands remain newline-delimited. `audio` verifies `audio:pcm_16000:8000:v1`. `mic` captures 4000 mono samples and returns `pcm:8000` plus exactly 8000 binary bytes. `play:N` accepts an even byte count up to 8000, replies `ready:play`, consumes exactly N binary bytes, waits for playback, then replies `ok:play`. `idle` releases both audio devices. Binary packets may contain newlines and are always read by length.

A single Python serial owner locks each complete command and binary packet so conversation state callbacks cannot interleave with audio. Transcriptions and replies are logged on the Mac, not sent to the robot screen. The worker prioritizes playback, drops queued audio on SDK interruption, and sends silence during playback to avoid acoustic echo. `status` begins with `display:status` and includes microphone and speaker sample counters; `speaker:diag` reads the amplifier power state, and `tone` plays a direct 1.5-second diagnostic tone.

Audio protocol v2 queues alternating persistent PCM buffers on the CoreS3 so
the next packet is ready before playback ends. `ok:playq` means accepted, not
finished; `drain` waits for the playback tail. Sample counters count accepted
samples. Protocol v1 remains supported by Python for older firmware.

Speech starts with up to 750 ms of prebuffering (or 750 ms of accumulated PCM)
to absorb initial network jitter. Small fragments are combined before USB
transfer; short replies flush at the timeout. Camera transfers wait while
buffered speech is in flight, and playback drains before the microphone resumes.
The presentation waits for the automatic greeting to finish before sending
START, so the checklist command does not interrupt the first message.
If no greeting arrives, START is sent after five seconds.
