# Adaptive DCA Strategy

## Ziel

Die **Adaptive DCA Strategy** kombiniert eine hohe Grundinvestitionsquote mit antizyklischen Zusatzkäufen bei stärkeren Rücksetzern.
Der Fokus liegt auf geringer Cash-Drag und einer robusten Balance aus DCA und Timing.

## Funktionsweise

1. **Monatliche Investition (Basis-DCA)**
   - Standard: Der Großteil der monatlichen Sparrate wird direkt investiert (`MONTHLY-DCA`).
   - Optional: Ein kleiner Anteil wird als taktische Reserve gehalten (`adca_reserve_pct`, Default: `10%`).

2. **Dip-Buying über feste Tranchen**
   - Bei definierten Drawdowns werden feste Zusatztranchen ausgelöst (`ADCA_T1` ... `ADCA_T4`).
   - Die Tranche ist nicht proportional zum Cashbestand und schrumpft daher nicht automatisch bei sinkendem Cash.
   - Wenn nicht genug Cash verfügbar ist, wird bis zum verfügbaren Betrag investiert (sofern `min_order_eur` erreicht ist).

3. **Kein VIX-Gating**
   - VIX wird bewusst nicht für die Signalentscheidung verwendet.

4. **Kurzer / optionaler Cooldown**
   - Über `adca_cooldown_days` steuerbar.
   - `0` deaktiviert den Cooldown.

## Unterschiede zu SDA

- SDA priorisiert stärker Cash-Management und VIX-Filterung.
- Adaptive DCA priorisiert hohe Investitionsquote und schnelle antizyklische Reaktion.
- SDA skaliert Dip-Käufe relativ zum Cashbestand.
- Adaptive DCA arbeitet mit festen drawdownabhängigen Tranchen.

## Vorteile

- Hoher Investitionsgrad im Normalmarkt.
- Weniger Cash-Drag.
- Planbare, klare Dip-Mechanik.
- Gute Nutzbarkeit in langen Abwärtsphasen durch kurze/optionale Cooldowns.

## Nachteile

- Geringere Defensivität als SDA.
- Kann in volatilen Seitwärtsmärkten mehr Trades erzeugen.
- Bei sehr niedrigem Cash kann die geplante Tranche nur teilweise umgesetzt werden.
