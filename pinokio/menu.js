// Operating Swarm — Pinokio launcher (local sideload only).
// Sideload via git URL. No public Discover listing from this tree.
//
// Loaded via the clone-root pinokio.js re-export. Menu hrefs point at
// pinokio/*.js. Root install.js / start.js / update.js remain thin wrappers
// so older sideload menus that still href those basenames keep working.

const path = require("path")

const INSTALLED_MARK = path.join(".pinokio", "installed")
const REPO_ROOT = path.join(__dirname, "..")

const INSTALL = "pinokio/install.js"
const START = "pinokio/start.js"
const UPDATE = "pinokio/update.js"

function isPromise(value) {
  return !!value && typeof value.then === "function"
}

async function exists(info, kernel, rel) {
  if (info && typeof info.exists === "function") {
    return !!info.exists(rel)
  }
  if (kernel && typeof kernel.exists === "function") {
    // Current Pinokio: info.exists(rel). Older kernels: exists(cwd, rel).
    let result = kernel.exists(rel)
    if (isPromise(result)) result = await result
    if (result) return true
    let resultRoot = kernel.exists(REPO_ROOT, rel)
    if (isPromise(resultRoot)) resultRoot = await resultRoot
    return !!resultRoot
  }
  return false
}

function running(info, kernel, rel) {
  if (info && typeof info.running === "function") {
    return !!info.running(rel)
  }
  if (kernel && typeof kernel.running === "function") {
    if (kernel.running(rel)) return true
    if (kernel.running(REPO_ROOT, rel)) return true
  }
  return false
}

function isRunning(info, kernel, rels) {
  return rels.some((rel) => running(info, kernel, rel))
}

async function menu(kernel, info) {
  const installed = await exists(info, kernel, INSTALLED_MARK)
  const installing = isRunning(info, kernel, [INSTALL, "install.js"])
  const starting = isRunning(info, kernel, [START, "start.js"])
  const updating = isRunning(info, kernel, [UPDATE, "update.js"])

  if (installing) {
    return [{
      default: true,
      icon: "fa-solid fa-plug",
      text: "Installing",
      href: INSTALL,
    }]
  }

  if (updating) {
    return [{
      default: true,
      icon: "fa-solid fa-clock",
      text: "Updating",
      href: UPDATE,
    }]
  }

  if (starting) {
    // REQ-47: running → Open App (href start script, default)
    return [{
      default: true,
      icon: "fa-solid fa-rocket",
      text: "Open App",
      href: START,
    }]
  }

  if (installed) {
    // installed + stopped → Start + Update
    return [{
      default: true,
      icon: "fa-solid fa-power-off",
      text: "Start",
      href: START,
    }, {
      icon: "fa-solid fa-rotate",
      text: "Update",
      href: UPDATE,
    }]
  }

  // not installed → Install
  return [{
    default: true,
    icon: "fa-solid fa-plug",
    text: "Install",
    href: INSTALL,
  }]
}

module.exports = {
  version: "2.0",
  title: "Operating Swarm",
  description: "Operating Swarm — multi-agent AI workflows as a local CLI, OpenAI-compatible API, and web UI.",
  icon: "assets/brand/favicon-minimal.svg",
  menu,
}
