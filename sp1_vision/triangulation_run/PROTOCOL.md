# Messlauf Triangulation — Anleitung für das Gerät

> **Abgeschlossen am 2026-09-24.** Die Maßstabsfrage, für die diese Anleitung
> geschrieben wurde, ist mit einem Lineal am Kalibrierbrett beantwortet
> (`calibration_images/README.md`); Lage und Höhe liefert Lauf 6. Die
> Anleitung bleibt für den Fall, dass ein ruhender Lauf noch einmal nötig wird.

Stand 2026-09-24. Gilt für `sp1_vision/cli_triangulate.py` ab Commit `35ca2db`
— **nicht davor**: bis dahin zeigte jede Aufnahme den Ball an der Marke der
VORIGEN Aufnahme (der Treiber hielt ein Bild zurück). Alle Läufe vor dem
2026-09-23 sind davon betroffen. Die Ergebnisse stehen in `README.md` daneben.

> **Vor jedem Lauf das Verzeichnis leeren**, sonst zählt das Werkzeug hinter
> alte Aufnahmen weiter. Nicht löschen, datiert wegschieben:
>
> ```bash
> cd ~/JetsonLM/sp1_vision
> mkdir JJJJ-MM-TT_runN && mv triangulation_run/cam1 triangulation_run/cam2 \
>    triangulation_run/run.json JJJJ-MM-TT_runN/
> ```

**Was der Lauf beantworten soll**

1. Stimmt die Triangulation gegen ein unabhängiges Längenmaß — und auf wie viel
   Prozent genau lässt sich das sagen? **Offen.** Lauf 5 hatte zu wenig
   Kontrast (s. u.); Lauf 6 hatte Kontrast, aber **keine Marken** — der Ball
   wurde nach Augenmaß um 5 cm weitergelegt, und dann misst der Lauf die
   Schrittlänge des Bedieners statt der Geometrie.
2. Wie sitzt das Gerät gegenüber dem Boden? Nicken, Rollen, Montagehöhe.
   **Gemessen** in Lauf 6 (−1,56° / −0,50° / 116,6 mm).
3. Welches Vorzeichen hat `yaw_from_target_line` physikalisch? **Beantwortet
   2026-09-23: positiv = Ziellinie rechts.** Die Aufnahmen 23/24 bleiben
   trotzdem im Lauf, sie kosten nichts.

Punkt 1 ist knapp: das Signal ist 0,6 %, das Budget dieses Aufbaus liegt bei
~0,45 %. Deshalb hängt einiges an der Sorgfalt unten — und, seit Lauf 5, am
**Kontrast des Balls**.

> **Warum Lauf 5 den Maßstab nicht entscheiden konnte.** Der Ball lag auf
> hellem Holz, von hinten beleuchtet, und war in cam2 **1,3 Graustufen**
> heller als der Tisch daneben, bei 2,2 Graustufen Bildrauschen. Sein Umriss
> war unsichtbar; Hough-Mitten sprangen um ganze Pixel (derselbe unberührte
> Ball: 684,9 gegen 678,1 mm), und `refine_ball` griff in cam1 die Kante des
> anliegenden Lineals und den Schattenrand. Deshalb ab Lauf 6: dunkles Tuch,
> Licht von der Kameraseite, kein Lineal am Ball — Abschnitt 2 Punkte 5–7.

---

## 1. Was du brauchst

| | |
|---|---|
| Golfball | **einer**, weiß, sauber, ohne Markierungen. Keine zweite Kugel im Raum. |
| Lineal | Zollstock oder Rollmaßband, **mindestens 700 mm**, matt (kein spiegelndes Metall) |
| Zweites Maß | für die seitlichen Positionen, grob reicht |
| **Dunkles, mattes Tuch** | groß genug für den ganzen Messbereich, ca. 70 × 60 cm, **flach und straff** — Falten heben den Ball an und verkippen die Ebene |
| **Lampe** | eine, die hinter oder über dem Gerät steht und auf den Ball scheint |
| **Klebestreifen** | kurze Stücke zum Markieren der Sollmarken auf dem Tuch |
| Zettel + Stift | für die Dinge, die das Werkzeug nicht fragt (siehe Abschnitt 6) |
| SSH-Sitzung | zum Jetson, `ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194` |

Zeitbedarf: etwa 30–40 Minuten für 24 Aufnahmen.

