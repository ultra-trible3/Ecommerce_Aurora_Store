/* Aurora Store — storefront interactions (vanilla JS) */
(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function csrfToken() {
    return window.CSRF_TOKEN || getCookie("csrftoken") || "";
  }

  function post(url, data) {
    const body = data instanceof FormData ? data : new URLSearchParams(data);
    if (!(body instanceof FormData)) body.append("csrfmiddlewaretoken", csrfToken());
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body,
      credentials: "same-origin",
    }).then((r) => r.json());
  }

  window.Aurora = { $, $$, getCookie, csrfToken, post };

  // ---------------------------------------------------------------------
  // Toasts (Django messages)
  // ---------------------------------------------------------------------
  function showToast(title, message, kind) {
    const host = $("#toast-host");
    if (!host) return;
    const color = kind === "error" ? "danger" : (kind || "success");
    const el = document.createElement("div");
    el.className = "toast au-toast";
    el.setAttribute("role", "alert");
    el.innerHTML =
      '<div class="toast-header">' +
      '<span class="dot me-2 bg-' + color + '"></span>' +
      '<strong class="me-auto">' + (title || "Notice") + "</strong>" +
      '<small class="text-muted">now</small>' +
      '<button type="button" class="btn-close ms-2 mb-1" data-bs-dismiss="toast" aria-label="Close"></button>' +
      "</div>" +
      '<div class="toast-body"></div>';
    el.querySelector(".toast-body").textContent = message || "";
    host.appendChild(el);
    const toast = new bootstrap.Toast(el, { delay: 4200 });
    toast.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  }
  window.showToast = showToast;

  document.addEventListener("DOMContentLoaded", function () {
    $$("#toast-host .toast").forEach((el) => {
      const t = new bootstrap.Toast(el, { delay: 4500 });
      t.show();
      el.addEventListener("hidden.bs.toast", () => el.remove());
    });
  });

  // ---------------------------------------------------------------------
  // Sticky header shadow on scroll
  // ---------------------------------------------------------------------
  const header = $("#site-header");
  if (header) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ---------------------------------------------------------------------
  // Search suggestions
  // ---------------------------------------------------------------------
  const searchInput = $("#search-input");
  const suggestBox = $("#search-suggest");
  if (searchInput && suggestBox) {
    let timer = null;
    let activeRequest = 0;

    const hide = () => suggestBox.classList.remove("show");

    searchInput.addEventListener("input", function () {
      const q = this.value.trim();
      clearTimeout(timer);
      if (q.length < 2) { hide(); return; }
      timer = setTimeout(() => {
        const id = ++activeRequest;
        fetch(`/search/suggest/?q=${encodeURIComponent(q)}`)
          .then((r) => r.json())
          .then((data) => {
            if (id !== activeRequest) return;
            if (!data.results || !data.results.length) { hide(); return; }
            suggestBox.innerHTML = data.results
              .map(
                (p) =>
                  `<a href="${p.url}">` +
                  (p.image ? `<img src="${p.image}" alt="">` : '<span class="no-image"></span>') +
                  `<span><b class="d-block">${p.name}</b>` +
                  `<small class="text-muted">${p.category || ""}</small></span>` +
                  `<span class="price">${p.price}</span></a>`
              )
              .join("");
            suggestBox.classList.add("show");
          })
          .catch(hide);
      }, 180);
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest("#header-search")) hide();
    });
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  }

  // ---------------------------------------------------------------------
  // Wishlist toggle (AJAX, falls back to full page)
  // ---------------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".wishlist-toggle");
    if (!btn) return;
    e.preventDefault();
    const slug = btn.dataset.product;
    if (!slug) return;
    post("/wishlist/toggle/", { slug: slug })
      .then((data) => {
        if (!data.authenticated) {
          window.location.href = `/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`;
          return;
        }
        btn.classList.toggle("is-active", data.wished);
        const icon = btn.querySelector("i");
        if (icon) icon.className = data.wished ? "bi bi-heart-fill" : "bi bi-heart";
        $$('[data-wishlist-count]').forEach((el) => (el.textContent = data.count));
        const wishLink = document.querySelector("[data-wishlist-link]");
        if (wishLink) {
          let wishBadge = wishLink.querySelector(".au-badge-count");
          if (data.count > 0 && !wishBadge) {
            wishBadge = document.createElement("span");
            wishBadge.className = "au-badge-count";
            wishBadge.setAttribute("data-wishlist-count", "");
            wishBadge.textContent = data.count;
            wishLink.appendChild(wishBadge);
          } else if (wishBadge && data.count === 0) {
            wishBadge.remove();
          }
        }
        showToast(
          data.wished ? "Added to wishlist" : "Removed from wishlist",
          data.wished ? "Saved for later." : "Removed from your wishlist.",
          data.wished ? "success" : "info"
        );
      })
      .catch(() => showToast("Error", "Could not update wishlist.", "error"));
  });

  // ---------------------------------------------------------------------
  // Compare toggle (AJAX, session-based — works without an account)
  // ---------------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".compare-toggle");
    if (!btn) return;
    e.preventDefault();
    const slug = btn.dataset.product;
    if (!slug) return;
    post("/compare/toggle/", { slug: slug })
      .then((data) => {
        if (!data.ok) {
          showToast("Compare", data.message || "Could not update compare list.", "error");
          return;
        }
        btn.classList.toggle("is-active", data.added);
        const icon = btn.querySelector("i");
        if (icon) icon.className = data.added ? "bi bi-columns-fill" : "bi bi-columns";
        $$('[data-compare-count]').forEach((el) => (el.textContent = data.count));
        showToast(
          data.added ? "Added to compare" : "Removed from compare",
          data.added ? "Open the compare page to see them side by side." : "Removed from your compare list.",
          data.added ? "success" : "info"
        );
        const headerLink = document.querySelector('a[href="/compare/"]');
        const badge = headerLink ? headerLink.querySelector(".au-badge-count") : null;
        if (data.count > 0 && !badge && headerLink) {
          const span = document.createElement("span");
          span.className = "au-badge-count";
          span.setAttribute("data-compare-count", "");
          span.textContent = data.count;
          headerLink.appendChild(span);
        } else if (badge) {
          badge.textContent = data.count;
          if (data.count === 0) badge.remove();
        }
      })
      .catch(() => showToast("Error", "Could not update compare list.", "error"));
  });

  // ---------------------------------------------------------------------
  // Quantity steppers
  // ---------------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const step = e.target.closest("[data-qty-step]");
    if (!step) return;
    const wrap = step.closest(".au-qty");
    if (!wrap) return;
    const input = wrap.querySelector("input[type=number], input[name=quantity]");
    if (!input) return;
    const min = parseInt(input.min || "1", 10);
    const max = parseInt(input.max || "9999", 10);
    let val = parseInt(input.value || "1", 10) || min;
    val += step.dataset.qtyStep === "up" ? 1 : -1;
    input.value = Math.max(min, Math.min(max, val));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // Auto-submit forms flagged data-autosubmit when a field inside changes.
  // Uses requestSubmit() so submit-event listeners (e.g. data-ajax-post) run.
  document.addEventListener("change", function (e) {
    const form = e.target.closest("form[data-autosubmit]");
    if (!form) return;
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.submit();
  });

  // ---------------------------------------------------------------------
  // Product gallery + lightbox album
  // ---------------------------------------------------------------------
  const gallery = $(".au-gallery");
  if (gallery) {
    const main = gallery.querySelector(".main-img img");
    const mainWrap = gallery.querySelector(".main-img");
    const thumbBtns = $$("[data-gallery-src]", gallery);
    // Album = main image first, then gallery images (thumb order).
    const album = thumbBtns.length
      ? thumbBtns.map((t) => ({ src: t.dataset.gallerySrc, alt: t.dataset.galleryAlt || "" }))
      : main
      ? [{ src: main.getAttribute("src"), alt: main.alt || "" }]
      : [];

    const lightboxEl = $("#productLightbox");
    const lbImg = $("#lb-img");
    const lbCount = $("#lb-count");
    const lbThumbs = $("#lb-thumbs");
    const lbPrev = $("#lb-prev");
    const lbNext = $("#lb-next");
    let lbModal = null;
    let lbIndex = 0;

    const setInline = (i) => {
      const item = album[i];
      if (!item || !main) return;
      main.setAttribute("src", item.src);
      main.alt = item.alt;
      thumbBtns.forEach((t, ti) => t.classList.toggle("active", ti === i));
      if (mainWrap) mainWrap.classList.remove("zoom");
    };

    const renderLb = () => {
      const item = album[lbIndex];
      if (!item) return;
      lbImg.setAttribute("src", item.src);
      lbImg.alt = item.alt;
      lbCount.textContent = lbIndex + 1 + " / " + album.length;
      const multi = album.length > 1;
      lbPrev.style.display = multi ? "" : "none";
      lbNext.style.display = multi ? "" : "none";
      lbThumbs.innerHTML = "";
      album.forEach((it, i) => {
        const b = document.createElement("button");
        b.type = "button";
        if (i === lbIndex) b.className = "active";
        const im = document.createElement("img");
        im.src = it.src;
        im.alt = "";
        b.appendChild(im);
        b.addEventListener("click", () => {
          lbIndex = i;
          renderLb();
        });
        lbThumbs.appendChild(b);
      });
      // Keep the inline gallery in sync with the lightbox.
      setInline(lbIndex);
      const activeThumb = lbThumbs.children[lbIndex];
      if (activeThumb && activeThumb.scrollIntoView) {
        activeThumb.scrollIntoView({ block: "nearest", inline: "center" });
      }
    };

    const openLb = (start) => {
      lbIndex = Math.max(0, Math.min(start, album.length - 1));
      renderLb();
      if (!lbModal) lbModal = new bootstrap.Modal(lightboxEl);
      lbModal.show();
    };

    const step = (d) => {
      lbIndex = (lbIndex + d + album.length) % album.length;
      renderLb();
    };

    // Thumbnail strip swaps the main image inline (existing behaviour).
    thumbBtns.forEach((t, i) => {
      t.addEventListener("click", () => setInline(i));
    });

    // Clicking the main image opens the album modal at the current image.
    if (mainWrap && album.length && main) {
      mainWrap.addEventListener("click", () => {
        const current = main.getAttribute("src");
        const idx = album.findIndex((a) => a.src === current);
        openLb(idx >= 0 ? idx : 0);
      });
    }

    if (lightboxEl) {
      lbPrev.addEventListener("click", () => step(-1));
      lbNext.addEventListener("click", () => step(1));
      lbImg.addEventListener("click", () => step(1));
      document.addEventListener("keydown", (e) => {
        if (!lightboxEl.classList.contains("show")) return;
        if (e.key === "ArrowLeft") step(-1);
        if (e.key === "ArrowRight") step(1);
      });
    }
  }

  // ---------------------------------------------------------------------
  // Variant selection (updates price/stock/hidden inputs)
  // ---------------------------------------------------------------------
  const variantBox = $("#variant-selector");
  if (variantBox) {
    variantBox.addEventListener("click", function (e) {
      const opt = e.target.closest(".au-variant");
      if (!opt || opt.disabled) return;
      $$(".au-variant", variantBox).forEach((o) => o.classList.remove("active"));
      opt.classList.add("active");
      const variantInput = $("#variant-input");
      if (variantInput) variantInput.value = opt.dataset.variantId || "";

      const priceEl = $("#product-price");
      if (priceEl && opt.dataset.price) priceEl.textContent = opt.dataset.price;
      const wasEl = $("#product-was-price");
      if (wasEl) {
        if (opt.dataset.salePrice) {
          wasEl.textContent = opt.dataset.wasPrice;
          wasEl.classList.remove("d-none");
        } else {
          wasEl.classList.add("d-none");
        }
      }
      const stockEl = $("#product-stock");
      if (stockEl) {
        const qty = parseInt(opt.dataset.stock || "0", 10);
        stockEl.innerHTML = qty > 0
          ? '<i class="bi bi-check-circle-fill text-success me-1"></i>In stock (' + qty + " available)"
          : '<i class="bi bi-x-circle-fill text-danger me-1"></i>Out of stock';
      }
      const qtyInput = $("#qty-input");
      if (qtyInput) {
        const qty = parseInt(opt.dataset.stock || "0", 10);
        qtyInput.max = Math.max(qty, 1);
        if (parseInt(qtyInput.value, 10) > qty) qtyInput.value = Math.max(qty, 1);
      }
      const addBtn = $("#add-to-cart-btn");
      if (addBtn) addBtn.disabled = parseInt(opt.dataset.stock || "0", 10) <= 0;
    });
  }

  // ---------------------------------------------------------------------
  // Newsletter form (AJAX)
  // ---------------------------------------------------------------------
  const newsletter = $("#newsletter-form");
  if (newsletter) {
    newsletter.addEventListener("submit", function (e) {
      e.preventDefault();
      const btn = this.querySelector("button");
      btn.classList.add("is-loading");
      btn.dataset.orig = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
      post(this.action, new FormData(this))
        .then((data) => {
          btn.classList.remove("is-loading");
          btn.innerHTML = btn.dataset.orig;
          showToast(
            data.ok ? "Subscribed!" : "Hmm...",
            data.message || "",
            data.ok ? "success" : "error"
          );
          if (data.ok) newsletter.reset();
        })
        .catch(() => {
          btn.classList.remove("is-loading");
          btn.innerHTML = btn.dataset.orig;
          showToast("Error", "Could not subscribe right now.", "error");
        });
    });
  }

  // ---------------------------------------------------------------------
  // Generic AJAX post handlers (data-ajax-post)
  // ---------------------------------------------------------------------
  function updateCartBadge(count) {
    const spans = $$("[data-cart-count]");
    if (count > 0) {
      if (spans.length) {
        spans.forEach((el) => (el.textContent = count));
      } else {
        const link = document.querySelector('[data-drawer-open][data-drawer-key="cart"]');
        if (link) {
          const span = document.createElement("span");
          span.className = "au-badge-count";
          span.setAttribute("data-cart-count", "");
          span.textContent = count;
          link.appendChild(span);
        }
      }
    } else {
      spans.forEach((el) => el.remove());
    }
  }

  document.addEventListener("submit", function (e) {
    const form = e.target.closest("form[data-ajax-post]");
    if (!form) return;
    e.preventDefault();
    const btn = form.querySelector("[type=submit]");
    if (btn) { btn.disabled = true; btn.dataset.orig = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
    post(form.action, new FormData(form))
      .then((data) => {
        if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig; }
        if (data.redirect) { window.location.href = data.redirect; return; }
        if (typeof data.count === "number") updateCartBadge(data.count);
        if (data.ok === false) {
          showToast("Error", data.message || "Request failed.", "error");
        } else {
          showToast(data.title || "Done", data.message || "Updated.", "success");
          if (data.reload !== false) setTimeout(() => window.location.reload(), 650);
        }
      })
      .catch(() => {
        if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.orig; }
        showToast("Error", "Network error, please retry.", "error");
      });
  });

  // ---------------------------------------------------------------------
  // Filter sidebar toggle (mobile)
  // ---------------------------------------------------------------------
  const filterToggle = $("#filter-toggle");
  if (filterToggle) {
    filterToggle.addEventListener("click", () => {
      const panel = $("#shop-filters");
      if (panel) panel.classList.toggle("d-none");
    });
  }

  // Remove a querystring parameter and reload (used by active-filter chips)
  window.removeFilterParam = function (key) {
    const url = new URL(window.location.href);
    url.searchParams.delete(key);
    url.searchParams.delete("page");
    window.location.href = url.toString();
  };
})();
