# P0 manual checks (all spikes, in one order)

Collected from the "Manual checks" sections of `docs/spikes/s1…s5`. The order keeps cable work in
one block and puts the X11 logout last, because logging out closes the Claude app.

- Every command writes its results to the spike's `out/` folder. Claude reads them from there, so
  you only need to report the things you see or hear.
- All binaries are built. Each block assumes a fresh terminal.
- Esc closes an S1 output window.

## A. At the desk, no cables (about 15 min)

- [x] **A1. Theme gallery (S4).** Open `spikes/s4-vendoring/out/gallery/contact-sheet.png`, then
      `01-grove.png` and the light themes. Decide whether IBM Plex stays the UI font.
- [x] **A2. Decisions (S4):**
  - Grove theme licence: GPL like the app, or MIT/Apache like the other themes?
  - Frosted blur: is it fine that it's cut?
  - Vendor SolidCraft from `main` or from a tag?
- [x] **A3. Window chrome on Wayland (S4).** Run:
  ```bash
  cd ~/LightGrove/spikes/s4-vendoring && ./target/release/window
  ```
  Check each of these:
  - drag by the title bar, and double-click it to maximise;
  - the minimise, maximise and close buttons;
  - resizing from the edges and corners;
  - the theme dropdown;
  - switching to Deutsch;
  - the Output menu.
- [x] **A4. Placement rerun (S1).** About 45 s of flashing fullscreen windows; don't touch anything
      while it runs.
  ```bash
  cd ~/LightGrove/spikes/s1-present && ./target/release/s1-present --script placement --monitors 0,1 --rounds 20 --out out/real-placement-diag.json
  ```
- [x] **A5. Identify (S5).** Shows a big card on each monitor.
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid identify --seconds 5
  ```
- [x] **A6. A/V sync by ear (S2).** The G435 is wireless, so allow for its latency.
  ```bash
  cd ~/LightGrove/spikes/s2-video && gst-launch-1.0 playbin3 uri=file://$PWD/media/av1080p30_h264_aac.mp4
  ```
  The beep should land about 43 ms after the white square, plus your headset's latency.
  ```bash
  cd ~/LightGrove/spikes/s2-video && ./target/release/s2-video av --secs 30 --loop-end-ms 10000 --volume 0.25 --out out/av-listen.json
  ```
  This one has no picture. Listen for gaps or clicks at the loop points, every 10 s.

## B. Cable work on DP-3 (about 25 min)

Keep the terminal on DP-2, the ultrawide.

- [x] **B1. 20 real replugs (S5).**
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid watch --windows-on DP-3 --log out/replug-dp3.jsonl
  ```
  Repeat this 20 times:
  1. Press Enter and pull DP-3 at the same moment.
  2. Wait for `some outputs waiting`.
  3. Press Enter and plug DP-3 back in.
  4. Wait for `all outputs bound` and the blue "2" card.

  Then press Ctrl-C.
- [x] **B2. Replug with real wgpu outputs (S1).**
  ```bash
  cd ~/LightGrove/spikes/s1-present && ./target/release/s1-present
  ```
  1. Open outputs on both monitors with the default clock strategy.
  2. Pull and replug DP-3 three times.
  3. Note whether the DP-3 output comes back, and whether DP-2 keeps running.
- [x] **B3. Cable swap (S5).**
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid list | grep -E "^  DP-[23] +enabled" && ./target/release/s5-edid watch --log out/swap.jsonl
  ```
  1. Swap both DP cables at the GPU.
  2. Expect a `resolve` line with no `WRONG`.
  3. Press Ctrl-C, and run the `list` part again.
  4. Swap the cables back.
- [x] **B4. Standby and power-off (S5).**
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid watch --log out/standby.jsonl
  ```
  Then, in a second terminal:
  ```bash
  kscreen-doctor --dpms off --dpms-excluded DP-2
  ```
  1. Wait 60 s, then wake the screen with the mouse.
  2. Switch DP-3 off at its power button, wait 30 s, and switch it on again.
  3. Press Ctrl-C.
- [x] **B5. Flatpak event delivery (S5).** Each probe waits 30 s; replug DP-3 once during each wait.
  ```bash
  B=~/LightGrove/spikes/s5-edid; flatpak run --system --filesystem=$B --socket=wayland --device=dri --share=ipc --command=$B/target/release/s5-edid org.freedesktop.Platform//26.08 probe --wait 30
  ```
  ```bash
  B=~/LightGrove/spikes/s5-edid; flatpak run --system --filesystem=$B --socket=wayland --device=dri --share=ipc --share=network --command=$B/target/release/s5-edid org.freedesktop.Platform//26.08 probe --wait 30
  ```
  ```bash
  B=~/LightGrove/spikes/s5-edid; flatpak run --system --filesystem=$B --socket=wayland --device=all --share=ipc --share=network --filesystem=/run/udev:ro --command=$B/target/release/s5-edid org.freedesktop.Platform//26.08 probe --wait 30
  ```
  Then do three replugs inside the sandbox (Enter and pull, as in B1), and press Ctrl-C:
  ```bash
  B=~/LightGrove/spikes/s5-edid; flatpak run --system --filesystem=$B --socket=wayland --device=dri --share=ipc --command=$B/target/release/s5-edid org.freedesktop.Platform//26.08 watch --log $B/out/replug-flatpak.jsonl
  ```

## C. 125 % scaling (about 5 min)

- [x] **C1. Pixel-exact output (S1).**
  1. In KDE's display settings, set DP-3 to 125 %.
  2. Run `./target/release/s1-present` in `spikes/s1-present` and open an output on DP-3.
  3. Look at the top-left checkerboard up close, or take a phone macro photo. Every pixel should
     alternate black and white, with no grey moiré.
  4. Set DP-3 back to 100 %.

## D. X11 session: dropped (2026-11-12; X11 is no longer a target)

Plasma 6.8 drops X11, so this only matters if you want to run shows on X11 with Plasma 6.7.

- [ ] **D0.** Install the session, which needs sudo:
  ```bash
  sudo dnf install plasma-workspace-x11
  ```
  Then log out and pick "Plasma (X11)".
- [ ] **D1. Pacing (S1):**
  ```bash
  cd ~/LightGrove/spikes/s1-present && ./target/release/s1-present --script pacing --strategy clock --monitors 0,1 --seconds 30
  ```
- [ ] **D2. EDID via RandR (S5):**
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid list --json out/list-x11.json
  ```
  Then do three replugs (as in B1, Enter marks) and run Identify:
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid watch --log out/replug-x11.jsonl
  ```
  ```bash
  cd ~/LightGrove/spikes/s5-edid && ./target/release/s5-edid identify
  ```
- [ ] **D3. Window chrome on X11 (S4).** Repeat A3.

## After the checks (Claude)

- [x] S2 reruns its final chain on the now quiet machine (zero-copy soak, A/V runs, Flatpak NVDEC,
      software-decode capacity, about 25 min). This also covers S2's manual check 2.
- [x] Claude analyses every `out/` file and fills in the open rows in the spike docs.
- [x] Claude folds all five verdicts into `docs/PLAN.md` and `tasks/todo.md`.

## Not checkable on this machine (stays open)

- **S2:**
  - zero-copy inside Flatpak (needs the M9 manifest);
  - AMD and Intel VA decode.
- **S3:**
  - AMD, Intel and Pi pre-emption;
  - building glslang-sys in the Flatpak SDK;
  - optionally, spot-checking the 13 black renders on shadertoy.com.
- **Already done:**
  - S3 runaway stutter and image comparison;
  - S4 KDE config: `kwinoutputconfig.json` has no `Virtual-N` entries.