---

## 2. Aufbau — einmal, und dann nichts mehr anfassen

1. **Gerät hinstellen**, auf den Boden, so wie es später stehen soll. Ab jetzt
   nicht mehr bewegen, nicht anstoßen, nicht am Kabel ziehen.

   > Stößt du es mitten in der Serie an, ändern sich Nicken und Rollen und die
   > Ebenenanpassung mischt zwei Geometrien. Das ist von außen nicht sichtbar.
   > Dann: Lauf abbrechen, Verzeichnis löschen, bei Aufnahme 1 neu anfangen.

2. **Lineal legen.** Flach auf den Boden, das **Nullende gegen die Frontfläche**
   des Geräts, und von dort weg zeigend — so gut du es nach Augenmaß rechtwinklig
   zur Frontfläche hinbekommst. Auf ±2° kommt es nicht an, der Lauf misst den
   Winkel selbst nach und korrigiert.

3. **Licht.** Normales Raumlicht. **Kein direkter Sonnenfleck auf dem Boden** im
   Bildbereich — eine helle Spiegelung kann den Ball im Hough-Detektor schlagen.
   Wenn die Sonne wandert: Vorhang zu.

4. **Hintergrund freiräumen — das ist der Punkt, an dem der erste Lauf
   gescheitert ist.**

   > Am 2026-08-10 stand das Gerät auf einem Schreibtisch und schaute quer
   > durchs Zimmer. Im Bild: ein Lautsprecher mit Tief- und Hochtöner, eine
   > Kugel obendrauf, Bilderrahmen, Pflanzen. **In 17 von 24 Aufnahmen hat
   > der Detektor den Lautsprecher vermessen** — erkennbar daran, dass die
   > Erkennung in cam1 immer bei (748, 407) lag, während der Ball bewegt
   > wurde. Ein Ball, der sich nicht bewegt, ist keiner.

   Das Werkzeug erkennt so etwas jetzt und weigert sich, aber **erkennen
   ersetzt nicht wegräumen**: liegen zwei ballförmige Dinge im Messvolumen,
   meldet es „ambiguous" und verwirft die Aufnahme. Neun Aufnahmen des ersten
   Laufs sind genau daran gescheitert.

   Was hilft, in dieser Reihenfolge:

   * Gerät auf eine **leere Wand** ausrichten statt quer durch den Raum;
   * ein **dunkles, mattes Tuch** über alles, was hinter dem Messfeld steht;
   * alles Runde und Helle aus dem Bild: zweite Bälle, Flaschendeckel,
     Lampen, Lautsprecher, glänzende Schraubenköpfe.

   Der Ball soll das einzige helle runde Ding im Bild sein. Alles andere ist
   Arbeit, die das Werkzeug für dich erledigen muss, und manchmal kann es das
   nicht.

5. **Dunkles Tuch unter den ganzen Messbereich** — neu seit Lauf 5, dort ist
   der Maßstab daran gescheitert. Ein weißer Ball auf hellem Holz hat keinen
   Umriss, den eine Kamera finden kann. Das Tuch liegt flach unter **allen**
   Positionen: Tiefenreihe, seitlich und Ziellinie. Ungleiche Unterlage
   verkippt die Ebene.

6. **Licht von der Kameraseite.** Die Lampe steht hinter oder über dem Gerät
   und scheint auf den Ball, nicht von hinten ins Bild. Ein von hinten
   beleuchteter Ball ist dunkler als das, worauf er liegt — genau das Bild aus
   Lauf 5. Im Betrieb übernimmt das später der IR-Blitz. **Ab dem Probeschuss
   das Licht nicht mehr ändern.**

7. **Die Sollmarken aufs Tuch, dann das Lineal weg** — siehe Abschnitt 4. Ein
   Lineal, das am Ball anliegt, ist für den Umrissfit eine fremde Kante direkt
   neben dem Ball; in Lauf 5 hat `refine_ball` sie in cam1 für den Ballrand
   gehalten.

---

## 3. Probeschuss — bevor du irgendetwas auslegst

```bash
cd ~/JetsonLM
python3 -m sp1_vision.cli_triangulate --shots 1 --out /tmp/testshot
```

Ball etwa 50 cm vor das Gerät legen, irgendein Wert bei der Ableseabfrage,
Serie `d`, Enter.

