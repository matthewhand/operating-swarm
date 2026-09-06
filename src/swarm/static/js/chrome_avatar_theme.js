/**
 * Settings avatar-theme picker. Same localStorage key as the SPA
 * (`swarm_avatar_theme`) so the choice survives Settings ↔ Chat hops.
 */
(function chromeAvatarTheme() {
  var KEY = "swarm_avatar_theme";
  var EVENT = "swarm:set-avatar-theme";

  function readTheme() {
    try {
      var stored = localStorage.getItem(KEY);
      // robot3d is the REQ-194 3D robot theme (ADR-008), active since Phase 1.
      if (stored === "robot3d") return "robot3d";
      if (stored === "bland" || stored === "default") return "bland";
      if (stored === "bee") return "bee";
      if (stored === "blobs") return "blobs";
    } catch (err) {
      /* storage unavailable */
    }
    return "blobs";
  }

  function writeTheme(theme) {
    var next = "blobs";
    if (theme === "robot3d") next = "robot3d";
    else if (theme === "bland" || theme === "default") next = "bland";
    else if (theme === "bee") next = "bee";
    try {
      if (next === "blobs") {
        localStorage.removeItem(KEY);
      } else {
        localStorage.setItem(KEY, next);
      }
    } catch (err) {
      /* persistence is best-effort */
    }
    try {
      window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
    } catch (err) {
      /* CustomEvent unavailable */
    }
    return next;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("os-avatar-theme");
    if (!select) return;
    select.value = readTheme();
    select.addEventListener("change", function () {
      writeTheme(select.value);
    });
  });
})();
