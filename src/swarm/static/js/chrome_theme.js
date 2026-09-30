/**
 * Shared Light/Dark toggle for Django chrome.
 * Uses the same localStorage key as the SPA (`swarm_theme`), including
 * `system`, so Chat → Settings keeps the same resolved theme.
 * Applies before first paint when possible. The initial apply does not
 * overwrite a stored `system` preference.
 */
(function chromeTheme() {
  var KEY = "swarm_theme";

  function readStored() {
    try {
      var stored = localStorage.getItem(KEY);
      if (stored === "light" || stored === "dark" || stored === "system") return stored;
    } catch (err) {
      /* storage unavailable */
    }
    return "system";
  }

  function systemTheme() {
    try {
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
      }
      if (window.matchMedia) return "light";
    } catch (err) {
      /* matchMedia unavailable */
    }
    return "dark";
  }

  function resolveTheme(stored) {
    if (stored === "light" || stored === "dark") return stored;
    return systemTheme();
  }

  function applyTheme(theme, persist) {
    var root = document.documentElement;
    root.setAttribute("data-bs-theme", theme);
    root.setAttribute("data-os-theme", theme);
    root.setAttribute("data-theme", theme);
    if (persist) {
      try {
        localStorage.setItem(KEY, theme);
      } catch (err) {
        /* persistence is best-effort */
      }
    }
    var btn = document.getElementById("os-theme-toggle");
    if (btn) {
      var toLight = theme === "dark";
      btn.textContent = toLight ? "Light" : "Dark";
      btn.setAttribute(
        "aria-label",
        toLight ? "Switch to light theme" : "Switch to dark theme",
      );
    }
  }

  function watchSystem() {
    try {
      if (!window.matchMedia) return;
      var media = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function (event) {
        if (readStored() !== "system") return;
        var next = event && event.matches ? "dark" : "light";
        applyTheme(next, false);
      };
      if (typeof media.addEventListener === "function") {
        media.addEventListener("change", onChange);
      } else if (typeof media.addListener === "function") {
        media.addListener(onChange);
      }
    } catch (err) {
      /* matchMedia unavailable */
    }
  }

  applyTheme(resolveTheme(readStored()), false);
  watchSystem();

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(resolveTheme(readStored()), false);
    var btn = document.getElementById("os-theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var next = resolveTheme(readStored()) === "dark" ? "light" : "dark";
      applyTheme(next, true);
    });
  });
})();