Du willst diese Zeile sehen:

```
  BALL at Z 498 mm  (X -38, Y +84; reproj 0.71 px, size +6%)  skew 3.1 ms
```

**Diese Zeile ist eine echte Prüfung**, anders als die frühere Meldung
`cam1 ball cam2 ball -> keep`, die nur sagte, dass irgendein Kreis gefunden
wurde — und die den ganzen ersten Lauf hindurch fröhlich gemeldet hat,
während beide Kameras einen Lautsprecher vermaßen. Jetzt muss das Ding

* im Messvolumen liegen,
* in beiden Bildern so groß erscheinen, wie es ein 42,67-mm-Ball in genau
  dieser Entfernung täte, und
* aus zwei Strahlen bestehen, die sich wirklich treffen.

**Prüfe die Zahlen gegen die Wirklichkeit**, nicht nur, dass eine Zeile
erscheint: `Z` muss ungefähr deinem Abstand entsprechen, `Y` ist positiv
(der Ball liegt unter der optischen Achse) und `size` sollte unter etwa 10 %
bleiben.

| Was du siehst | Was zu tun ist |
|---|---|
| `BALL at Z …` mit plausiblen Zahlen | weiter zu Abschnitt 4 |
| `no circle at all in cam1 …` | Boden zu hell oder zu dunkel. Erst `--exposure 200` (Einheit 100 µs, also 20 ms), dann `100` oder `400`. |
| `ambiguous: two ball-shaped objects …` | Es liegt noch etwas Ballförmiges im Bild. Zurück zu Abschnitt 2 Punkt 4 und aufräumen. |
| `no ball-consistent pair among N x M circles` | Der Ball ist nicht sauber zu sehen — Belichtung, Kontrast zum Untergrund, oder er liegt außerhalb 250–950 mm. |
| `… solved BEHIND the cameras … check which device is cam1` | Die Kameras sind vertauscht. `camera_paths.py` prüfen, nicht weitermessen. |
| `NO BALL` trotz sauberem Bild | Dünne, **matte dunkle Unterlage** — aber unter **allen** Positionen, auch den seitlichen und den Ziellinien-Positionen. Ungleiche Unterlage verkippt die Ebene. |

**Kontrastprüfung, bevor irgendetwas ausgelegt wird.** Findet der Probeschuss
den Ball, prüft Claude per SSH in beiden Bildern den Helligkeitsabstand
zwischen Ball und Tuch direkt daneben. Ziel: **über 40 Graustufen in beiden
Kameras.** Lauf 5 hatte 12 (cam1) und 1,3 (cam2) — damit ist der Maßstab
nicht zu entscheiden, egal wie sorgfältig abgelesen wird. Liegt der Wert
darunter: Lampe näher oder anders ausrichten, erneut probeschießen.

Die Prüfung meldet auch die **Helligkeit des Tuchs**. Schwarzer Stoff ist im
nahen Infrarot oft hellgrau — das Handtuch aus Lauf 6 lag bei ~115. Das ist
kein Hindernis, solange der Kontrast stimmt, aber es entscheidet die
Auswertung: bei einem Tuch über etwa 90 Graustufen verliert der
Standard-Detektor die fernen Bälle, und ausgewertet wird dann mit
`--refiner contrast` (Abschnitt 7).

Achte auch auf `skew`: bei gutem Licht um 3 ms. Werte um 15–19 ms (Lauf 5)
heißen, die automatische Belichtung ist bei 40 ms angekommen und die Kameras
laufen nur noch mit ~25 statt 120 Bildern pro Sekunde — ein Zeichen für zu
wenig Licht.

Dann `/tmp/testshot` löschen und weiter. Die Belichtungsoption, die
funktioniert hat, merkst du dir für den echten Lauf.

> Die Aufnahme lädt jetzt die Kalibrierung, bevor der erste Schuss fällt —
> ohne Rig lässt sich nicht prüfen, ob ein Kreis ein Ball ist. Eine kaputte
> Kalibrierung stoppt die Sitzung damit vor Aufnahme 1 statt nach Aufnahme 24.

---

## 4. Ablesen — die eine Sache, die den Maßstab entscheidet

**Ab Lauf 6: Marken setzen, Lineal weg, Ball an die Marke.**

