# Open Swarm — Bee Avatar Suite

Comprehensive suite of 12 vector SVG default avatar icons for Open Swarm agents and user profiles.

## Summary

- **Total Icons:** 12
- **Full Profile Bees:** 6
- **Close-up Bee Faces:** 6
- **Format:** Pure SVG (64x64 viewBox, scalable vector, zero runtime dependencies)
- **Palette:** Open Swarm dark theme badge background (`#1D2226` / `#17212A`), signature golds (`#EFAB22`, `#EBA222`, `#F4C400`, `#C48A1C`), and translucent flight wings.

---

## 1. Actual Bees — Full Profile (6 Icons)

| Filename | Title | Characteristics |
|---|---|---|
| `bee-profile-worker.svg` | Honeybee Worker Profile | Classic worker honeybee in side profile with golden-amber and charcoal striped abdomen, hairy thorax, dual translucent wings swept back, articulated legs, and sharp stinger. |
| `bee-profile-bumblebee.svg` | Bumblebee Profile | Plump, rounded bumblebee profile with thick golden-black fur bands, short rounded wings, and a prominent bright golden-orange pollen basket (*corbicula*) on the hind leg. |
| `bee-profile-queen.svg` | Queen Honeybee Profile | Slender elongated golden abdomen with royal chitin rings, compact delicate wings, and dignified stance. |
| `bee-profile-hover.svg` | Hovering Flight Profile | Dynamic flight posture angled upward at 30°, elevated dual wings with motion venation, legs swept back, and alert antennae. |
| `bee-profile-carpenter.svg` | Carpenter Bee Profile | Dark obsidian-indigo iridescent chitin sheen, dense golden furry thorax, stout legs, strong mandibles, and smoky translucent wings. |
| `bee-profile-dorsal.svg` | Dorsal Specimen Profile | Symmetrical top-down anatomical specimen profile with outspread veined wings and abdominal chevron striping. |

---

## 2. Close-up of Bee Faces (6 Icons)

| Filename | Title | Characteristics |
|---|---|---|
| `bee-face-macro-front.svg` | Macro Compound Eyes Face | Ultra close-up macro portrait featuring massive curved lateral compound eyes with hexagonal facet textures, 3 simple ocelli eyes on the crown, golden clypeus, and antennae. |
| `bee-face-bumble-fluff.svg` | Fluffy Bumblebee Face | Friendly plush bumblebee portrait with dense yellow facial fur halo, large dark velvety compound eyes with white catchlights, and outward-curved antennae. |
| `bee-face-three-quarter.svg` | 3/4 Inquisitive Face | Dynamic 3/4 angle portrait highlighting compound eye curvature, sculpted facial ridge, and a curious antenna gesture. |
| `bee-face-cyber-swarm.svg` | Cyber Swarm Tech Face | High-tech robotic bee face with faceted hexagonal amber visor optics, titanium armor carapace seams, telemetry circuitry, and sensor probes. |
| `bee-face-queen-regal.svg` | Queen Bee Regal Face | Symmetrical regal portrait with crowned chitin crest above the ocelli, deep reflective obsidian compound eyes, and polished amber facial plates. |
| `bee-face-expressive-cute.svg` | Expressive Stylized Face | Inquisitive companion portrait with large expressive pupils, bobble antennae, and friendly smile designed for interactive agent avatars. |

---

## Serving & Usage in Open Swarm

### 1. SPA WebUI (Static Public Assets)
The icons are served directly at `/avatars/bee/<filename>` (e.g. `/avatars/bee/bee-profile-worker.svg`).

### 2. Django Backend (Staticfiles)
The icons are served under `{% static 'img/avatars/bee/<filename>' %}` (`/static/img/avatars/bee/<filename>`).

### 3. Agent Blueprints
Assign directly to agent definition JSON / blueprint metadata:
```json
{
  "id": "research-assistant",
  "name": "Research Bee",
  "avatar_path": "/avatars/bee/bee-profile-worker.svg"
}
```
