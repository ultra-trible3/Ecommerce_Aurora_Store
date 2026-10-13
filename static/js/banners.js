/* Banner tracking and interactions (vanilla JS) */
(function () {
  "use strict";

  // Walk up the DOM to find a URL provided via data attributes
  // (data-impression-url / data-seen-url / data-click-url)
  function readUrl(el, key) {
    while (el) {
      if (el.dataset && el.dataset[key]) return el.dataset[key];
      el = el.parentElement;
    }
    return null;
  }

  function post(url) {
    if (!url) return;
    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": window.CSRFToken || window.CSRF_TOKEN || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    }).catch(function () {});
  }

  function trackImpression(el) {
    post(readUrl(el, "impressionUrl"));
  }

  function trackClick(el) {
    post(readUrl(el, "clickUrl"));
  }

  function markSeen(el) {
    post(readUrl(el, "seenUrl"));
  }

  // Observe banner visibility for impression tracking
  function observeBanner(bannerEl) {
    if (!bannerEl.dataset.bannerId) return;

    var impressionSent = false;
    var seenSent = false;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting && !impressionSent) {
            impressionSent = true;
            trackImpression(entry.target);
            // If show_once_per_session, mark as seen
            if (bannerEl.dataset.showOncePerSession === "true" && !seenSent) {
              seenSent = true;
              markSeen(entry.target);
            }
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );

    observer.observe(bannerEl);
  }

  // Track clicks on banner links/buttons
  function trackBannerClicks() {
    document.addEventListener("click", function (e) {
      var link = e.target.closest("[data-banner-id][data-banner-action]");
      if (!link) return;
      if (!link.dataset.bannerId) return;
      trackClick(link);
    });
  }

  // Initialize on DOM ready
  document.addEventListener("DOMContentLoaded", function () {
    // Observe all banners (hero banner + carousel slides)
    document
      .querySelectorAll(".au-hero-banner[data-banner-id], .carousel-item[data-banner-id]")
      .forEach(observeBanner);
    // Track clicks
    trackBannerClicks();
  });
})();