> **Ohne Marken beantwortet der Lauf die Maßstabsfrage nicht.** Lauf 6 wurde
> ohne Marken gemessen, der Ball jeweils „5 cm" weitergelegt; die Auswertung
> kam auf 0,961, also 48 statt 50 mm pro Schritt. Das ist ein Schätzfehler,
> kein Geometriefehler, und von außen nicht zu unterscheiden. Der Lauf war
> für Lage und Höhe trotzdem gut — für den Maßstab nicht.

1. Lineal flach aufs Tuch, Nullende an der Frontfläche.
2. An jeder Sollmarke (300, 350, … 640) einen kurzen Klebestreifen **quer**
   aufs Tuch kleben, **etwa 4 cm neben** der Linie, auf der die Bälle liegen
   werden — nicht unter und nicht direkt neben dem Ball. Die Vorderkante des
   Streifens liegt genau auf der Marke.
3. **Lineal wegnehmen.** Es bleibt für die ganze Serie weg.
4. Ball so hinlegen, dass seine **nahe Kante** (die dem Gerät zugewandte
   Seite) auf Höhe der Streifenvorderkante liegt. Senkrecht von oben
   anpeilen; ein Geodreieck quer über Streifen und Ball hilft.

Vier Zentimeter Abstand, weil `refine_ball` Kanten bis etwa einen halben
Ballradius außerhalb des Balls noch für den Rand halten kann — ein Streifen
direkt am Ball wäre wieder das Lineal aus Lauf 5.

**Der Ball liegt auf dem Tuch, niemals auf einem Streifen oder dem Lineal.**

> Läge er erhöht, säße die ganze Tiefenreihe eine Streifen- oder Linealdicke
> höher als die seitlichen Bälle. Die Ebenenanpassung mittelt dann zwischen
> zwei parallelen Ebenen und verkippt — Nicken und Rollen wären falsch, und
> nichts in der Ausgabe würde es sagen.

**Maßgeblich ist die NAHE Kante des Balls.** Immer dieselbe Kante, immer
dieselbe Seite der Streifen, die ganze Serie lang.

Warum die Kante und nicht die Mitte: eine Kante ist scharf und lässt sich von
oben anpeilen, eine Mitte ist eine Schätzung. Der eine Ballradius, den die
Kante daneben liegt, ist eine **Konstante** — und Konstanten landen im
Achsenabschnitt der Anpassung, wo sie nichts kosten. Genauso die Lage der
Linealnull.

Beim Ablesen **senkrecht von oben schauen**, nicht schräg. Schräg kostet dich
leicht 3 mm, und 3 mm auf einer 340-mm-Spanne sind 0,9 % — das Anderthalbfache
des gesuchten Signals.

**Die Marke ist genauer als eine Ablesung.** Einen Ball an eine Kante zu
legen gelingt besser, als einen Zollstock auf einen halben Millimeter
abzulesen. Also: sorgfältig an die Marke legen und die **runde Zahl
eintippen**. Der Platzierungsfehler landet dann im Residuum statt in der
x-Achse, und der Standardfehler der Anpassung weist ihn aus, statt ihn zu
verstecken.

---

## 5. Die 24 Aufnahmen, einzeln

Aufruf für den ganzen Lauf:

```bash
cd ~/JetsonLM
python3 -m sp1_vision.cli_triangulate --shots 24 --out sp1_vision/triangulation_run
```

Bricht etwas ab: einfach neu aufrufen. Er zählt hinter das Vorhandene weiter
und schreibt `run.json` nach jeder Aufnahme.

**Davor und danach je ein Leerbild** — dieselbe Szene ohne Ball, Wert `0`,
Serie `d`; die Meldung `NO BALL` ist hier richtig. Es ist Rohmaterial, um
einen Detektor, der gegen den leeren Hintergrund vergleicht, später an
echten Bildern zu prüfen, und zeigt nebenbei, ob sich das Licht während des
Laufs verändert hat:

```bash
python3 -m sp1_vision.cli_triangulate --shots 1 --out sp1_vision/triangulation_run_empty
```

### Wie eine einzelne Aufnahme abläuft

**Es ist ein reines Terminalprogramm, keine Oberfläche, und es löst nichts von
selbst aus.** Kein Timer, keine Serie im Hintergrund. Jede der 24 Aufnahmen
löst du selbst aus, und zwar mit einem Enter — dieses eine Enter greift
**beide Kameras zusammen** ab. Du triggerst nicht zwei Kameras einzeln.

