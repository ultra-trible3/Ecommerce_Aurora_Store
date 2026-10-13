/* Aurora Store — shared cart / wishlist side drawer */
(function () {
  "use strict";

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));
  const A = window.Aurora || {};
  const post = A.post || function () { return Promise.reject(new Error("no post helper")); };
  const toast = (title, message, kind) => {
    if (typeof window.showToast === "function") window.showToast(title, message, kind);
  };

  const META = {
    cart: { title: "Shopping cart", icon: "bi-bag" },
    wishlist: { title: "Saved for later", icon: "bi-heart" },
  };

  const drawer = $("[data-drawer]");
  const overlay = $("[data-drawer-overlay]");
  const body = drawer ? $("[data-drawer-body]", drawer) : null;
  const titleEl = drawer ? $("[data-drawer-title]", drawer) : null;
  const iconEl = drawer ? $("[data-drawer-icon]", drawer) : null;

  let open = false;
  let currentKey = null;
  let currentUrl = null;
  let lastFocus = null;
  let seq = 0;
  let scrollY = 0;
  let overlayTimer = null;

  if (!drawer || !overlay || !body) return;

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function setBadge(key, count) {
    if (typeof count !== "number") return;
    const attr = key === "cart" ? "[data-cart-count]" : "[data-wishlist-count]";
    $$(attr).forEach((el) => {
      el.textContent = count;
      if (count === 0) el.remove();
    });
    const trigger = $$("[data-drawer-open][data-drawer-key='" + key + "']")[0];
    if (count > 0 && trigger && !$(".au-badge-count", trigger)) {
      const span = document.createElement("span");
      span.className = "au-badge-count";
      if (key === "cart") span.setAttribute("data-cart-count", "");
      else span.setAttribute("data-wishlist-count", "");
      span.textContent = count;
      trigger.appendChild(span);
    }
  }

  function refresh() {
    if (!currentUrl) return;
    const mySeq = ++seq;
    fetch(currentUrl, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then((html) => {
        if (mySeq !== seq || !open) return;
        body.innerHTML = html;
      })
      .catch(() => {
        if (mySeq !== seq || !open) return;
        body.innerHTML =
          '<div class="au-panel-empty"><i class="bi bi-exclamation-circle"></i>' +
          "<b>Could not load right now.</b>" +
          '<button class="btn btn-sm btn-outline-secondary mt-2" type="button" data-drawer-retry>Retry</button></div>';
      });
  }

  function triggerEls(key) {
    return $$("[data-drawer-open][data-drawer-key='" + key + "']");
  }

  function setExpanded(key, value) {
    triggerEls(key).forEach((el) => el.setAttribute("aria-expanded", value ? "true" : "false"));
  }

  function openDrawer(trigger) {
    const key = trigger.getAttribute("data-drawer-key");
    const url = trigger.getAttribute("data-drawer-url");
    if (!key || !url) return;

    // Toggle: clicking the same icon again closes the drawer.
    if (open && currentKey === key) {
      closeDrawer();
      return;
    }

    // Close an open Bootstrap offcanvas (mobile nav) before sliding in.
    const offcanvasHost = trigger.closest(".offcanvas");
    if (offcanvasHost && window.bootstrap && bootstrap.Offcanvas) {
      const inst = bootstrap.Offcanvas.getInstance(offcanvasHost);
      if (inst) inst.hide();
    }

    if (!open) {
      lastFocus = document.activeElement;
      scrollY = window.scrollY;
      document.body.classList.add("au-drawer-lock");
      document.body.style.top = -scrollY + "px";
      if (overlayTimer) {
        clearTimeout(overlayTimer);
        overlayTimer = null;
      }
      overlay.hidden = false;
      // Force reflow so the entry transition runs.
      void overlay.offsetWidth;
      overlay.classList.add("is-open");
      drawer.classList.add("is-open");
      drawer.setAttribute("aria-hidden", "false");
      open = true;
      const closeBtn = $("[data-drawer-close]", drawer);
      if (closeBtn) closeBtn.focus();
    }

    currentKey = key;
    currentUrl = url;
    setExpanded(key, true);

    const meta = META[key] || {};
    if (titleEl) titleEl.textContent = meta.title || "";
    if (iconEl) iconEl.className = "bi " + (meta.icon || "bi-bag") + " me-1";

    body.innerHTML =
      '<div class="au-panel-loading"><span class="spinner-border spinner-border-sm"></span></div>';
    refresh();
  }

  function closeDrawer() {
    if (!open) return;
    open = false;
    seq++;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    overlay.classList.remove("is-open");
    if (overlayTimer) clearTimeout(overlayTimer);
    overlayTimer = setTimeout(() => {
      if (!open) overlay.hidden = true;
      overlayTimer = null;
    }, 240);
    document.body.classList.remove("au-drawer-lock");
    document.body.style.top = "";
    window.scrollTo(0, scrollY);
    if (currentKey) setExpanded(currentKey, false);
    currentKey = null;
    currentUrl = null;
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
    lastFocus = null;
  }

  // ------------------------------------------------------------------
  // Open / close wiring
  // ------------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const retry = e.target.closest("[data-drawer-retry]");
    if (retry) {
      refresh();
      return;
    }

    if (e.target.closest("[data-drawer-close]") || e.target.closest("[data-drawer-overlay]")) {
      closeDrawer();
      return;
    }

    const trigger = e.target.closest("[data-drawer-open]");
    if (trigger) {
      e.preventDefault();
      openDrawer(trigger);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (!open) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeDrawer();
      return;
    }
    if (e.key === "Tab") {
      const focusables = $$(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        drawer
      ).filter((el) => el.offsetParent !== null);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      } else if (!drawer.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  // ------------------------------------------------------------------
  // Drawer actions (qty steppers, remove, move to cart)
  // ------------------------------------------------------------------
  function handleForm(form) {
    if (form._busy) return;
    form._busy = true;
    const btn = form.querySelector('[type="submit"]:not([data-qty-step])');
    const prevDisabled = btn ? btn.disabled : false;
    if (btn) btn.disabled = true;

    post(form.action, new FormData(form))
      .then((data) => {
        form._busy = false;
        if (btn) btn.disabled = prevDisabled;
        if (data && data.authenticated === false) {
          window.location.href =
            "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
          return;
        }
        if (!data || data.ok === false) {
          toast("Oops", (data && data.message) || "Request failed.", "error");
        }
        const isWish = form.action.indexOf("/wishlist/") !== -1;
        if (isWish) {
          setBadge("wishlist", data.count);
          setBadge("cart", data.cart_count);
          if (currentKey === "wishlist") refresh();
          if (currentKey === "cart") refresh();
        } else {
          setBadge("cart", data.count);
          refresh();
        }
      })
      .catch(() => {
        form._busy = false;
        if (btn) btn.disabled = prevDisabled;
        toast("Error", "Network error, please retry.", "error");
      });
  }

  document.addEventListener("submit", function (e) {
    const form = e.target.closest("[data-drawer] form[data-panel-form]");
    if (!form) return;
    e.preventDefault();
    handleForm(form);
  });

  document.addEventListener("change", function (e) {
    const input = e.target;
    if (!input.name || input.name !== "quantity") return;
    const form = input.closest("form[data-panel-form]");
    if (!form || !form.closest("[data-drawer]")) return;
    handleForm(form);
  });
})();
