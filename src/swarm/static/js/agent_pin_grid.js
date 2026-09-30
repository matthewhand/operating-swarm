/**
 * Unlabeled chrome pin grid — drop target for AGENTS sidepane rows.
 * Persist pins in localStorage.swarm_pinned_agents (REQ-94: move, not a copy).
 */
(function agentPinGrid() {
  var STORAGE_KEY = "swarm_pinned_agents";
  var MIME = "application/x-swarm-agent";
  var MARK_COUNT = 6;

  function loadPins() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw === null) {
        var seeded = [{ id: "support", name: "Support" }];
        savePins(seeded);
        return seeded;
      }
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      var seen = {};
      var pins = [];
      parsed.forEach(function (item) {
        var pin = normalize(item);
        if (!pin || seen[pin.id]) return;
        seen[pin.id] = true;
        pins.push(pin);
      });
      return pins;
    } catch (err) {
      return [];
    }
  }

  function savePins(pins) {
    var unique = [];
    var seen = {};
    pins.forEach(function (item) {
      var pin = normalize(item);
      if (!pin || seen[pin.id]) return;
      seen[pin.id] = true;
      unique.push(pin);
    });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(unique));
    } catch (err) {
      /* persistence is best-effort */
    }
    return unique;
  }

  function normalize(value) {
    if (typeof value === "string" && value.length) return { id: value, name: value };
    if (!value || typeof value !== "object" || typeof value.id !== "string" || !value.id) {
      return null;
    }
    return { id: value.id, name: value.name || value.id };
  }

  function markIndex(id) {
    var hash = 0;
    for (var i = 0; i < id.length; i += 1) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    }
    return String(hash % MARK_COUNT);
  }

  function parseDrop(dataTransfer) {
    if (window.__osAgentDrag && window.__osAgentDrag.id) {
      return normalize(window.__osAgentDrag);
    }
    if (!dataTransfer) return null;
    try {
      var typed = dataTransfer.getData(MIME);
      if (typed) return normalize(JSON.parse(typed));
    } catch (err) {
      /* fall through */
    }
    try {
      return normalize(dataTransfer.getData("text/plain"));
    } catch (err2) {
      return null;
    }
  }

  function selectedBlueprint() {
    try {
      return new URLSearchParams(window.location.search).get("blueprint") || "";
    } catch (err) {
      return "";
    }
  }

  function render(grid, pins) {
    grid.replaceChildren();
    grid.classList.toggle("is-empty", pins.length === 0);
    var selected = window.location.pathname.indexOf("/chat") === 0 ? selectedBlueprint() : "";
    pins.forEach(function (pin) {
      var tile = document.createElement("div");
      tile.className = "os-agent-tile" + (selected === pin.id ? " is-active" : "");

      var link = document.createElement("a");
      link.className = "os-agent-tile__link";
      link.href = "/chat?blueprint=" + encodeURIComponent(pin.id);
      if (selected === pin.id) link.setAttribute("aria-current", "page");

      var dot = document.createElement("span");
      dot.className = "os-agent-dot os-agent-tile__avatar";
      dot.setAttribute("data-mark", markIndex(pin.id));
      dot.setAttribute("aria-hidden", "true");

      var name = document.createElement("span");
      name.className = "os-agent-tile__name";
      name.textContent = pin.name;

      link.appendChild(dot);
      link.appendChild(name);

      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "os-agent-tile__remove";
      remove.setAttribute("aria-label", "Remove " + pin.name);
      remove.textContent = "×";
      remove.addEventListener("click", function () {
        pins = savePins(pins.filter(function (item) { return item.id !== pin.id; }));
        render(grid, pins);
      });

      tile.appendChild(link);
      tile.appendChild(remove);
      grid.appendChild(tile);
    });
  }

  function init() {
    var grid = document.getElementById("os-agent-pin-grid");
    if (!grid) return;
    var pins = loadPins();

    grid.addEventListener("dragover", function (event) {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      grid.classList.add("is-over");
    });
    grid.addEventListener("dragleave", function (event) {
      if (!grid.contains(event.relatedTarget)) grid.classList.remove("is-over");
    });
    grid.addEventListener("drop", function (event) {
      event.preventDefault();
      grid.classList.remove("is-over");
      var agent = parseDrop(event.dataTransfer);
      window.__osAgentDrag = null;
      if (!agent) return;
      var exists = pins.some(function (item) { return item.id === agent.id; });
      if (!exists) {
        pins = savePins(pins.concat([agent]));
        render(grid, pins);
      }
    });

    render(grid, pins);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