So sieht eine Aufnahme aus:

```
--- shot 3 ---
  reading on the rule at the ball's NEAR edge (the side
  facing the unit), mm: 400            <- du tippst, Enter
  series - [d]epth line / [s]pread / [t]arget line: d   <- du tippst, Enter
  place the ball, stand clear, press Enter:              <- nur Enter
  BALL at Z 380 mm  (X -37, Y +85; reproj 1.62 px, size +4%)  skew 3.1 ms
```

**Lies die Rückmeldung, sie kostet zwei Sekunden.** Sie ist dieselbe Prüfung,
die die Auswertung später anlegt — was hier durchfällt, fällt dort auch durch,
nur stehst du jetzt noch daneben. `Z` muss zur Sollmarke passen, `Y` positiv
sein, `size` klein. Steht dort stattdessen `NO BALL - …`, folgt eine Zeile
mit dem Grund; die Tabelle in Abschnitt 3 sagt, was zu tun ist.

Die praktische Reihenfolge am Boden ist deshalb:

1. Ball an die Marke legen
2. zur Tastatur, Markenwert tippen, Serienbuchstabe tippen
3. **prüfen, dass du nicht im Bildfeld stehst**, dann Enter
4. die Rückmeldezeile lesen

Der dritte Prompt heißt zwar „place the ball" — zu dem Zeitpunkt liegt er
längst. Was er wirklich meint: **jetzt ist niemand mehr im Bild und nichts
bewegt sich.** Das Bild entsteht erst NACH diesem Enter (seit `35ca2db`;
davor zeigte es die vorige Position).

> **Stell Laptop oder Tastatur seitlich oder hinter das Gerät**, außerhalb des
> Blickfelds der Kameras. Sonst stehst du bei jedem Enter im Bild und musst für
> jede der 24 Aufnahmen einmal hin und her laufen.

Steht dort `MOVE THE BALL AND RETAKE`, ist die Aufnahme trotzdem gespeichert
und wird später verworfen — leg den Ball ein paar Zentimeter anders hin und
nimm die Position mit demselben Ablesewert noch einmal auf. Das kostet nur
eine Aufnahmenummer. Häufen sich die Fehlschläge, liegt es nicht am Ball:
dann zurück zu Abschnitt 2 Punkt 4.

### 5.1 Tiefenreihe, erster Durchgang — Aufnahmen 1 bis 8

Marken kleben, Lineal ist weg. Ball mit der nahen Kante an die Marke,
Markenwert eintippen, Serie `d`.

| # | Marke | Serie | Anmerkung |
|---|---|---|---|
| 1 | 300 mm | `d` | nächste Position |
| 2 | 350 mm | `d` | |
| 3 | 400 mm | `d` | |
| 4 | 450 mm | `d` | |
| 5 | 500 mm | `d` | |
| 6 | 550 mm | `d` | |
| 7 | 600 mm | `d` | |
| 8 | 640 mm | `d` | fernste Position |

Die Sollmarken sind so gewählt, dass die tatsächliche Tiefe zur Kamera etwa
340–700 mm wird — die Kamera sitzt einige Zentimeter hinter der Frontfläche.

### 5.2 Tiefenreihe, zweiter Durchgang — Aufnahmen 9 bis 16

**Dieselben acht Marken noch einmal, Ball jedes Mal neu hingelegt.** Den Ball
zwischendurch wirklich wegnehmen und neu an die Marke legen — genau diese
Streuung ist die Information.

| # | Sollmarke | Serie |
|---|---|---|
| 9 | 300 mm | `d` |
| 10 | 350 mm | `d` |
| 11 | 400 mm | `d` |
| 12 | 450 mm | `d` |
| 13 | 500 mm | `d` |
| 14 | 550 mm | `d` |
| 15 | 600 mm | `d` |
| 16 | 640 mm | `d` |

> Zwei Durchgänge über acht verschiedene Positionen statt drei Wiederholungen
> über sechs: jede neue Distanz bringt auch eine neue Subpixel-Phase mit. Genau
> gegen diese Systematik sind bloße Wiederholungen machtlos.

### 5.3 Ruhemessung ganz hinten — Aufnahmen 17 und 18

