/* Modern confirm modal — replaces native window.confirm() for destructive
   actions. Any form with a data-confirm attribute opens the modal instead of
   the browser dialog; the form is submitted only when the user confirms. */
(function () {
  "use strict";

  var modal = document.getElementById("au-confirm");
  var textEl = document.getElementById("au-confirm-text");
  var okBtn = document.getElementById("au-confirm-ok");
  var onConfirm = null;
  var lastFocus = null;

  function open(message, confirmHandler) {
    if (!modal || !textEl || !okBtn) {
      // Partial missing on this page: fall back to the browser dialog.
      if (window.confirm(message)) confirmHandler();
      return;
    }
    textEl.textContent = message;
    onConfirm = confirmHandler;
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("au-confirm-open");
    okBtn.focus();
  }

  function close() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove("au-confirm-open");
    onConfirm = null;
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
    lastFocus = null;
  }

  function confirmNow() {
    var handler = onConfirm;
    close();
    if (handler) handler();
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || form.tagName !== "FORM") return;
    var message = form.getAttribute("data-confirm");
    if (!message) return;

    event.preventDefault();
    open(message, function () {
      // Native submit() does not dispatch a "submit" event, so no recursion.
      HTMLFormElement.prototype.submit.call(form);
    });
  });

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-au-dismiss]")) {
      event.preventDefault();
      close();
    } else if (target.closest("#au-confirm-ok")) {
      event.preventDefault();
      confirmNow();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") close();
  });
})();
