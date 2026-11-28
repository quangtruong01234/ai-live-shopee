"""Sizes shared by the scene loader and the layout."""

# The 013 showcase draws the lit main product up to ~0.41·H tall or ~450 px wide on a 480 px frame; FR-028 wants 1.5
# source px per drawn px, also on a 720x1280 frame (ADR-079). A bigger copy only costs memory and resample time.
ART_MAX_SIDE = 960