Nach Aufnahme 16 bleibt der Ball bei 640 mm **unberührt liegen**. Zweimal noch
auslösen und **exakt denselben Wert wie bei Aufnahme 16** eintippen.

| # | Was | Serie | Ablesewert |
|---|---|---|---|
| 17 | Ball nicht anfassen, nur auslösen | `d` | derselbe wie #16 |
| 18 | Ball nicht anfassen, nur auslösen | `d` | derselbe wie #16 |

Das sind die einzigen drei Aufnahmen mit identischem Ablesewert, und sie geben
die reine Wiederholbarkeit von Sensor und Detektor. Am fernen Ende, weil dort
die Tiefenauflösung am schlechtesten ist — 6,9 mm pro Pixel Disparitätsfehler.
Die Auswertung druckt daraus die Zeile `repeat spread`.

(Das Lineal ist schon seit dem Markenkleben weg.)

### 5.4 Seitliche Positionen — Aufnahmen 19 bis 22

Diese Serie tut nichts für den Maßstab und alles für die Bodenebene: ohne
seitliche Streuung über die Bildbreite ist die Ebene unbestimmt, und mit ihr
sind Nicken, Rollen **und** Gieren verloren. Auf Genauigkeit kommt es hier
nicht an — auf Streuung.

Alle vier auf den Boden, geschätzte Werte reichen, Serie `s`:

| # | ungefähr geradeaus | seitlich | Serie | Ablesewert |
|---|---|---|---|---|
| 19 | 440 mm | **190 mm links** | `s` | `440` genügt |
| 20 | 440 mm | **190 mm rechts** | `s` | `440` genügt |
| 21 | 590 mm | **~230 mm links** | `s` | `590` genügt |
| 22 | 590 mm | **~230 mm rechts** | `s` | `590` genügt |

230 statt der Obergrenze 254 mm: dort ist der Ball schon am Rand, und ein
Gegenstand, der den Platz begrenzt, liegt direkt daneben. Links und rechts
möglichst gleich weit; `conditioning` in der Auswertung sagt, ob es reicht
(Lauf 5: 0,513 bei 213 mm rechts).

Links und rechts von dir aus gesehen, wenn du hinter dem Gerät stehst und über
es hinweg nach vorn schaust.

> Warum nicht weiter seitlich: die Grenze ist 0,43 mal der Tiefe, weil die
> Verzeichnung darüber hinaus nicht kalibriert ist. Bei 440 mm sind das 189 mm,
> bei 590 mm sind es 254 mm — die Werte oben liegen genau darauf. Und **nicht
> gleichzeitig nah und weit seitlich**: eine unkalibrierte Ecke liest sich wie
> eine echte Verschiebung.

Meldet eine dieser Aufnahmen `cam2 --`, ist der Ball für die zweite Kamera aus
dem Bild. Dann 30–40 mm nach innen und noch einmal.

### 5.5 Ziellinie — Aufnahmen 23 und 24

Die Bodenebene kann kein Gieren liefern; sie ist um ihre eigene Normale
drehsymmetrisch. Dieses Paar ist das einzige, was es kann — und es entscheidet
die Vorzeichenfrage, die seit dem Review offen ist.

| # | geradeaus | seitlich | Serie | Ablesewert |
|---|---|---|---|---|
| 23 | 340 mm | **0 mm**, mittig vor dem Gerät | `t` | `340` genügt |
| 24 | 620 mm | **100 mm nach RECHTS** | `t` | `620` genügt |

Rechts, wenn du **hinter dem Gerät** stehst und nach vorn schaust. Miss die
100 mm einigermaßen ordentlich und **schreib die Richtung auf den Zettel.**

Erwartet wird `yaw ≈ +19,7°` (das ist arctan(100/280)), plus die Schräglage
des Lineals. **Das Vorzeichen ist seit 2026-09-23 beantwortet:** Lauf 5 legte
den fernen Ball nach rechts und erhielt +24,5° — positiv heißt Ziellinie
rechts, die Konvention ist nicht invertiert. (Der Betrag lag höher, weil der
Ball 112 statt 100 mm neben der Tiefenlinie lag.) Die Aufnahmen bleiben im
Lauf, weil Gieren die heutige Aufstellung beschreibt und jedes Mal neu ist.

> Der Versatz ist bewusst groß. Bei 10 mm misst du Rauschen statt Richtung.

---

