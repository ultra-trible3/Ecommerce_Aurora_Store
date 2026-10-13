/* Profile photo cropping (Cropper.js) — pick, crop, then upload. */
(function () {
  "use strict";

  var input = document.querySelector('input[type="file"][data-crop]');
  var modal = input && document.getElementById("au-crop");
  if (!input || !modal) {
    return;
  }

  var CropperLib = window.Cropper;
  var img = document.getElementById("au-crop-img");
  var zoom = document.getElementById("au-crop-zoom");
  var applyBtn = document.getElementById("au-crop-apply");
  var rotLeft = document.getElementById("au-crop-rot-l");
  var rotRight = document.getElementById("au-crop-rot-r");
  var photoWrap = input.closest(".au-photo");
  var preview = photoWrap && photoWrap.querySelector(".au-photo-avatar");
  var state = document.querySelector("[data-crop-state]");
  var stateText = document.querySelector("[data-crop-state-text]");
  var resetBtn = document.querySelector("[data-crop-reset]");

  var ratio = parseFloat(input.getAttribute("data-crop-ratio") || "1");
  var size = parseInt(input.getAttribute("data-crop-size") || "512", 10) || 512;
  var maxBytes = 5 * 1024 * 1024;

  var cropper = null;
  var objectUrl = null;
  var zoomValue = Number(zoom.value);
  var hasApplied = false;
  var previewHTML = preview ? preview.innerHTML : "";

  function setState(message, isError) {
    if (!state) {
      return;
    }
    state.hidden = !message;
    state.classList.toggle("is-error", Boolean(isError));
    if (stateText) {
      stateText.textContent = message || "";
    }
  }

  function openModal(file) {
    objectUrl = URL.createObjectURL(file);
    img.src = objectUrl;
    modal.hidden = false;
    document.documentElement.style.overflow = "hidden";
    if (cropper) {
      cropper.destroy();
    }
    cropper = new CropperLib(img, {
      viewMode: 1,
      dragMode: "move",
      aspectRatio: ratio > 0 ? ratio : NaN,
      autoCropArea: 0.9,
      responsive: true,
      restore: false,
      guides: true,
      center: true,
      movable: true,
      zoomable: true,
      rotatable: true,
      scalable: false,
      background: false
    });
    zoomValue = Number(zoom.value);
    applyBtn.focus();
  }

  function closeModal() {
    modal.hidden = true;
    document.documentElement.style.overflow = "";
    if (cropper) {
      cropper.destroy();
      cropper = null;
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    img.removeAttribute("src");
  }

  function cancelCrop() {
    closeModal();
    if (!hasApplied) {
      input.value = "";
      setState("");
    }
  }

  function applyCrop() {
    if (!cropper) {
      return;
    }
    var cropped = cropper.getCroppedCanvas({
      width: size,
      height: size,
      minWidth: size,
      minHeight: size,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high"
    });
    if (!cropped) {
      cancelCrop();
      return;
    }

    var out = document.createElement("canvas");
    out.width = size;
    out.height = size;
    var ctx = out.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(cropped, 0, 0, size, size);

    out.toBlob(function (blob) {
      if (!blob) {
        cancelCrop();
        return;
      }
      var name = "avatar-" + Date.now() + ".jpg";
      if (typeof File !== "undefined" && typeof DataTransfer !== "undefined") {
        var file = new File([blob], name, {
          type: "image/jpeg",
          lastModified: Date.now()
        });
        var dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        hasApplied = true;
      }
      if (preview) {
        preview.innerHTML =
          '<img src="' + out.toDataURL("image/jpeg", 0.9) +
          '" alt="' + t("New photo preview") + '">';
      }
      setState(ts("Cropped photo ready — %s (%s×%s)", name, size, size));
      closeModal();
    }, "image/jpeg", 0.9);
  }

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) {
      return;
    }
    if (!/^image\//.test(file.type)) {
      setState(t("That file is not an image — choose a JPG or PNG."), true);
      input.value = "";
      return;
    }
    if (file.size > maxBytes) {
      setState(t("Image is too large (max 5 MB)."), true);
      input.value = "";
      return;
    }
    if (!CropperLib) {
      setState(ts("Photo selected: %s", file.name));
      return;
    }
    openModal(file);
  });

  zoom.addEventListener("input", function () {
    if (!cropper) {
      return;
    }
    var value = Number(zoom.value);
    var delta = ((value - zoomValue) / 100) * 0.8;
    zoomValue = value;
    if (delta) {
      cropper.zoom(delta);
    }
  });

  rotLeft.addEventListener("click", function () {
    if (cropper) {
      cropper.rotate(-90);
    }
  });

  rotRight.addEventListener("click", function () {
    if (cropper) {
      cropper.rotate(90);
    }
  });

  applyBtn.addEventListener("click", applyCrop);

  Array.prototype.forEach.call(
    modal.querySelectorAll("[data-crop-dismiss]"),
    function (el) {
      el.addEventListener("click", cancelCrop);
    }
  );

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      input.value = "";
      hasApplied = false;
      if (preview) {
        preview.innerHTML = previewHTML;
      }
      setState("");
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) {
      cancelCrop();
    }
  });
})();
