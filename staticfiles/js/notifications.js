/* Aurora Store — header notifications: mark-as-read + new-notification chime */
(function () {
  "use strict";

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));
  const A = window.Aurora || {};
  const post = A.post || function () { return Promise.reject(new Error("no post helper")); };
  const toast = (title, message, kind) => {
    if (typeof window.showToast === "function") window.showToast(title, message, kind);
  };

  // ------------------------------------------------------------------
  // Badge
  // ------------------------------------------------------------------
  function setUnreadBadge(count) {
    const bell = $(".au-action-notification");
    if (!bell) return;
    let badge = $("[data-unread-badge]", bell) || $(".au-badge-count", bell);
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "au-badge-count";
        badge.setAttribute("data-unread-badge", "");
        bell.appendChild(badge);
      }
      badge.textContent = count;
      bell.classList.add("has-unread");
      const icon = $("i", bell);
      if (icon) icon.className = "bi bi-bell-fill";
    } else {
      if (badge) badge.remove();
      bell.classList.remove("has-unread");
      const icon = $("i", bell);
      if (icon) icon.className = "bi bi-bell";
    }
  }

  // ------------------------------------------------------------------
  // Sound (Web Audio chime — no asset file needed)
  //
  // Browsers start AudioContext suspended and only allow it to run after a
  // user gesture; they may re-suspend it later (e.g. background tab). The
  // chime is therefore queued and flushed from several paths: async
  // resume(), the context's `statechange` event, a timeout, the next user
  // gesture, and tab-visibility return.
  // ------------------------------------------------------------------
  let audioCtx = null;
  let pendingChime = false;

  function ensureAudio() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      if (!audioCtx) audioCtx = new Ctx();
      return audioCtx;
    } catch (e) {
      return null;
    }
  }

  function synthChime(ctx) {
    try {
      const now = ctx.currentTime;
      // Two-note ascending chime.
      [[880, 0], [1318.5, 0.14]].forEach(function (pair) {
        const freq = pair[0];
        const at = now + pair[1];
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.32, at + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.5);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(at);
        osc.stop(at + 0.55);
      });
    } catch (e) { /* audio unavailable — badge/toast still fire */ }
  }

  function flushIfRunning(ctx) {
    if (pendingChime && ctx && ctx.state === "running") {
      pendingChime = false;
      synthChime(ctx);
    }
  }

  function tryResume(ctx) {
    if (!ctx) return;
    if (ctx.state === "running") {
      flushIfRunning(ctx);
      return;
    }
    if (!ctx.__auHooked) {
      ctx.__auHooked = true;
      try {
        ctx.addEventListener("statechange", function () { flushIfRunning(ctx); });
      } catch (e) { /* older browsers: no statechange listener */ }
    }
    try {
      const p = ctx.resume();
      if (p && typeof p.then === "function") {
        p.then(function () { flushIfRunning(ctx); }).catch(function () {});
      }
    } catch (e) { /* resume rejected — next gesture will retry */ }
    setTimeout(function () { flushIfRunning(ctx); }, 400);
  }

  function playChime() {
    const ctx = ensureAudio();
    if (!ctx) return;
    if (ctx.state === "running") {
      pendingChime = false;
      synthChime(ctx);
      return;
    }
    pendingChime = true; // queued until a gesture/visibility event resumes audio
    tryResume(ctx);
  }

  // Keep these listeners for the whole session (not {once}) — the context
  // can be suspended again later, and each gesture re-attempts resume+flush.
  ["pointerdown", "keydown", "touchstart"].forEach(function (evt) {
    document.addEventListener(evt, function () {
      const ctx = ensureAudio();
      if (!ctx) return;
      if (ctx.state === "running") flushIfRunning(ctx);
      else tryResume(ctx);
    }, { passive: true });
  });

  // Returning to a hidden tab: resume audio and flush a queued chime.
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) tryResume(audioCtx || ensureAudio());
  });

  // Manual test hook: run AuroraChime() in the devtools console to hear it.
  window.AuroraChime = function () { playChime(); };

  // ------------------------------------------------------------------
  // Mark one as read (check button, or clicking the notification itself)
  // ------------------------------------------------------------------
  function markRead(item) {
    if (!item || item._readBusy || item.classList.contains("is-read")) return Promise.resolve(null);
    item._readBusy = true;
    return post(item.getAttribute("data-notif-read"), {})
      .then(function (data) {
        item._readBusy = false;
        if (data && data.authenticated === false) {
          window.location.href = "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
          return null;
        }
        if (!data || !data.ok) {
          toast("Oops", (data && data.message) || "Could not update notification.", "error");
          return null;
        }
        item.classList.remove("unread");
        item.classList.add("is-read");
        const btn = item.querySelector("[data-notif-read-btn]");
        if (btn) btn.remove();
        if (typeof data.unread === "number") setUnreadBadge(data.unread);
        return data;
      })
      .catch(function () {
        item._readBusy = false;
        toast("Error", "Network error, please retry.", "error");
        return null;
      });
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-notif-read-btn]");
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      markRead(btn.closest("[data-notif-item]"));
      return;
    }
    // Clicking the notification body/link marks it read, then navigates.
    const link = e.target.closest("[data-notif-item] .item-title");
    if (link) {
      const item = link.closest("[data-notif-item]");
      if (item && item.hasAttribute("data-notif-read") && !item.classList.contains("is-read")) {
        e.preventDefault();
        const href = link.getAttribute("href");
        markRead(item).then(function () {
          if (href) window.location.href = href;
        });
      }
      return;
    }
    // Link-less notification: clicking anywhere on the row marks it read.
    const row = e.target.closest("[data-notif-item][data-notif-read]");
    if (row) markRead(row);
  });

  // ------------------------------------------------------------------
  // Mark all as read
  // ------------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-notif-read-all]");
    if (!btn || btn._busy) return;
    e.preventDefault();
    btn._busy = true;
    post(btn.getAttribute("data-notif-read-all"), {})
      .then(function (data) {
        btn._busy = false;
        if (data && data.authenticated === false) {
          window.location.href = "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
          return null;
        }
        if (!data || !data.ok) return;
        $$("[data-notif-item]").forEach(function (item) {
          item.classList.remove("unread");
          item.classList.add("is-read");
          const b = item.querySelector("[data-notif-read-btn]");
          if (b) b.remove();
        });
        setUnreadBadge(0);
        toast("Notifications", "All notifications marked as read.", "success");
      })
      .catch(function () {
        btn._busy = false;
        toast("Error", "Network error, please retry.", "error");
      });
  });

  // ------------------------------------------------------------------
  // Poll for new notifications → chime + badge + refresh list
  // ------------------------------------------------------------------
  const pollLink = $("[data-notif-poll]");
  if (!pollLink) return;

  const pollUrl = pollLink.getAttribute("data-notif-poll");
  const listUrl = pollLink.getAttribute("data-notif-list-url");
  let latestId = 0;
  let seenFirst = false;
  let inflight = false;

  function refreshList() {
    const list = $("[data-notif-list]");
    if (!list || !listUrl) return;
    fetch(listUrl, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { if (html) list.innerHTML = html; })
      .catch(function () {});
  }

  function poll() {
    if (inflight || document.hidden) return;
    inflight = true;
    // Send `since` from the second poll onward (baseline may be id 0,
    // which is falsy — do NOT gate on `latestId` truthiness).
    const url = seenFirst ? pollUrl + "?since=" + latestId : pollUrl;
    fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        inflight = false;
        if (!data || data.authenticated === false) return;
        const fresh = data.new || [];
        latestId = data.latest_id || latestId;
        if (!seenFirst) {
          seenFirst = true;
          setUnreadBadge(data.unread || 0);
          return;
        }
        if (fresh.length) {
          setUnreadBadge(data.unread || 0);
          playChime();
          refreshList();
          toast(
            "New notification",
            fresh[0].title + (fresh.length > 1 ? " (+" + (fresh.length - 1) + " more)" : ""),
            "info"
          );
        } else if (typeof data.unread === "number") {
          setUnreadBadge(data.unread);
        }
      })
      .catch(function () { inflight = false; });
  }

  poll(); // establish baseline (no sound for existing items)
  setInterval(poll, 15000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) poll();
  });
})();
