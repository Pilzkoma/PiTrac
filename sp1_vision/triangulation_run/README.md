# Messlauf Triangulation — Ergebnisse

Anleitung: `PROTOCOL.md` daneben. Rohdaten liegen **nicht** in git (je ~35 MB),
sondern datiert unter `sp1_vision/` auf dem Jetson und auf dem Windows-Rechner.

## Stand 2026-09-24

| Frage | Antwort | Belastbarkeit |
|---|---|---|
| Maßstab | **+1,1 %, korrigiert** | **entschieden 2026-09-24 — ohne Messlauf.** Das Kalibrierbrett hat 24,27 mm statt 24,0 mm Felder (Lineal über 8 und 5 Felder); die Basislinie ist jetzt 79,64 mm. Siehe `calibration_images/README.md` |
| Nicken / Rollen gegen den **Boden** | −1,55° / −0,50° | Lauf 6, `--refiner contrast`, Ebene 2,1 mm rms |
| Höhe cam1 über dem Boden | 117,5 mm (Annahme 115) | Lauf 6, mit korrigiertem Maßstab |
| Vorzeichen `yaw_from_target_line` | **positiv = Ziellinie rechts** | entschieden (Lauf 5) |

**Die Messläufe mit ruhendem Ball sind abgeschlossen.** Die Frage, die sie
beantworten sollten, hing an einer einzigen Zahl — der Feldgröße des
Kalibrierbretts —, und die ließ sich direkt messen. Ein Lauf 7 wurde bewusst
nicht gemacht: Raumlicht und lange Belichtung sind nicht die Bedingungen, unter
denen das Gerät arbeitet. Weiter geht es mit Aufnahmen unter dem IR-Blitz.

Lauf 6 stand auf dem Boden, Läufe 4/5 auf der Schreibtischplatte — ein
anderes Rollen ist deshalb kein Widerspruch. Nicken und Höhe von Lauf 6
treffen Lauf 4 (−1,58°, 117,0 mm); Lauf 5 (−1,19°, 112,8 mm) war der Ausreißer,
und seine Hough-Mitten auf kontrastloser Szene sind die naheliegende Erklärung.
(Die Höhen der Läufe 4 und 5 stammen noch vom alten Maßstab; mit 1,01125
multipliziert: 118,3 und 114,1 mm.)

## Die Läufe

| Lauf | Datum | Ordner | Ergebnis |
|---|---|---|---|
| 1 | 2026-08-10 | `2026-08-10_cluttered/` | Lautsprecher vermessen. Außerdem eine Aufnahme zu spät (s. u.). |
| 2 | 2026-08-10 | — | als „Ablesefehler“ abgebrochen — **wahrscheinlich der Pufferfehler** |
| 3 | 2026-08-11 | `2026-08-11_run3_aborted/` | eine Aufnahme; deren Bild ist Fixture `lit_from_one_side` |
| 4 | 2026-09-23 | `2026-09-23_run4_stale_frames/` | **jedes Bild eine Aufnahme zu spät**; umgeordnet auswertbar, Gieren fehlt |
| 5 | 2026-09-23 | `2026-09-23_run5_backlit/` | Zuordnung richtig; Maßstab am Kontrast gescheitert |
| 6 | 2026-09-24 | `2026-09-24_run6_towel/` | Kontrast gut; Lage und Höhe gemessen; ohne Marken kein Maßstab |

### Der Pufferfehler (behoben in `35ca2db`)

Bis `35ca2db` lieferte `CameraPair.grab_with_skew` nach einer Pause das Bild,
das der Treiber seit dem vorigen Lesen zurückgehalten hatte — trotz
`BUFFERSIZE 1`. `cli_triangulate` wartet auf Enter und liest einmal, also
zeigte jede Aufnahme den Ball an der Marke der **vorigen** Aufnahme, und die
erste zeigte den Stand beim Öffnen der Kameras. Live sah das aus wie „misst
immer zu kurz“ (der Bediener hat es so beobachtet und hatte recht).
Nachgewiesen durch Umschalten der Belichtung zwischen zwei Aufnahmen: das
erste Bild danach hatte in beiden Kameras noch die alte Helligkeit.

Betroffen: alle Läufe 1–4 und die Fixtures `lit_from_one_side`,
`cluttered_ball`, `cluttered_decoy` (Ablesewerte korrigiert in
`tests/fixtures/ball_pairs/README.md`). Nicht betroffen: die Kalibrierung vom
2026-08-09 (beide Kameras hielten denselben Moment, und ein Kalibrierpaar
trägt keinen eingetippten Wert) und nach Prüfung `measured_300mm`.

### Lauf 4 — umgeordnet

Mit jedem Bild dem Wert der vorigen Aufnahme zugeordnet (Original-`run.json`
unverändert, Umordnung nur in einer Kopie): Maßstab 0,980 ± 0,014, Nicken
−1,58°, Rollen +0,20°, Höhe 117,0 mm, Ebene 1,15 mm rms bei `conditioning`
0,675. Die Ziellinien-Position 620/100 rechts wurde nie aufgenommen.

### Lauf 5 — Detektor gegen eine kontrastlose Szene

