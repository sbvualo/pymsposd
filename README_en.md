# pymsposd
Parses for GPS data from msp-osd (.osd) files.

When searching for GPS and other data, the parser is relies on glyphs, i.e. the glyph of latitude, longitude, km/h, etc., so the parser is not absolutely accurate. Accordingly, sometimes the parser can be wrong, i.e. if the values are displayed on the screen without gap. It is also not possible to reliably recognize a parameter that does not have a unique glyph and is marked with a non-unique measure unit, i.e. km/h.

Tested on:
* DJI Goggles v1 + Betaflight 4.4.2
* DJI Goggles v2 + INAV 6.1.0


Command line example:

```sh
msposd.py -o output.csv input.osd
```
