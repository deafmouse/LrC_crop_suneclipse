# Adobe Lightroom Classic - crop & align sun eclipse photos

## Problem Statement
Shooting the Sun during a solar eclipse with a telephoto lens on a standard, non-motorized tripod is challenging. Earth's rotation causes the Sun to drift continuously across the frame, and periodic manual repositioning of the camera introduces sudden compositional jumps. To assemble a smooth time-lapse or consistent photo series, every frame must be cropped with the Sun locked dead center.

I use **[Adobe Lightroom Classic](https://www.adobe.com/products/photoshop-lightroom-classic.html)** to manage and edit my photos. I wanted to automate the solar cropping and image alignment while keeping the entire editing workflow strictly non-destructive, allowing me to make additional adjustments later on (such as color grading, exposure balance, or tone curves).

## Problem Analysis
Typical workarounds fail to satisfy these requirements:
* **Manual alignment in Lightroom** across hundreds or thousands of photos is tedious, slow, and lacks sub-pixel precision. Lightroom provides no native automated tool for this.
* **Third-party registration software** (such as PIPP or OpenCV image warpers) requires exporting intermediate TIFFs or PNGs. This breaks the non-destructive RAW workflow; if changes are needed later, every frame must be re-exported and re-processed from scratch. Additionally, it demands substantial extra disk storage, not to mention the processing power required to re-render batches across hundreds of heavy RAW files.
* **Partial crescents break standard algorithms:** Simple thresholding or center-of-mass detection is pulled off-center by the lopsided crescent shape during partial eclipse phases.
* **Lightroom XMP crash hazard:** Lightroom's Camera Raw engine parses XMP sidecars strictly. If an alignment script produces invalid syntax or floating-point `NaN` values, Lightroom Classic crashes immediately upon reading the metadata.

## The Solution
The Python script `crop_sun.py` automatically detects the true geometric center of the Sun (even on thin crescents) using a radius-constrained RANSAC circle fit, and writes standard Adobe crop coordinates directly into each photo's `.xmp` sidecar.

In practice, the workflow is seamless:
1. Save XMP metadata for all target photos in Lightroom (**Metadata → Save Metadata to Files**).
2. Run `crop_sun.py` to compute and write the exact crop bounds.
3. Reload the metadata in Lightroom (**Metadata → Read Metadata from Files**) to apply the centered crops instantly.

All original RAW files remain untouched, and storage overhead is virtually zero (limited only to the tiny `.xmp` sidecars).

## Known Limitations
The script still struggles to detect the geometric center of the Sun during the [Baily's beads phase](https://en.wikipedia.org/wiki/Baily%27s_beads). Because this phase lasts only for a very brief period right before and after totality, only a few manual adjustments are required. During this window, the visible crescent breaks into localized points of light caused by lunar surface topography (mountains and valleys), depending on the exact trajectory and angle at which the Moon traverses the Sun - this makes automated circle fitting unreliable.
