# Griptape Nodes OpenTimelineIO Library

Turn a Fountain script into a timeline. Default clip lengths come from the amount of dialogue, and a timeline widget lets you adjust the timing. Save the timeline as an OpenTimelineIO (OTIO) file, render it to a movie, or turn it back into a script.

<img width="1767" height="1145" alt="image" src="https://github.com/user-attachments/assets/6e228e61-983b-4b12-bd6d-d208757bc74e" />

## How the timeline works

The library has its own timeline format: a plain list of tracks and clips, with every time counted in whole frames. Nodes pass this **timeline** to each other. It is what the Timeline Editor edits.

- **In:** build a timeline from a script (Script to Timeline) or load one from an `.otio` file (Load OTIO).
- **Edit:** the Timeline Editor changes the timeline.
- **Out:** write it as an `.otio` file (Save OTIO), render it to a movie (Timeline to Movie), make a Blender storyboard from it (Timeline to Blender Storyboard) or turn it back into a script (Timeline to Fountain).

OpenTimelineIO (OTIO) is the file format, used to share a timeline with other tools such as Resolve or Hiero. A file only appears at the ends. Between nodes the timeline is passed as it is, because OTIO text is more than twice the size of the same timeline.

## Nodes

| Node | Takes | Gives |
|---|---|---|
| **Load Fountain Script** | a `.fountain` file or typed text (choose with `source`) | the parsed script, the title, a summary |
| **Script to Timeline** | the parsed script | a timeline, the runtime, a summary. Also saves an `.otio` and its media unless `save_otio` is off |
| **Load OTIO** | an `.otio` file | a timeline and a summary of what was in it |
| **Timeline Editor** | a timeline, or an `.otio` file (choose with `source`) | the edited timeline. Also saves it as a file when it has somewhere to put it |
| **Save OTIO** | a timeline | an `.otio` file in a folder, with placeholder media |
| **Timeline to Movie** | a timeline | an H.264 `.mp4` with sound. Video clips are laid on black at their place, every clip with sound is mixed in, spoken lines are drawn as subtitles, and placeholder slates show as title cards. Editor mute buttons are not saved, so they do not apply |
| **Timeline to Blender Storyboard** | a timeline, or an `.otio` file (choose with `source`) | a Blender `.blend` made from Blender's Storyboarding template, to start drawing boards. Each shot becomes its own scene with a camera and a Grease Pencil object, named like the shot and as long as the shot. The Edit scene lays them out as scene strips. Audio clips linked to real footage become sound strips with their in-points. Needs Blender 5.0 or newer, found automatically or chosen in `blender`. The save rules add a version number, so it never replaces an earlier storyboard |
| **Timeline to Fountain** | a timeline | the script as Fountain text, and optionally a `.fountain` file |

```
Load Fountain Script ──► Script to Timeline ──timeline──► Timeline Editor ──edited──► Timeline to Movie
Load OTIO ───────────────────────────────timeline──┘                          └────► Save OTIO
                                         Timeline Editor ──edited──► Timeline to Fountain ──fountain──► Load Fountain Script
```

The `timeline` outputs are not saved with the workflow. They are made again each time a node runs. The edits themselves are kept in the Timeline Editor.

### Breakdown rules

- A shot starts at the first action or dialogue after a scene heading or a transition, and at every action line that begins with a shot cue in capitals (`WIDE SHOT of…`, `CLOSE UP of…`, `ANOTHER ANGLE of…`). The cue list is editable.
- A sequence starts at the first shot, after a transition such as `CUT TO:`, and when a scene switches between INT. and EXT.
- A spoken line lasts its word count divided by `words_per_second`, with a minimum, plus `line_pause`. A shot is as long as its dialogue, with a minimum. Shots without dialogue use `default_shot_seconds`.

### Output folder

Script to Timeline and Save OTIO save into a folder, set up the same way as the standard library's Extract Frames node. `directory` defaults to `{outputs}/timeline_v{###}`. `{outputs}` and other project macros work, and `{###}` counts up (`timeline_v001`, `timeline_v002`, ...) by looking at the folders already there. The gear button creates and connects a FileOutputSettings node instead. `file_name` (default `timeline`) names the `.otio` inside it. An existing file with the same name is replaced.

### Placeholder media

Editors report clips with no media as offline, so the nodes that save an OTIO make placeholder media in a `media` folder next to the file. Turn it off with `placeholder_media`.

- Each shot gets a slate video: a still frame showing its name, sequence, scene heading and description, encoded with ffmpeg as a small `.mov` (about 90 KB each).
- All audio clips share one silent file (`silence_<frames>f.mov`).
- Files are never written over. A file's name holds a hash of what it shows and its length, so editing a clip's name or description changes only the OTIO and, for a placeholder slate, makes a new slate beside the old one. Another timeline that still points at the old slate keeps working. Media you link yourself is never touched.
- Media has handles (`media_handles`, 10 s by default) before and after each clip, so a clip can be lengthened in an editor. A slate is remade when its text changes or the clip outgrows its handles. Media that is still good is reused.
- Pillow draws the slate. ffmpeg comes from `static-ffmpeg`. The engine already depends on both.

