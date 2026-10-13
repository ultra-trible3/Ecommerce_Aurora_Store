/* Aurora Store — light/dark theme switch
   The initial theme is applied before first paint by the inline script in
   base.html (no flash). This file keeps the toggle button, the OS
   preference and other open tabs in sync. */
(function () {
  "use strict";

  var KEY = "au-theme";
  var root = document.documentElement;
  var COLOR = { light: "#f5efe1", dark: "#141110" };

  function current() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function readStored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function store(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) { /* private mode */ }
  }

  function syncButtons(theme) {
    var dark = theme === "dark";
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-theme-toggle]"),
      function (btn) {
        var icon = btn.querySelector("[data-theme-icon]");
        if (icon) icon.className = "bi " + (dark ? "bi-sun" : "bi-moon-stars");
        btn.setAttribute("aria-pressed", dark ? "true" : "false");
        var label = dark
          ? btn.getAttribute("data-to-light")
          : btn.getAttribute("data-to-dark");
        if (label) {
          btn.setAttribute("aria-label", label);
          btn.setAttribute("title", label);
        }
      }
    );
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", COLOR[theme]);
  }

  function apply(theme, save) {
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme);
    if (save) store(theme);
    syncButtons(theme);
    // Brief crossfade so the swap feels deliberate, not abrupt.
    root.classList.add("au-theme-anim");
    setTimeout(function () { root.classList.remove("au-theme-anim"); }, 320);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    e.preventDefault();
    apply(current() === "dark" ? "light" : "dark", true);
  });

  // Follow the OS preference only while the user hasn't chosen explicitly.
  if (window.matchMedia) {
    var mq = matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      if (!readStored()) apply(mq.matches ? "dark" : "light", false);
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  // Keep other open tabs in step.
  window.addEventListener("storage", function (e) {
    if (e.key === KEY && (e.newValue === "light" || e.newValue === "dark")) {
      apply(e.newValue, false);
    }
  });

  // The inline script already set the theme; just sync button state.
  syncButtons(current());
})();
