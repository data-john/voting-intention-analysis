"use strict";

// This warning still works when the publishing workflow never starts.
const updateSourceFreshness = () => {
  const timestamp = document.querySelector("[data-source-check]");
  const status = document.querySelector("[data-source-status]");
  if (!timestamp || !status) return;
  const now = new Date();
  const monday = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London", weekday: "short",
  }).format(now) === "Mon";
  const overdue = now - new Date(timestamp.dateTime) > (monday ? 2 : 7) * 3600000;
  status.classList.toggle("is-overdue", overdue);
  status.textContent = overdue
    ? "The next YouGov check is overdue. These figures reflect the last successful source check shown above."
    : "The YouGov workbook was checked successfully. The latest available poll is shown above.";
};
updateSourceFreshness();
setInterval(updateSourceFreshness, 60000);

document.querySelectorAll("[data-category-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const open = button.dataset.categoryAction === "open";
    document.querySelectorAll(".category-panel").forEach((panel) => {
      panel.open = open;
    });
  });
});

document.querySelectorAll("[data-group-filter]").forEach((input) => {
  const content = input.closest(".category-content");
  const cards = [...content.querySelectorAll("[data-filter-item]")];
  const status = content.querySelector("[data-filter-status]");
  const empty = content.querySelector("[data-filter-empty]");

  const update = () => {
    const query = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const matches = card.dataset.searchText.includes(query);
      card.hidden = !matches;
      if (matches) visible += 1;
    });
    status.textContent = `${visible} of ${cards.length} groups`;
    empty.hidden = visible !== 0;
  };

  input.addEventListener("input", update);
});

const dialog = document.querySelector("[data-chart-dialog]");
const dialogImage = dialog.querySelector("[data-dialog-image]");
const dialogCaption = dialog.querySelector("[data-dialog-caption]");
const viewport = dialog.querySelector("[data-dialog-viewport]");
const zoomLevel = dialog.querySelector("[data-zoom-level]");
const panHint = dialog.querySelector("[data-pan-hint]");
const zoomIn = dialog.querySelector("[data-zoom-in]");
const zoomOut = dialog.querySelector("[data-zoom-out]");
let fitScale = 1;
let zoomScale = 1;

const renderZoom = () => {
  if (!dialogImage.naturalWidth) return;
  const width = Math.round(dialogImage.naturalWidth * fitScale * zoomScale);
  const height = Math.round(dialogImage.naturalHeight * fitScale * zoomScale);
  dialogImage.style.width = `${width}px`;
  dialogImage.style.height = `${height}px`;
  zoomLevel.textContent = zoomScale === 1 ? "Fit" : `${Math.round(zoomScale * 100)}%`;
  viewport.classList.toggle("can-drag", zoomScale > 1);
  panHint.hidden = zoomScale <= 1;
  zoomIn.disabled = zoomScale >= 4;
  zoomOut.disabled = zoomScale <= 0.5;
};

const fitChart = () => {
  if (!dialogImage.naturalWidth) return;
  fitScale = Math.min(
    1,
    viewport.clientWidth / dialogImage.naturalWidth,
    viewport.clientHeight / dialogImage.naturalHeight,
  );
  zoomScale = 1;
  renderZoom();
  viewport.scrollTo(0, 0);
};

const setZoom = (nextScale) => {
  if (!dialogImage.naturalWidth) return;
  const oldWidth = Math.max(viewport.scrollWidth, viewport.clientWidth);
  const oldHeight = Math.max(viewport.scrollHeight, viewport.clientHeight);
  const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / oldWidth;
  const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / oldHeight;
  zoomScale = Math.min(4, Math.max(0.5, nextScale));
  renderZoom();
  requestAnimationFrame(() => {
    viewport.scrollLeft = centerX * Math.max(viewport.scrollWidth, viewport.clientWidth) - viewport.clientWidth / 2;
    viewport.scrollTop = centerY * Math.max(viewport.scrollHeight, viewport.clientHeight) - viewport.clientHeight / 2;
  });
};

dialogImage.addEventListener("load", () => requestAnimationFrame(fitChart));
zoomIn.addEventListener("click", () => setZoom(zoomScale * 1.25));
zoomOut.addEventListener("click", () => setZoom(zoomScale / 1.25));
dialog.querySelector("[data-zoom-fit]").addEventListener("click", fitChart);

dialog.addEventListener("keydown", (event) => {
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    setZoom(zoomScale * 1.25);
  } else if (event.key === "-") {
    event.preventDefault();
    setZoom(zoomScale / 1.25);
  } else if (event.key === "0") {
    event.preventDefault();
    fitChart();
  }
});

let dragState = null;
viewport.addEventListener("pointerdown", (event) => {
  if (event.target !== dialogImage || event.button !== 0 || zoomScale <= 1) return;
  dragState = {
    pointerId: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    scrollLeft: viewport.scrollLeft,
    scrollTop: viewport.scrollTop,
  };
  viewport.setPointerCapture(event.pointerId);
  viewport.classList.add("is-dragging");
  event.preventDefault();
});

viewport.addEventListener("pointermove", (event) => {
  if (!dragState || event.pointerId !== dragState.pointerId) return;
  viewport.scrollLeft = dragState.scrollLeft - (event.clientX - dragState.x);
  viewport.scrollTop = dragState.scrollTop - (event.clientY - dragState.y);
});

const stopDragging = () => {
  dragState = null;
  viewport.classList.remove("is-dragging");
};
viewport.addEventListener("pointerup", stopDragging);
viewport.addEventListener("pointercancel", stopDragging);
viewport.addEventListener("lostpointercapture", stopDragging);

viewport.addEventListener("wheel", (event) => {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  setZoom(zoomScale * (event.deltaY < 0 ? 1.25 : 1 / 1.25));
}, { passive: false });

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-chart-view]");
  if (!link || typeof dialog.showModal !== "function") return;

  event.preventDefault();
  const thumbnail = link.querySelector("img");
  dialogImage.alt = thumbnail ? thumbnail.alt : "Expanded chart";
  dialogCaption.textContent = link.closest("figure").querySelector("figcaption").textContent;
  dialog.showModal();
  dialogImage.src = link.href;
  requestAnimationFrame(fitChart);
});

dialog.querySelector("[data-close-dialog]").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
dialog.addEventListener("close", () => {
  dialogImage.removeAttribute("src");
  dialogImage.style.removeProperty("width");
  dialogImage.style.removeProperty("height");
  zoomScale = 1;
  dragState = null;
  viewport.classList.remove("can-drag", "is-dragging");
  panHint.hidden = true;
  zoomLevel.textContent = "Fit";
});