### What the OTIO contains

- A **Shots** video track of clips that point at their slates, and one audio track per speaker, plus empty **SFX** and **Audio** tracks.
- Sequence, scene and note markers on the Shots track, as ranged markers.
- Every detail this library adds is under the metadata key `griptape_otio`. Times are whole frames.

### Timeline to Fountain

Turns a timeline back into a script, so edits made in the Timeline Editor can go back into the writing. The scene headings, action, dialogue, parentheticals, transitions, script notes and title page come from what the timeline holds. Edited text, deleted shots and split shots are carried over. In the 17-shot test script, the title page, all 9 scene headings, all 34 dialogue lines (speaker, `(V.O.)` and words) and all 6 transitions come back exactly.

- Shots and lines that are **disabled** in the timeline are left out of the script, so a disabled shot is a way to try the script without it.
- **Timing as notes** writes each shot's length as a Fountain note, for example `[[10.5 s]]`. **Sound clips as notes** writes SFX and audio clips into the shot they start in, for example `[[SFX: car crash at 1:51.9]]`. Both are off by default. Notes do not change what the script says when it is read back.
- Not recovered: the order of action and dialogue inside one shot (action comes first), actions that were separate paragraphs in one shot are written as one, spacing, and `(CONT'D)`.
- `fountain` outputs the text and goes straight into Load Fountain Script's text option. `save_fountain` also saves a versioned `.fountain` through the usual file output. An OTIO that Script to Timeline did not make has no script details, so it gives little or nothing.

### Saving edits

The Timeline Editor works like the annotate node. Choose a `source` (`file` or `timeline`), then choose an `.otio` file or connect a timeline to `timeline`. Only the matching input is shown, so there is no doubt which one is used. It opens in the editor **the first time**. After that the edits belong to the node: they are kept when the workflow is saved, reopened or run, and a new timeline arriving never replaces them. Running the node only reads them.

- **Run** outputs the edited timeline on `edited`.
- **With a file source** it also saves `<name>_edited.otio` in the same folder as the original (never changed), with any new placeholder media in that folder's `media/`. The file is replaced each run, and `edited_file` outputs its path. A file already called `..._edited.otio` is saved over itself.
- **Output File** saves somewhere else, and is the way to save when the timeline came in as text. Its gear connects a FileOutputSettings node. Left alone with no file chosen, nothing is written and only the text comes out.
- **Reload** (the button right under the editor) throws the edits away and opens the input again.

### Timeline Editor widget

**Viewer.** A monitor above the timeline shows what is under the playhead: the shot's slate (name, sequence, scene heading and description), the spoken lines as subtitles, and any SFX or audio clips as chips. It is drawn from the timeline itself, so it follows your edits as you drag. There is no picture or sound yet, so playback shows timing, not footage.

**The bar above the timeline** keeps everything about the selected clip next to where you are looking. All of it is icons (Lucide), and the tooltips appear after about a tenth of a second. On the left are the clip tools: split, delete, add SFX, add audio, and the snap, ripple and link switches. In the middle are the play controls: start, back a frame, play or pause, forward a frame, end, loop. On the right is the playhead time and the total length. The title, the zoom and Expand stay in the header above the viewer.

**Expand** (button or F) opens the editor in a modal, like the annotate widget's: the page behind is dimmed, the editor fills a centred dialog with a title bar and a close button, and the selected clip's details sit on the right. Close it with the X, Collapse, Escape, F, or by clicking the dimmed backdrop. The editor goes back into the node where it was.

**Height.** The timeline takes the height that is left, so stretching the node taller gives it more room. The viewer takes a share of the height, and the details panel keeps a fixed size.

Lanes: sequence and scene bands (worked out from the shots), the Shots track, one lane per speaker, SFX and Audio.

