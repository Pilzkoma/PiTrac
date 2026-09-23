# Messlauf Triangulation — Ergebnisse

Anleitung: `PROTOCOL.md` daneben. Rohdaten liegen **nicht** in git (je ~35 MB),
sondern datiert unter `sp1_vision/` auf dem Jetson und auf dem Windows-Rechner.

## Stand 2026-09-23

| Frage | Antwort | Belastbarkeit |
|---|---|---|
| Maßstab gegen das Maßband | 1,029 ± 0,017 | **nicht entschieden** — 1 liegt innerhalb 2σ, Budget war ~0,45 % |
| Nicken / Rollen gegen die Auflagefläche | −1,19° / +0,45° | vorläufig |
| Höhe cam1 über der Auflagefläche | 112,8 mm (Annahme 115) | vorläufig |
| Vorzeichen `yaw_from_target_line` | **positiv = Ziellinie rechts** | entschieden |

Alle Werte aus Lauf 5, Schreibtischplatte (Holz) als Auflage, nicht der Boden.
Vorläufig heißt: Lauf 4 ergibt bei **unverändert stehendem Gerät** −1,58° /
+0,20° / 117,0 mm. 4 mm und 0,4° sind mehr, als die Ebenenanpassung
(1,1 mm rms) hergeben sollte. Ungeklärt; Verdacht: Hough-Mitten verschieben
sich mit dem Licht, und Lauf 4 lief bei anderem Licht.

## Die Läufe

| Lauf | Datum | Ordner | Ergebnis |
|---|---|---|---|
| 1 | 2026-08-10 | `2026-08-10_cluttered/` | Lautsprecher vermessen. Außerdem eine Aufnahme zu spät (s. u.). |
| 2 | 2026-08-10 | — | als „Ablesefehler“ abgebrochen — **wahrscheinlich der Pufferfehler** |
| 3 | 2026-08-11 | `2026-08-11_run3_aborted/` | eine Aufnahme; deren Bild ist Fixture `lit_from_one_side` |
| 4 | 2026-09-23 | `2026-09-23_run4_stale_frames/` | **jedes Bild eine Aufnahme zu spät**; umgeordnet auswertbar, Gieren fehlt |
| 5 | 2026-09-23 | `2026-09-23_run5_backlit/` | Zuordnung richtig; Maßstab am Kontrast gescheitert |

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
