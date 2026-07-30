# Optional bundled fonts

`utils/export.py` checks this folder **first** when picking a font for
non-English text in "Download as Image" / "Download as PDF".

You usually don't need to add anything here:
- On Windows (local dev), it already finds Nirmala UI (Tamil/Hindi/other
  Indic scripts), Arial, and DengXian (Chinese) automatically from
  `C:\Windows\Fonts`.
- In Docker/Render, the Dockerfile installs `fonts-noto` and
  `fonts-noto-cjk`, which cover the same scripts on Linux.

Only drop a `.ttf`/`.ttc` file here if a script you need still shows the
"couldn't render" fallback note in PDF downloads - e.g. for Arabic,
Thai, or another script not covered above. Google Fonts' "Noto Sans"
family (https://fonts.google.com/noto) has a free font for almost every
script; grab the matching one and place it here, e.g.
`NotoSansArabic-Regular.ttf`.