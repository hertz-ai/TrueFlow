# Visual Inspection Checklist - Ultimate Architecture Visualization

**Purpose**: Manual quality assurance checklist for reviewing generated videos
**When to use**: After fixing bugs and before deployment
**Who**: QA testers, developers, stakeholders

---

## Pre-Inspection Setup

### 1. Generate Test Videos
```bash
# Generate 3 test videos with different traces
python ultimate_architecture_viz.py <small_trace.json>   # 5-10 calls
python ultimate_architecture_viz.py <medium_trace.json>  # 20-50 calls
python ultimate_architecture_viz.py <large_trace.json>   # 100+ calls
```

### 2. Prepare Viewing Environment
- [ ] Use video player with frame-by-frame control (VLC recommended)
- [ ] View on 1080p or higher resolution screen
- [ ] Ensure good lighting (no glare)
- [ ] Have notepad ready for observations

### 3. Reference Materials
- [ ] Have trace JSON file open for comparison
- [ ] Keep color specification chart handy
- [ ] Review 3Blue1Brown style guidelines

---

## Phase 1: Architecture Overview (0-10s)

### Scene Entry (0-2s)
- [ ] **Title Appearance**: "Embodied AI: Complete Architecture Walkthrough"
  - [ ] Text is gold color
  - [ ] Text is bold
  - [ ] Font size is large (40pt)
  - [ ] Positioned at top edge
  - [ ] Write animation is smooth
  - [ ] Appears in ~1.5 seconds

