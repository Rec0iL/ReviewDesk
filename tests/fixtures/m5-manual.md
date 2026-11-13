# M5 manual check (about 15 minutes)

Tick it off in the browser with `python3 tools/check.py m5`: mark what works, write what needs to
change (paste or drop screenshots into a note), then Save (answers go to
`docs/testing/m5-results.md`, screenshots to `docs/testing/m5-results/`).

Map a few things on DP-3, standing in for the projector: anything round, anything with corners,
something curved (a bottle, a bent sheet of paper). The editor stays on DP-2.

```bash
cd ~/LightGrove && ./target/release/lightgrove
```

Open a project with DP-3 as an output and a checker or grid pattern in the Library.

## 1. A freeform surface, drawn on the projector

- [ ] **Surfaces & Content → Draw surface.** Move the mouse onto DP-3 and click around something
      (each click a point; they snap like corners). Backspace takes the last point back.
- [ ] Double-click (or Enter, or click the first point again) finishes: a new surface, selected,
      its points as handles. Give it the pattern.
- [ ] Drag a point; double-click an edge for a new point; Tab picks a point and Delete removes it.
- [ ] Ctrl+Z takes back each of those, one at a time.

## 2. An ellipse with soft edges

- [ ] Add a surface, **Shape → Ellipse**, fit it to something round on DP-3.
- [ ] Set all four **Feather** values to about 0.15: the edge fades all round, evenly.
- [ ] Try a rectangle with only Left feathered: a clean soft band down the left edge, no
      diagonal lines at the corners.

## 3. A grid, bent smoothly, then straight

- [ ] On a surface, **Add detail** twice (4 × 4 grid). The picture doesn't move.
- [ ] Set **Soft radius** to about 200, drag a middle point on DP-3: its neighbours follow, a ring
      shows how far. The checker bends without creases.
- [ ] **Cells: Straight**: each cell flat; it folds at the grid lines. Back to **Smooth**.
- [ ] **Back to corners**, then Ctrl+Z: the grid is back.

## 4. Masking part of a surface

- [ ] Select a surface, **Add mask**, click an outline over part of it (on the stage or DP-3),
      double-click. That part is cut out; its outline shows dashed.
- [ ] **Keep inside**: only that part shows. **Feather** about 30: a soft edge.
- [ ] **On: Canvas**, then move the surface: the mask stays where it is. **On: Surface**: it moves
      along.

## 5. A crop in the Source view

- [ ] Select the content under a surface, **Edit crop** (or **Source** above the stage): the whole
      source, the crop's corners as handles.
- [ ] Drag a corner, and the inside; they snap to the source's edges and middle. DP-3 follows.
- [ ] Put the same source on a second surface: its crop is outlined in the Source view.
- [ ] Esc twice: back to the canvas. **Whole source** resets the crop.

## 6. Undo throughout

- [ ] Ctrl+Z back through all of it. Each drag, drawing, Add detail, mask and crop change is one
      step.

**Not yet:** rotating or scaling whole surfaces; Bézier warps and masks, a mask brush (P2);
slices, soft edges between projectors and output warps (M7).

Tell me what felt off.