## 6. Auf den Zettel, weil das Werkzeug nicht danach fragt

* Datum, Uhrzeit
* **Nach welcher Seite** der ferne Ziellinien-Ball versetzt war und um wie viel
* Bodenbelag, Farbe; ob eine Unterlage benutzt wurde und welche
* Raumlicht, Tageszeit, ob die Sonne hereinschien
* Ob `--exposure` benutzt wurde und mit welchem Wert
* Jede Aufnahme, bei der etwas schiefging, mit Nummer
* Ob das Gerät zwischendurch angestoßen wurde — falls ja: Lauf ist ungültig

---

## 7. Auswerten

```bash
cd ~/JetsonLM
python3 -m sp1_vision.cli_triangulate --analyse sp1_vision/triangulation_run
```

War das Tuch bei der Kontrastprüfung hell (über etwa 90 Graustufen), dazu
`--refiner contrast`. Das vermisst **jede** Aufnahme des Laufs mit der
kontrastbasierten Umrissverfeinerung; der Kopf der Ausgabe nennt, welche lief.
Nie zwei Auswertungen mit verschiedenen Refinern Zeile für Zeile mischen —
jede Methode hat ihren eigenen kleinen Versatz, und wechselt er mit der
Entfernung, ist das ein Maßstabsfehler (Lauf 6: 0,961 gegen 0,931).

Bevor du irgendeiner Zahl glaubst, diese vier Zeilen prüfen:

| Zeile | Was gut ist | Was es bedeutet, wenn nicht |
|---|---|---|
| Spalte `reproj` je Zeile | unter 2,0 px | Zeile wird verworfen; steht der Grund daneben |
| `conditioning` | über 0,15 | die seitlichen Positionen lagen zu eng — nachlegen und neu auswerten |
| `plane rms` | wenige Millimeter | Bälle lagen nicht alle auf derselben Fläche |
| `depth line obliquity` | unter 3° | Lineal stand schief; die korrigierte Zeile benutzen |

Und dann die eigentlichen Ergebnisse:

* `pitch`, `roll` — Lage des Geräts gegen den Boden. Sollte in derselben
  Größenordnung liegen wie die Kalibrierwerte, muss es aber nicht: die
  Kalibrierung misst Kamera gegen Kamera, dieser Lauf misst das **Gerät gegen
  die Welt**. Das ist eine andere Größe, und noch nichts hat sie je gemessen.
* `camera 1 sits ... mm above the floor` — die Montagehöhe, gegen die 115 mm
  aus der Spezifikation.
* `yaw` — Betrag ≈ 19,7°, Vorzeichen ist die Antwort.
* `scale against tape: X.XXXX +- Y.YYYY` — **die Unsicherheit ist die halbe
  Antwort.** Liegt `1 − X` unter `2·Y`, hat der Lauf die Maßstabsfrage nicht
  entschieden, egal wie sauber die Zahl aussieht.
* `repeat spread` — untere Schranke des Fehlers, **nie der Fehler selbst**.
  Ein Detektionsversatz, der mit der Tiefe wächst, ist ein Maßstabsfehler unter
  anderem Namen, und keine Wiederholung kann ihn sehen.

Die gesamte Ausgabe kopieren und schicken — daraus entstehen der
Teilmengen-Gegencheck (nahe gegen ferne Hälfte), das `README.md` dieses
Verzeichnisses, die Konfigurationswerte und die CLAUDE.md-Korrekturen.

---

## 8. Was dieser Lauf ausdrücklich NICHT tut

* Er schreibt **nichts** in `golf_sim_config.json` oder
  `stereo_extrinsics.json`. Das Werkzeug druckt Zahlen; eintragen tut sie ein
  Mensch, nach Durchsicht.
* Er wiederholt **keine Kalibrierung**. Intrinsics und Extrinsics vom
  2026-08-09 bleiben, wie sie sind.
* `kCameraNAngles` wird aus diesem Lauf **nicht** befüllt. Nicken und Rollen
  sind durch Mount und Boden festgenagelt, Gieren aber durch die Stelle, an der
  das Gerät heute stand — und es steht frei, ohne Anschlag. Solange das so ist,
  beschreibt Gieren die Aufstellung und nicht das Gerät. Die Konstante könnte
  unsere drei Winkel ohnehin nicht tragen; Rollen fällt dort heraus.