18 von 26 Aufnahmen gefunden (inkl. zwei nachgereichter Ziellinien-Aufnahmen
gs_25/26). Tiefenlinie 1,6 mm rms gerade, 2,0° schräg; Ebene 1,12 mm rms,
`conditioning` 0,513; Gieren +24,5° (ferner Ball 112 mm rechts der
Tiefenlinie, nicht 100).

**Warum der Maßstab nicht entschieden ist** — gemessen am ruhenden Ball
gs_17/gs_18, Graustufen:

| | Ball | Tisch daneben | Kontrast | Rauschen |
|---|---|---|---|---|
| cam1 | 61,5 | 73,5 | 12 | 2,1 |
| cam2 | 57,7 | 59,0 | **1,3** | 2,2 |

Von hinten beleuchtet, auf hellem Holz: in cam2 ist der Ball so hell wie der
Tisch. Folgen, jede einzeln belegt:

* **Präzisionsstufe bei keiner einzigen Aufnahme angenommen.** `refine_ball`
  nimmt je Richtung die äußerste Kante; in cam1 sind das die Kante des
  anliegenden Lineals und der Schattenrand (gs_09: r 58 → 69), oder es gibt
  in einer Kamera ganz auf (7 von 18). Alle Z-Werte sind rohe Hough-Mitten.
* **Hough-Mitten liegen auf einem 1-px-Raster.** Derselbe unberührte Ball
  (gs_17/18) ergab 684,9 und 678,1 mm — ein Kreis sprang in cam2 um 1 px.
  Die 7,6 mm Wiederholstreuung sind Detektor, nicht Platzierung.
* **8 Fehlschläge bei klar sichtbarem Ball:** 5 am Größentor (Hough-Radien
  21–26 % zu groß, Tor 20 %), 1 am Radiusverhältnis, 2 ohne Kandidat.

Ein Wegwerf-Experiment (Ballinneres aus cam1 in cam2 wiederfinden, statt zwei
Kreise zu fitten) brachte den ruhenden Ball auf 0,6 mm, sprang aber über die
Positionen auf benachbarte Dellen und war insgesamt nicht besser als Hough.
Auf Bildern mit 1,3 Graustufen Kontrast lässt sich keine Detektorvariante
fair bewerten; deshalb ändert Lauf 6 die Szene (Tuch, Licht von vorn, kein
Lineal am Ball — PROTOCOL.md Abschnitt 2 Punkte 5–7).

**Nebenbefund:** Die automatische Belichtung stand im Dämmerlicht bei 40 ms.
Die Kameras liefen damit mit ~25 statt 120 Bildern pro Sekunde, daher der
Kameraversatz von 15–19 ms statt 3 ms. Für ruhende Bälle egal, für den
fliegenden Ball nicht.

### Lauf 6 — dunkles Tuch, das im Infrarot hell ist

Schwarzes Handtuch auf dem Boden, Lampe seitlich vor dem Gerät, keine
`--exposure`-Option (skew 10,8 ms). Kontrastprüfung am Probeschuss:
+66 / +70 Graustufen (Ziel > 40; Lauf 5: −19 / −5). 20 von 24 Aufnahmen
gefunden. **Keine Marken:** der Ball wurde von 300 bis 650 jeweils nach
Augenmaß um 5 cm weitergelegt, die eingetippten Werte sind Sollwerte.

**Der Detektor hat die ferne Hälfte nicht vermessen.** Das Handtuch ist für
die Kameras hellgrau (~115). `refine_ball` setzt seine Canny-Schwellen aus
der Helligkeit (≈ 75/150), die Randkante eines Balls bei 650 mm hat ≈ 50 —
ab 550 mm gab die Verfeinerung in jeder Aufnahme auf, es blieben rohe
Hough-Kreise, teils 4 px daneben (#7: Sollwert 600, Z 581). Neu:
`refine_ball_by_contrast` und `--analyse … --refiner contrast`, das einen
ganzen Lauf mit einer Methode vermisst. Pro Aufnahme zwischen den Methoden
zu wechseln, wurde gemessen und verworfen (Maßstab 0,961 → 0,931: jede
Methode hat ihren eigenen kleinen Versatz, und der wechselt dann mit der
Entfernung).

| | Canny (Standard) | `--refiner contrast` |
|---|---|---|
| Tiefenreihe, Residuum | 13,4 mm | **4,4 mm** |
| Wiederholstreuung | 15,9 mm | 5,4 mm |
| Ebene rms (conditioning) | 3,1 mm (0,57) | 2,1 mm (0,60) |
| Nicken / Rollen | −1,95° / −0,72° | −1,56° / −0,50° |
| Höhe cam1 | 120,4 mm | 116,6 mm |
| Maßstab gegen Sollwerte | 0,961 ± 0,029 | 0,961 ± 0,010 |

Nicht gefunden: #10, #16 (kein passendes Paar), #20/#22 (rechts seitlich,
Größentor), #23 (Logo erzeugt einen zweiten Kreis → `ambiguous`; damit fehlt
auch das Gieren). #20 ist als Serie `d` statt `s` eingetragen.