- [ ] **Background Color**: Dark gray (#1a1a1a)
  - [ ] Consistent throughout
  - [ ] No flickering
  - [ ] Good contrast with text

### Architecture Build (2-8s)
- [ ] **Phase Title**: "Phase 1: System Architecture"
  - [ ] Blue color
  - [ ] Font size 36pt
  - [ ] Positioned at top
  - [ ] Fades in smoothly

- [ ] **Layer Titles**: Check each layer
  - [ ] "Input/Sensor" - Green - Z-depth 0
  - [ ] "Encoder" - Blue - Z-depth -3
  - [ ] "Processing" - Purple - Z-depth -6
  - [ ] "Memory" - Orange - Z-depth -9
  - [ ] "Output/Decoder" - Red - Z-depth -12

  For each layer title:
  - [ ] Correct color
  - [ ] Readable font size (22pt, scaled by depth)
  - [ ] Billboard effect (always faces camera)
  - [ ] Positioned left of modules

- [ ] **Module Boxes**: Check each module
  For each module:
  - [ ] Cube shape (not distorted)
  - [ ] Correct color (matches layer)
  - [ ] Proper opacity (~0.75)
  - [ ] Sheen effect visible (subtle highlight)
  - [ ] Positioned at correct Z-depth
  - [ ] GrowFromCenter animation smooth

- [ ] **Module Labels**: Check each label
  - [ ] Module name truncated to 18 chars
  - [ ] White text on dark background
  - [ ] Background panel has padding
  - [ ] Billboard effect works
  - [ ] Positioned below module box
  - [ ] Font size 13pt (scaled by depth)

- [ ] **Call Count Labels**: Check each
  - [ ] Shows "N calls" format
  - [ ] Gray color
  - [ ] Positioned above module box
  - [ ] Font size 10pt
  - [ ] Accurate count (compare to trace JSON)

### Camera Movement (8-14s)
- [ ] **Ambient Rotation**:
  - [ ] Starts after modules appear
  - [ ] Rotates clockwise
  - [ ] Speed is comfortable (rate=0.08)
  - [ ] Lasts ~6 seconds
  - [ ] Shows all sides of architecture
  - [ ] No jumping or stuttering

- [ ] **3D Depth Perception**:
  - [ ] Can see Z-depth differences
  - [ ] Layers appear stacked
  - [ ] Near layers larger than far layers
  - [ ] Perspective is consistent

### Transition (14-16s)
- [ ] **Architecture Shrink**:
  - [ ] Scales to 0.5× size
  - [ ] Moves to upper-left corner
  - [ ] Animation is smooth (2 seconds)
  - [ ] Uses smooth rate function
  - [ ] Phase title fades out
  - [ ] Architecture stays visible

**Phase 1 Overall**:
- [ ] Total duration ~15 seconds
- [ ] No visual glitches
- [ ] Smooth flow between sections
- [ ] All text readable at all times
- [ ] Colors are consistent

---

## Phase 2: Execution Walkthrough (10-40s)

### Scene Entry (0-2s)
- [ ] **Phase Title**: "Phase 2: Execution Walkthrough"
  - [ ] Green color
  - [ ] Font size 36pt
  - [ ] Fades in smoothly

- [ ] **Camera Reset**:
  - [ ] Moves back to origin
  - [ ] Sets to phi=70°, theta=-45°
  - [ ] Animation is smooth (2 seconds)
  - [ ] Rate function is smooth

### Call Visualization (2-30s)
- [ ] **Call Boxes**: Check several calls
  For each call:
  - [ ] Small cube (side_length=0.5)
  - [ ] Blue color
  - [ ] Opacity ~0.7
  - [ ] Sheen effect visible
  - [ ] GrowFromCenter animation smooth
  - [ ] Positioned according to depth

- [ ] **Call Labels**: Check several
  - [ ] Function name truncated to 20 chars
  - [ ] White text
  - [ ] Dark background panel
  - [ ] Billboard effect works
  - [ ] Positioned below call box

- [ ] **Data Flow Arrows**: Check several
  - [ ] Curved Bezier path
  - [ ] Yellow color
  - [ ] Smooth arc (not straight line)
  - [ ] Appears between consecutive calls
  - [ ] Create animation is smooth

- [ ] **Flow Particles**: Check several
  - [ ] 3 particles per flow
  - [ ] Yellow color
  - [ ] Sphere shape (small)
  - [ ] Move along arrow path
  - [ ] MoveAlongPath is smooth
  - [ ] Fade out after animation

- [ ] **Module Pulsing**: Check several
  - [ ] Corresponding module highlights
  - [ ] Opacity increases to 1.0
  - [ ] Scale increases to 1.1×
  - [ ] Returns to normal
  - [ ] Animation is quick (~0.4s total)

### Pacing
- [ ] **Call Display Rate**:
  - [ ] Each call appears in ~0.3s
  - [ ] Wait every 10 calls (~0.2s)
  - [ ] Not too fast (can follow)
  - [ ] Not too slow (maintains interest)

- [ ] **Overall Duration**:
  - [ ] Proportional to call count
  - [ ] ~0.5s per call average
  - [ ] Max 50 calls shown
  - [ ] Warning if truncated? (currently no)

**Phase 2 Overall**:
- [ ] Clear execution flow
- [ ] Data movement is evident
- [ ] Can track program flow
- [ ] Not overwhelming
- [ ] Phase title fades out at end

---

## Phase 3: Error Visualization (if errors present)

### Scene Entry
- [ ] **Phase Title**: "Phase 3: Error Analysis"
  - [ ] Red color (matches error theme)
  - [ ] Font size 36pt
  - [ ] Fades in smoothly

### Error Display
For each error shown (up to 5):
- [ ] **Module Highlighting**:
  - [ ] Error module turns red
  - [ ] Opacity increases to 1.0
  - [ ] Color change is smooth (0.5s)
  - [ ] Module stays highlighted

- [ ] **Error Message**:
  - [ ] Shows "Error: <message>"
  - [ ] Message truncated to 50 chars
  - [ ] Red text
  - [ ] Dark background panel
  - [ ] Billboard effect works
  - [ ] Positioned above module
  - [ ] Font size 14pt
  - [ ] Visible for ~1 second
  - [ ] Fades out smoothly

- [ ] **Error Sequence**:
  - [ ] Shows up to 5 errors
  - [ ] One at a time
  - [ ] Clear which module failed
  - [ ] Error message is readable

**Phase 3 Overall**:
- [ ] Errors are obvious
- [ ] Red color theme is consistent
- [ ] Not too much text at once
- [ ] Phase title fades out at end

**Note**: If no errors, Phase 3 is skipped (correct behavior)

---

## Phase 4: Statistics Summary (last 10s)

### Scene Entry
- [ ] **Phase Title**: "Phase 4: Performance Summary"
  - [ ] Purple color
  - [ ] Font size 36pt
  - [ ] Fades in smoothly

### Bar Chart
- [ ] **Chart Structure**:
  - [ ] Shows top 5 modules by call count
  - [ ] Bars grow from bottom edge
  - [ ] Positioned in lower center
  - [ ] Clear separation between bars

- [ ] **Bar Properties**: Check each bar
  - [ ] Width 0.5 units
  - [ ] Height proportional to calls
  - [ ] Color gradient (green → red)
  - [ ] Fill opacity 0.8
  - [ ] No stroke
  - [ ] GrowFromEdge animation smooth

- [ ] **Bar Labels**: Check each
  - [ ] Module name truncated to 15 chars
  - [ ] Shows "<name>\n<N> calls"
  - [ ] White text
  - [ ] Dark background
  - [ ] Positioned above bar
  - [ ] Font size 12pt

- [ ] **Chart Accuracy**:
  - [ ] Top 5 matches actual data
  - [ ] Heights are proportional
  - [ ] Counts are correct (compare to JSON)

### Summary Text
- [ ] **Total Summary**:
  - [ ] Shows "Total: N calls across M modules"
  - [ ] Gold color
  - [ ] Font size 18pt
  - [ ] Positioned below chart
  - [ ] Accurate counts
  - [ ] Fades in after bars

### Exit
- [ ] **Fade Out**:
  - [ ] Phase title fades
  - [ ] All bars fade
  - [ ] All labels fade
  - [ ] Summary text fades
  - [ ] Animation is smooth (1 second)
  - [ ] Leaves clean screen

**Phase 4 Overall**:
- [ ] Statistics are clear
- [ ] Chart is easy to read
- [ ] Colors help understanding
- [ ] Numbers are accurate

---

## Overall Video Quality

### Technical Quality
- [ ] **Resolution**: 1080p (1920×1080)
- [ ] **Frame Rate**: 30 FPS
- [ ] **Codec**: H.264 (MP4)
- [ ] **File Size**: 5-50 MB (reasonable)
- [ ] **Duration**: 30s - 5 min (depends on trace)
- [ ] **Audio**: None (expected)

### Visual Quality
- [ ] **No Artifacts**:
  - [ ] No pixelation
  - [ ] No banding in gradients
  - [ ] No compression artifacts
  - [ ] No aliasing on edges

- [ ] **Smooth Playback**:
  - [ ] No stuttering
  - [ ] No frame drops
  - [ ] Consistent frame timing
  - [ ] Smooth animations throughout

### Readability
- [ ] **Text Clarity**:
  - [ ] All text is readable
  - [ ] Font sizes are appropriate
  - [ ] High contrast everywhere
  - [ ] No text overlap
  - [ ] No text clipping

- [ ] **Visual Hierarchy**:
  - [ ] Important info is prominent
  - [ ] Supporting info is subtle
  - [ ] Clear focus at all times
  - [ ] Not cluttered

### 3Blue1Brown Style Compliance
- [ ] **Smooth Transitions**:
  - [ ] No abrupt changes
  - [ ] rate_func=smooth used
  - [ ] run_time values appropriate
  - [ ] Animations feel natural

- [ ] **Clear Purpose**:
  - [ ] Every animation has meaning
  - [ ] Nothing is just decoration
  - [ ] Viewer understands why
  - [ ] Flow is logical

- [ ] **Professional Polish**:
  - [ ] Consistent color scheme
  - [ ] Clean visual design
  - [ ] Attention to detail
  - [ ] No obvious bugs

---

## Edge Cases to Check

### Small Trace (< 10 calls)
- [ ] Doesn't look empty
- [ ] Pacing is not too slow
- [ ] Statistics make sense
- [ ] Video feels complete

### Medium Trace (20-50 calls)
- [ ] Pacing is comfortable
- [ ] Not too fast to follow
- [ ] Not too slow to bore
- [ ] All phases feel balanced

### Large Trace (100+ calls)
- [ ] Truncation at 50 is clear (or should add warning?)
- [ ] Doesn't feel rushed
- [ ] Statistics still accurate
- [ ] Performance is acceptable

### Trace with Many Layers
- [ ] All layers visible
- [ ] Z-depth is clear
- [ ] No overlap issues
- [ ] Camera captures all

### Trace with Few Layers
- [ ] Doesn't look sparse
- [ ] Camera angle is good
- [ ] Layout makes sense
- [ ] Not too zoomed in

### Trace with Errors
- [ ] Phase 3 appears
- [ ] Errors are clear
- [ ] Not overwhelming
- [ ] Red theme consistent

### Trace with No Errors
- [ ] Phase 3 skipped (correct)
- [ ] Smooth transition 2→4
- [ ] No awkward pause
- [ ] Flow is natural

---

## Common Issues to Watch For

### Text Issues
- [ ] **No Overlap**: Labels don't overlap each other
- [ ] **No Clipping**: Text not cut off at edges
- [ ] **Consistent Sizing**: Similar elements same size
- [ ] **Background Coverage**: Panels fully cover text

### Animation Issues
- [ ] **No Jumps**: All movements are smooth
- [ ] **No Flicker**: No rapid on/off
- [ ] **Timing Correct**: Not too fast or slow
- [ ] **Synchronized**: Related items move together

### Layout Issues
- [ ] **Proper Spacing**: Elements not too close
- [ ] **Alignment**: Text aligned consistently
- [ ] **Depth Ordering**: Near objects occlude far objects
- [ ] **Screen Bounds**: Nothing goes off-screen

### Performance Issues
- [ ] **Rendering Time**: Acceptable for trace size
- [ ] **File Size**: Not unreasonably large
- [ ] **Playback**: Smooth on target hardware
- [ ] **Memory**: Doesn't crash on generation

---

## Comparison Tests

### Compare Against Original Trace
- [ ] **Call Count**: Matches JSON
- [ ] **Module Count**: Matches JSON
- [ ] **Error Count**: Matches JSON
- [ ] **Call Sequence**: Follows JSON order
- [ ] **Module Names**: Match JSON (truncated ok)

### Compare Against Specification
- [ ] **Phase 1 Colors**: Match spec
  - Input/Sensor: GREEN ✓
  - Encoder: BLUE ✓
  - Processing: PURPLE ✓
  - Memory: ORANGE ✓
  - Output/Decoder: RED ✓

- [ ] **Phase Structure**: Match spec
  - Phase 1: 10 seconds ✓
  - Phase 2: 10-40 seconds ✓
  - Phase 3: If errors ✓
  - Phase 4: Last 10 seconds ✓

- [ ] **Font Sizes**: Match spec
  - Title: 40pt ✓
  - Phase titles: 36pt ✓
  - Layer titles: 22pt ✓
  - Module labels: 13pt ✓
  - Call counts: 10pt ✓

---

## Acceptance Criteria

### Must Pass (Mandatory)
- [ ] All 4 phases render without errors
- [ ] No crashes during generation
- [ ] Video file is created and playable
- [ ] All text is readable
- [ ] Animations are smooth
- [ ] Colors are correct
- [ ] Duration is appropriate
- [ ] File size is reasonable

### Should Pass (Important)
- [ ] 3D depth is perceptible
- [ ] Flow is easy to follow
- [ ] Statistics are accurate
- [ ] Errors are obvious (if present)
- [ ] No visual glitches
- [ ] Professional appearance
- [ ] Matches 3Blue1Brown style

### Nice to Have (Optional)
- [ ] Impressive visual effects
- [ ] Intuitive understanding
- [ ] Educational value
- [ ] Shareable quality
- [ ] Documentation-ready

---

## Sign-Off

### Inspector Information
- **Name**: _________________
- **Date**: _________________
- **Trace File Tested**: _________________
- **Video Duration**: _________________
- **Playback Environment**: _________________

### Overall Assessment
- [ ] **PASS** - Ready for production
- [ ] **PASS WITH NOTES** - Minor issues noted, acceptable
- [ ] **FAIL** - Major issues, must fix

### Critical Issues Found
1. _________________________________________________
2. _________________________________________________
3. _________________________________________________

### Minor Issues Found
1. _________________________________________________
2. _________________________________________________
3. _________________________________________________

### Recommendations
_________________________________________________
_________________________________________________
_________________________________________________

### Approval
- [ ] Approved for deployment
- [ ] Approved for plugin integration
- [ ] Approved for documentation

**Signature**: _________________
**Date**: _________________

---

**End of Checklist**