- Drag a clip to move it and drag its edges to trim. Moves and trims stop at neighbouring clips.
- **Snap** snaps to the playhead, to 0 and to other clips' edges, within about 8 screen pixels, and draws a yellow line where it caught. Shots sit edge to edge, so they mostly snap when trimmed. Free clips (dialogue, SFX, audio) snap when moved. **Ripple** makes a shot's new length push everything after it. **Link** keeps a shot's dialogue with it when it moves or is deleted.
- **Split** cuts the selected clip at the playhead. The SFX and audio buttons add clips at the playhead. **Delete** removes the selected clip.
- The viewer plays a clip's linked video, muted, at the frame under the playhead. It plays a small copy (720p H.264, short keyframe spacing, no audio) that the node makes once per linked file in the project's previews folder, because some files cannot be seeked in a browser. The linked file is only read and the OTIO keeps pointing at it. The node makes a URL for each copy when it opens, links or runs the timeline, and keeps them in the editor value under `previews`, not in the OTIO. If a file has no URL or the browser cannot play its format, the viewer keeps showing the slate and says "no preview".
- Linked audio plays while the timeline plays: files linked to clips on the dialogue, SFX and Audio tracks are heard (the placeholder audio is silent, and video clips stay silent). The node makes an AAC `.m4a` copy of each linked audio file in the previews folder, so formats such as AIFF play. The speaker button in an audio track's name column mutes it. Mute is for playback only and is not saved to the OTIO.
- In the clip sidebar, the folder button beside the media field opens the editor's file picker for the node's Media File field, to swap a clip's media. It relies on the editor's page markup. If it is not found, the sidebar says so and the node's Media File field does the same job.
- The widget works at any canvas zoom: drags follow the mouse and the snap distance stays about 8 screen pixels even when the editor canvas is zoomed out.
- Clicking or dragging a clip selects it and leaves the playhead where it is, so a split lands where you put it. Click the ruler, or a scene or sequence band, to place the playhead there. Dragging on the ruler stops at the edge of the lanes and scrolls that way, and the playhead is hidden when it is scrolled out of view, so it never shows through over the track names.
- **The scroll wheel works as in Nuke Studio and Hiero:** the wheel zooms around the cursor, **Option and the wheel pans** sideways, and **Shift and the wheel** scrolls the lanes up and down. A trackpad's sideways swipe pans, and a pinch zooms. Keys: Space play or pause, Home and End, S split, Delete, F expand, Left and Right nudge a selected clip or move the playhead a frame (Shift for 10), Up and Down go to the previous and next clip (see below), + and - zoom, Escape deselect.
- The details panel edits a clip's name, description, start, duration, color and enabled state, and the media it points at (see below).
- **Up and Down** work like Premiere and Resolve. With a clip selected, they select the previous or next clip on its track and put the playhead at its start. With nothing selected, they jump the playhead to the previous or next edit point, which is wherever any clip starts or ends.
- **Zoom** (out, slider, in, fit) sits in the bar above the timeline, on the right next to the time.
- The node outputs only valid timelines, so a half-finished edit never reaches a later node.

Shots can be moved into gaps but not reordered past each other yet.

### Media: placeholder or real

A clip's **Media** row in the details panel shows what it points at. Empty means the placeholder slate, which is made when the node saves.

- **To use real media**, select the clip in the editor, then choose a file with the **Media File** picker on the node, right under the editor. It links the selected clip and empties itself, so the same file can be chosen again. It offers video, audio and image files. A widget cannot open the editor's file picker itself, so the picker is a field on the node and the widget tells the node which clip is selected.
- **Or paste a path** into the sidebar's Media field: a plain path, a `file://` address or a project path such as `{inputs}/plate.mov`. This works while the editor is expanded, when the node's picker is out of reach. Either way it works for shots (video) and dialogue, SFX and audio clips. **Source start** sets where in the file the clip begins, and **Use placeholder** (or clearing the field) goes back to the slate.
- **When the node runs**, the file is found, checked and measured. A file that is missing stops the save and names the clip. A clip longer than its file stops the save and says so. A file whose length cannot be read (a still image) is saved with an unknown length.
- **Trimming** the start of a linked clip moves where it begins in the file, so it still shows the same footage. **Splitting** keeps the link, with the second half starting later in the file.
- **Text is separate from the file.** Changing a linked clip's name or description changes only the OTIO. The linked file is never written to. The viewer still draws a slate and notes `linked: <file>`, because it cannot show footage.
- **Placeholder slates that are out of date.** When you change a shot's name or description, the preview shows the new text but the slate file on disk still shows the old text. The clip gets a dashed border, the viewer gets a dashed amber border and a "Preview differs from the media file" badge, and the Media row explains it. Running the node makes a new slate beside the old one (files are never written over) and the warnings go away.

## Paths

Nodes give their path outputs as project macro paths, such as `{outputs}/timeline_v003/timeline.otio`, so a workflow still finds its files if the project moves. This covers Script to Timeline (`otio_path`, `output_directory`), Save OTIO, the Timeline Editor (`edited_file`) and Timeline to Fountain (`fountain_file`). Every node that takes a path reads macro paths: the Load Fountain Script file, the Load OTIO file, the Timeline Editor file, the Output File, and the media paths typed into a clip or chosen with the picker. A path outside the project stays absolute.

The OTIO itself is the exception. Programs other than this engine read it, and only this engine can resolve a macro, so media addresses inside an OTIO are always absolute `file://` addresses. The editor keeps media paths as they were typed, so they still follow the project when it moves, and the absolute form is only written into the saved file.

## Status

Next: check the widget in the Griptape editor.

## Development

```bash
make install/dev
uv run pytest
node --test tests/js/
make check
```
