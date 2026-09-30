/**
 * Django AGENTS sidepane — same hide contract as the SPA AgentSidebar.
 * Persist hidden ids in localStorage.swarm_hidden_agents (no hide-all).
 */
(function agentSidebar() {
  var STORAGE_KEY = "swarm_hidden_agents";
  var PINNED_KEY = "swarm_pinned_agents";
  var MARK_COUNT = 6;

  var DEFAULT_HIDDEN = ["gate", "tool_gate", "skeptic"];

  function hasHiddenStorage() {
    try {
      return localStorage.getItem(STORAGE_KEY) !== null;
    } catch (err) {
      return false;
    }
  }

  function isDefaultHiddenAgent(agent) {
    var id = String((agent && agent.id) || "").toLowerCase();
    var name = String((agent && agent.name) || "").toLowerCase();
    return (
      id === "gate" ||
      id === "tool_gate" ||
      id === "tool-gate" ||
      id === "skeptic" ||
      name === "gate" ||
      name === "safety" ||
      name === "skeptic"
    );
  }

  function loadPinnedIds() {
    try {
      var raw = localStorage.getItem(PINNED_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      var ids = [];
      parsed.forEach(function (item) {
        var id = typeof item === "string" ? item : item && item.id;
        if (typeof id === "string" && id.length && ids.indexOf(id) === -1) ids.push(id);
      });
      return ids;
    } catch (err) {
      return [];
    }
  }

  function loadHidden() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(function (id) {
        return typeof id === "string" && id.length > 0;
      });
    } catch (err) {
      return [];
    }
  }

  function seedHidden(agents) {
    if (hasHiddenStorage()) return loadHidden();
    var fromCatalog = [];
    (agents || []).forEach(function (agent) {
      if (agent && agent.id && isDefaultHiddenAgent(agent) && fromCatalog.indexOf(agent.id) === -1) {
        fromCatalog.push(agent.id);
      }
    });
    return saveHidden(fromCatalog.length ? fromCatalog : DEFAULT_HIDDEN);
  }

  function saveHidden(ids) {
    var unique = [];
    ids.forEach(function (id) {
      if (id && unique.indexOf(id) === -1) unique.push(id);
    });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(unique));
    } catch (err) {
      /* persistence is best-effort */
    }
    return unique;
  }

  function markIndex(id) {
    var hash = 0;
    for (var i = 0; i < id.length; i += 1) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    }
    return String(hash % MARK_COUNT);
  }

  function agentLabel(agent) {
    return agent.name || agent.id;
  }

  function normalizeRole(value) {
    var key = String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
    if (key === "cos" || key === "chief" || key === "chief-of-staff" || key === "chiefofstaff") {
      return "chief_of_staff";
    }
    if (key === "tool_gate" || key === "tool-gate" || key === "toolgate") return "gate";
    if (key === "helper") return "support";
    if (key === "reviewer") return "skeptic";
    if (key === "support" || key === "gate" || key === "skeptic" || key === "chief_of_staff" || key === "suggestions") {
      return key;
    }
    return "default";
  }

  function roleOf(agent) {
    var role = normalizeRole(agent && agent.role);
    if (role !== "default") return role;
    var id = String((agent && agent.id) || "").toLowerCase();
    if (id === "support" || id === "gate" || id === "skeptic" || id === "suggestions") return id;
    if (id === "cos" || id === "chief" || id === "chief_of_staff") return "chief_of_staff";
    return "default";
  }

  function isSupport(agent) {
    return roleOf(agent) === "support";
  }

  function roleRank(agent) {
    var role = roleOf(agent);
    if (role === "support") return 0;
    if (role === "chief_of_staff") return 1;
    if (role === "gate") return 2;
    if (role === "skeptic") return 3;
    return 10;
  }

  function sortRoles(list) {
    return list.slice().sort(function (a, b) {
      return roleRank(a) - roleRank(b);
    });
  }

  function badgeLabel(role) {
    if (role === "chief_of_staff") return "CoS";
    if (role === "support") return "Support";
    if (role === "gate") return "Gate";
    if (role === "skeptic") return "Skeptic";
    if (role === "suggestions") return "Suggest";
    return "";
  }

  function matchesFilter(agent, query) {
    if (!query) return true;
    var hay = (agentLabel(agent) + " " + (agent.id || "") + " " + (agent.description || "") + " " + (agent.kind || "") + " " + (agent.remote || "")).toLowerCase();
    return hay.indexOf(query) !== -1;
  }

  function init() {
    var listEl = document.getElementById("os-agent-list");
    var hiddenListEl = document.getElementById("os-agent-hidden-list");
    var hiddenWrap = document.getElementById("os-agent-hidden-wrap");
    var hiddenToggle = document.getElementById("os-agent-hidden-toggle");
    var hiddenCount = document.getElementById("os-agent-hidden-count");
    var statusEl = document.getElementById("os-agent-status");
    var filterEl = document.getElementById("os-agent-filter");
    var menuEl = document.getElementById("os-agent-menu");
    var sidebar = document.getElementById("os-agent-sidebar");
    if (!listEl || !hiddenListEl || !statusEl || !menuEl || !sidebar) return;

    var agents = [];
    var teams = [];
    var hiddenIds = hasHiddenStorage() ? loadHidden() : [];
    var hiddenOpen = false;
    var filter = "";

    var DEMO_TEAM = {
      id: "demo-team",
      name: "Demo Team",
      description: "Example multi-agent roster",
      members: [
        { id: "codey", name: "Codey", kind: "agent", role: "coder" },
        { id: "stewie", name: "Stewie", kind: "agent", role: "ops" },
      ],
    };

    function teamHideId(id) {
      return "team:" + id;
    }

    function parseRosters(payload) {
      var list = [];
      if (Array.isArray(payload)) list = payload;
      else if (payload && Array.isArray(payload.data)) list = payload.data;
      else if (payload && Array.isArray(payload.teams)) list = payload.teams;
      return list.filter(function (row) {
        return row && row.object !== "blueprint" && (row.object === "team_roster" || Array.isArray(row.members));
      });
    }

    function loadTeams(done) {
      var urls = ["/team_rosters.json", "/v1/team-rosters/"];
      function tryNext(i) {
        if (i >= urls.length) {
          teams = [DEMO_TEAM];
          done();
          return;
        }
        fetch(urls[i])
          .then(function (res) {
            if (!res.ok) throw new Error("status " + res.status);
            return res.json();
          })
          .then(function (payload) {
            var parsed = parseRosters(payload);
            if (parsed.length) {
              teams = parsed;
              done();
              return;
            }
            tryNext(i + 1);
          })
          .catch(function () {
            tryNext(i + 1);
          });
      }
      tryNext(0);
    }

    function closeMenu() {
      menuEl.hidden = true;
      menuEl.replaceChildren();
      if (menuEl.parentElement && menuEl.parentElement !== document.body) {
        document.body.appendChild(menuEl);
      }
    }

    function openDrawer() {
      sidebar.classList.add("is-open");
      var backdrop = document.getElementById("os-sidebar-backdrop");
      if (backdrop) backdrop.hidden = false;
    }

    function closeDrawer() {
      sidebar.classList.remove("is-open");
      var backdrop = document.getElementById("os-sidebar-backdrop");
      if (backdrop) backdrop.hidden = true;
    }

    function agentHref(agent) {
      if (agent.kind === "herdr") {
        return "/teams/#herdr-members";
      }
      return "/chat?blueprint=" + encodeURIComponent(agent.id);
    }

    function makeLink(agent, hidden) {
      var link = document.createElement("a");
      var role = roleOf(agent);
      link.href = agentHref(agent);
      link.className = "os-agent-item" + (role !== "default" ? " os-agent-item--" + role : "");
      var name = agentLabel(agent);
      link.setAttribute("aria-label", name);
      if (role !== "default") {
        link.setAttribute("data-role", role);
      }

      var dot = document.createElement("span");
      dot.className = "os-agent-dot";
      dot.setAttribute("data-mark", markIndex(agent.id));
      dot.setAttribute("aria-hidden", "true");

      var text = document.createElement("span");
      text.className = "os-agent-item__text";
      var titleRow = document.createElement("span");
      titleRow.className = "os-agent-item__name-row";
      var title = document.createElement("span");
      title.className = "os-agent-item__name";
      title.textContent = name;
      titleRow.appendChild(title);
      var chip = badgeLabel(role);
      if (chip) {
        var badge = document.createElement("span");
        badge.className = "os-agent-role-badge";
        badge.setAttribute("data-role", role);
        badge.textContent = chip;
        titleRow.appendChild(badge);
      }
      text.appendChild(titleRow);
      if (agent.kind === "herdr") {
        var herdrBadge = document.createElement("span");
        herdrBadge.className = "os-agent-item__desc";
        herdrBadge.textContent = agent.remote
          ? "Herdr · " + agent.remote
          : "Herdr · localhost";
        text.appendChild(herdrBadge);
      } else if (agent.description) {
        var desc = document.createElement("span");
        desc.className = "os-agent-item__desc";
        desc.textContent = agent.description;
        text.appendChild(desc);
      }

      link.appendChild(dot);
      link.appendChild(text);
      link.addEventListener("contextmenu", function (event) {
        if (isSupport(agent)) return;
        event.preventDefault();
        openMenu(event, agent.id, hidden);
      });
      return link;
    }

    function makeTeamLink(team, hidden, nested) {
      var link = document.createElement("a");
      link.href = "/chat?team=" + encodeURIComponent(team.id);
      link.className = "os-agent-item os-team-item" + (nested ? " os-agent-item--nested" : "");
      link.setAttribute("data-kind", "team");
      var name = team.name || team.id;
      link.setAttribute("aria-label", name + " (team)");

      var mark = document.createElement("span");
      mark.className = "os-team-mark";
      mark.setAttribute("aria-hidden", "true");
      var icon = document.createElement("i");
      icon.className = "fas fa-users";
      mark.appendChild(icon);

      var text = document.createElement("span");
      text.className = "os-agent-item__text";
      var titleRow = document.createElement("span");
      titleRow.className = "os-team-item__title";
      var title = document.createElement("span");
      title.className = "os-agent-item__name";
      title.textContent = name;
      var badge = document.createElement("span");
      badge.className = "os-team-badge os-agent-role-badge";
      badge.setAttribute("data-kind", "team");
      badge.textContent = "Team";
      titleRow.appendChild(title);
      titleRow.appendChild(badge);
      text.appendChild(titleRow);
      if (team.description) {
        var desc = document.createElement("span");
        desc.className = "os-agent-item__desc";
        desc.textContent = team.description;
        text.appendChild(desc);
      }

      link.appendChild(mark);
      link.appendChild(text);
      link.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        openMenu(event, teamHideId(team.id), hidden);
      });
      return link;
    }

    function openMenu(event, hideId, hidden) {
      menuEl.replaceChildren();
      var item = document.createElement("button");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      item.className = "os-agent-menu__item";
      item.textContent = hidden ? "Unhide" : "Hide from sidebar";
      item.addEventListener("click", function () {
        if (hidden) {
          hiddenIds = saveHidden(hiddenIds.filter(function (id) { return id !== hideId; }));
        } else {
          hiddenIds = saveHidden(hiddenIds.concat([hideId]));
        }
        closeMenu();
        render();
      });
      menuEl.appendChild(item);
      var host = event.currentTarget.parentElement || event.currentTarget;
      host.appendChild(menuEl);
      menuEl.hidden = false;
      menuEl.classList.add("is-anchored");
    }

    function render() {
      var q = filter.trim().toLowerCase();
      var visibleTeams = teams.filter(function (team) {
        return hiddenIds.indexOf(teamHideId(team.id)) === -1 && matchesFilter(team, q);
      });
      var hiddenTeams = teams.filter(function (team) {
        return hiddenIds.indexOf(teamHideId(team.id)) !== -1 && matchesFilter(team, q);
      });
      var pinnedIds = loadPinnedIds();
      var visible = sortRoles(agents.filter(function (agent) {
        return hiddenIds.indexOf(agent.id) === -1 && pinnedIds.indexOf(agent.id) === -1 && matchesFilter(agent, q);
      }));
      var hidden = sortRoles(agents.filter(function (agent) {
        return hiddenIds.indexOf(agent.id) !== -1 && matchesFilter(agent, q);
      }));
      var hiddenTotal = hidden.length + hiddenTeams.length;

      listEl.replaceChildren();
      hiddenListEl.replaceChildren();

      if (!agents.length && !teams.length) {
        statusEl.hidden = false;
        return;
      }
      statusEl.hidden = true;
      statusEl.textContent = "";

      if (!visible.length && !visibleTeams.length) {
        var empty = document.createElement("p");
        empty.className = "os-agent-status";
        empty.textContent = "No matching agents.";
        listEl.appendChild(empty);
      } else {
        var nestedIds = {};
        teams.forEach(function (roster) {
          (roster.members || []).forEach(function (member) {
            if (member.kind === "team") nestedIds[member.team_id || member.id] = true;
          });
        });
        visibleTeams.forEach(function (team) {
          if (nestedIds[team.id]) return;
          var tli = document.createElement("li");
          tli.appendChild(makeTeamLink(team, false, false));
          listEl.appendChild(tli);
          var nest = document.createElement("ul");
          nest.className = "os-agent-team-nest";
          var nestedAny = false;
          (team.members || []).forEach(function (member) {
            if (member.kind !== "team") return;
            var childId = member.team_id || member.id;
            if (hiddenIds.indexOf(teamHideId(childId)) !== -1) return;
            var child = null;
            teams.forEach(function (r) { if (r.id === childId) child = r; });
            var nestLi = document.createElement("li");
            nestLi.appendChild(makeTeamLink(child || { id: childId, name: childId }, false, true));
            nest.appendChild(nestLi);
            nestedAny = true;
          });
          if (nestedAny) listEl.appendChild(nest);
        });
        visible.forEach(function (agent) {
          var li = document.createElement("li");
          li.appendChild(makeLink(agent, false));
          listEl.appendChild(li);
        });
      }

      if (hiddenWrap) {
        hiddenWrap.hidden = hiddenTotal === 0;
      }
      if (hiddenCount) hiddenCount.textContent = String(hiddenTotal);
      hiddenListEl.hidden = !hiddenOpen;
      if (hiddenToggle) hiddenToggle.setAttribute("aria-expanded", hiddenOpen ? "true" : "false");

      hiddenTeams.forEach(function (team) {
        var trow = document.createElement("li");
        trow.className = "os-agent-hidden__row";
        trow.appendChild(makeTeamLink(team, true));
        var unhideTeam = document.createElement("button");
        unhideTeam.type = "button";
        unhideTeam.className = "os-agent-unhide";
        unhideTeam.setAttribute("aria-label", "Unhide " + (team.name || team.id));
        unhideTeam.textContent = "Unhide";
        unhideTeam.addEventListener("click", function () {
          hiddenIds = saveHidden(hiddenIds.filter(function (id) { return id !== teamHideId(team.id); }));
          render();
        });
        trow.appendChild(unhideTeam);
        hiddenListEl.appendChild(trow);
      });

      hidden.forEach(function (agent) {
        var li = document.createElement("li");
        li.className = "os-agent-hidden__row";
        li.appendChild(makeLink(agent, true));
        var unhide = document.createElement("button");
        unhide.type = "button";
        unhide.className = "os-agent-unhide";
        unhide.setAttribute("aria-label", "Unhide " + agentLabel(agent));
        unhide.textContent = "Unhide";
        unhide.addEventListener("click", function () {
          hiddenIds = saveHidden(hiddenIds.filter(function (id) { return id !== agent.id; }));
          render();
        });
        li.appendChild(unhide);
        hiddenListEl.appendChild(li);
      });
    }

    if (hiddenToggle) {
      hiddenToggle.addEventListener("click", function () {
        hiddenOpen = !hiddenOpen;
        render();
      });
    }
    if (filterEl) {
      filterEl.addEventListener("input", function () {
        filter = filterEl.value;
        render();
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeMenu();
    });
    document.addEventListener("mousedown", function (event) {
      if (!menuEl.hidden && !menuEl.contains(event.target)) closeMenu();
    });

    var openBtn = document.getElementById("os-sidebar-open");
    var closeBtn = document.getElementById("os-sidebar-close");
    var backdrop = document.getElementById("os-sidebar-backdrop");
    if (openBtn) openBtn.addEventListener("click", openDrawer);
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    if (backdrop) backdrop.addEventListener("click", closeDrawer);

    Promise.all([
      fetch("/v1/blueprints/").then(function (res) {
        if (!res.ok) throw new Error("status " + res.status);
        return res.json();
      }),
      fetch("/v1/herdr-agents/").then(function (res) {
        if (!res.ok) return { data: [] };
        return res.json();
      }).catch(function () {
        return { data: [] };
      }),
    ])
      .then(function (results) {
        var blueprints = Array.isArray(results[0] && results[0].data) ? results[0].data : [];
        var herdr = Array.isArray(results[1] && results[1].data) ? results[1].data : [];
        var herdrAgents = herdr.map(function (row) {
          return {
            id: "herdr:" + (row.name || row.id),
            name: row.name,
            kind: "herdr",
            remote: row.remote || "",
            description: row.remote ? "Herdr · " + row.remote : "Herdr · localhost",
            rail: true,
          };
        });
        var catalogSeats = blueprints.filter(function (row) {
          return row && row.rail === true;
        });
        agents = catalogSeats.concat(herdrAgents);
        hiddenIds = seedHidden(agents);
        if (!agents.length && !teams.length) statusEl.textContent = "No agents yet.";
        loadTeams(render);
      })
      .catch(function () {
        agents = [];
        loadTeams(function () {
          if (!teams.length) {
            statusEl.textContent = "Could not load agents.";
            statusEl.hidden = false;
            return;
          }
          render();
        });
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
