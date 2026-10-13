/**
 * EN <-> AR language toggle.
 *
 * The `django_language` cookie set by /i18n/setlang/ stays the source of
 * truth (the server renders the page in that language); localStorage only
 * mirrors the choice so the client can re-sync if the cookie ever disappears.
 * Without JavaScript the form still posts to set_language and Django handles
 * the redirect + cookie itself.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "aurora_lang";
  var GUARD_KEY = "aurora_lang_synced";

  function remember(lang) {
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (err) {
      /* private mode / storage disabled */
    }
  }

  function remembered() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      return null;
    }
  }

  function postLanguage(form, lang) {
    var data = new FormData(form);
    data.set("language", lang);
    data.set("next", window.location.pathname + window.location.search);

    return fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
      redirect: "follow",
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("set_language failed with " + response.status);
      }
      return response.text();
    });
  }

  // document.write() re-parses the whole page in the *same* JS realm, so every
  // inline script runs again. Top-level `const`/`let` bindings from the first
  // run are still there, which makes the re-declaration throw a SyntaxError and
  // kills the entire script block (that is what blanked the dashboard charts
  // after switching to Arabic). Wrapping each inline body in an IIFE keeps
  // those declarations scoped to the block. Data scripts (json_script) and
  // external/module scripts must be left untouched.
  function wrapInlineScripts(html) {
    return html.replace(
      /<script(\b[^>]*)?>([\s\S]*?)<\/script\s*>/gi,
      function (match, attrs, body) {
        attrs = attrs || "";
        var isData =
          /type\s*=\s*["']?(application|text)\/(json|ld\+json)/i.test(attrs) ||
          /\btype\s*=\s*["']module["']/i.test(attrs);
        if (isData || /\bsrc\s*=/i.test(attrs) || /^\s*$/.test(body)) {
          return match;
        }
        return "<script" + attrs + ">(function(){" + body + "})();" + "</script>";
      }
    );
  }

  function swapDocument(html) {
    var scrollY = window.scrollY;
    try {
      document.open("text/html", "replace");
      document.write(wrapInlineScripts(html));
      document.close();
      window.scrollTo(0, scrollY);
    } catch (err) {
      reload(); // the language cookie is already set: one real load fixes it
      return;
    }
    // Scripts that throw *after* write() has returned (async parsing) would
    // leave a half-alive page: recover with one real load. Only a thrown
    // script counts, failed asset loads pass no `error` object.
    var recovery = function (event) {
      if (!event || !event.error) return;
      window.removeEventListener("error", recovery);
      reload();
    };
    window.addEventListener("error", recovery);
    setTimeout(function () {
      window.removeEventListener("error", recovery);
    }, 1000);
  }

  function reload() {
    window.location.reload();
  }

  function switchTo(form, lang) {
    remember(lang);
    postLanguage(form, lang)
      .then(swapDocument)
      .catch(function () {
        // The cookie may still be missing: retry once on the next load.
        try {
          sessionStorage.setItem(GUARD_KEY, lang);
        } catch (err) {
          /* ignore */
        }
        reload();
      });
  }

  // The cookie is HttpOnly, so a stored preference that differs from the
  // language the server rendered means the cookie was cleared: restore it.
  function syncStoredLanguage(form) {
    var stored = remembered();
    var current = document.documentElement.lang;
    if (!stored || !current || stored === current) {
      try {
        sessionStorage.removeItem(GUARD_KEY);
      } catch (err) {
        /* ignore */
      }
      return;
    }
    try {
      if (sessionStorage.getItem(GUARD_KEY) === stored) {
        // Already retried this value: stop nagging so we never loop.
        return;
      }
      sessionStorage.setItem(GUARD_KEY, stored);
    } catch (err) {
      return;
    }
    postLanguage(form, stored)
      .then(function () {
        reload();
      })
      .catch(function () {
        /* keep the rendered language, guard already prevents a loop */
      });
  }

  function init() {
    var form = document.getElementById("au-lang-form");
    if (!form) {
      return;
    }

    var pending = null;
    Array.prototype.forEach.call(
      form.querySelectorAll("button[data-lang]"),
      function (button) {
        button.addEventListener("click", function () {
          pending = button.dataset.lang;
        });
      }
    );

    form.addEventListener("submit", function (event) {
      var lang = pending || (event.submitter && event.submitter.dataset.lang);
      pending = null;
      if (!lang || lang === document.documentElement.lang) {
        return; // let the plain form POST handle it
      }
      event.preventDefault();
      switchTo(form, lang);
    });

    syncStoredLanguage(form);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
