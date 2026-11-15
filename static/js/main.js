/* ==========================================================================
   آب پاک | ABPAK — Main scripts
   Theme • Header • Drawer • Slider • Live search • AJAX cart • Tabs • Filters • FAQ
   ========================================================================== */
(function () {
  "use strict";

  var body = document.body;
  var $ = function (selector, root) { return (root || document).querySelector(selector); };
  var $$ = function (selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); };
  var csrf = ($('meta[name="csrf-token"]') || {}).content || "";
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function toFa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }

  function formatPrice(value) {
    return toFa(Number(value || 0).toLocaleString("en-US").replace(/,/g, "٬"));
  }

  /* ------------------------------------------------------------------ Toasts */
  var toastStack = $("#toastStack");
  function toast(message, type) {
    if (!toastStack || !message) return;
    type = type || "success";
    var icons = { success: "i-check-circle", error: "i-info", info: "i-info" };
    var el = document.createElement("div");
    el.className = "toast toast--" + type;
    el.innerHTML =
      '<span class="toast__icon"><svg class="icon" aria-hidden="true"><use href="#' +
      (icons[type] || "i-info") +
      '"></use></svg></span><div class="toast__body"></div>' +
      '<button type="button" class="toast__close" aria-label="بستن"><svg class="icon" style="width:14px;height:14px"><use href="#i-close"></use></svg></button>';
    $(".toast__body", el).textContent = message;
    toastStack.appendChild(el);
    var remove = function () {
      el.classList.add("is-hiding");
      window.setTimeout(function () { el.remove(); }, 300);
    };
    $(".toast__close", el).addEventListener("click", remove);
    window.setTimeout(remove, 4500);
  }

  /* ------------------------------------------------------------------ Theme */
  var themeToggleButtons = $$("[data-theme-toggle]");
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("abpak-theme", theme); } catch (e) {}
    themeToggleButtons.forEach(function (button) {
      button.setAttribute("aria-label", theme === "dark" ? "روشن کردن حالت روز" : "فعال کردن حالت شب");
      button.setAttribute("title", theme === "dark" ? "حالت روز" : "حالت شب");
    });
  }
  themeToggleButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      toast(next === "dark" ? "حالت شب فعال شد." : "حالت روز فعال شد.", "info");
    });
  });
  applyTheme(document.documentElement.getAttribute("data-theme") || "light");

  /* ------------------------------------------------------------------ Header / scroll */
  var header = $(".header");
  var backToTop = $("#backToTop");
  function onScroll() {
    var y = window.scrollY || document.documentElement.scrollTop;
    if (header) header.classList.toggle("is-stuck", y > 8);
    if (backToTop) backToTop.classList.toggle("is-visible", y > 520);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  if (backToTop) {
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    });
  }

  /* ------------------------------------------------------------------ Drawer */
  var drawer = $("#mobileDrawer");
  var drawerOpeners = $$("[data-drawer-open]");
  var drawerClosers = $$("[data-drawer-close]");
  function setDrawer(open) {
    if (!drawer) return;
    drawer.classList.toggle("is-open", open);
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    body.classList.toggle("is-locked", open);
    drawerOpeners.forEach(function (btn) { btn.setAttribute("aria-expanded", open ? "true" : "false"); });
    if (open) {
      var first = $("input, a, button", drawer);
      if (first) window.setTimeout(function () { first.focus(); }, 120);
    }
  }
  drawerOpeners.forEach(function (btn) { btn.addEventListener("click", function () { setDrawer(true); }); });
  drawerClosers.forEach(function (btn) { btn.addEventListener("click", function () { setDrawer(false); }); });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (drawer && drawer.classList.contains("is-open")) setDrawer(false);
    closeAllDropdowns();
    closeSuggest();
    closeFilters();
  });

  /* ------------------------------------------------------------------ Dropdown menus */
  var dropdowns = $$("[data-dropdown]");
  function closeAllDropdowns(except) {
    dropdowns.forEach(function (item) {
      if (item !== except) {
        item.classList.remove("is-open");
        var toggle = $("[data-dropdown-toggle]", item);
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      }
    });
  }
  dropdowns.forEach(function (item) {
    var toggle = $("[data-dropdown-toggle]", item);
    if (!toggle) return;
    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var open = !item.classList.contains("is-open");
      closeAllDropdowns(item);
      item.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-dropdown]")) closeAllDropdowns();
  });

  /* ------------------------------------------------------------------ Hero slider */
  var slider = $("[data-slider]");
  if (slider) {
    var slides = $$("[data-slide]", slider);
    var dots = $$("[data-slide-to]", slider);
    var progress = $("[data-slider-progress]", slider);
    var interval = parseInt(slider.getAttribute("data-autoplay") || "7500", 10);
    var current = 0;
    var timer = null;
    var paused = false;

    var showSlide = function (index) {
      if (!slides.length) return;
      current = (index + slides.length) % slides.length;
      slides.forEach(function (slide, i) {
        slide.classList.toggle("is-active", i === current);
        slide.setAttribute("aria-hidden", i === current ? "false" : "true");
      });
      dots.forEach(function (dot, i) {
        dot.classList.toggle("is-active", i === current);
        dot.setAttribute("aria-selected", i === current ? "true" : "false");
      });
      if (progress) {
        progress.classList.remove("is-running");
        void progress.offsetWidth;
        if (!reduceMotion) progress.classList.add("is-running");
      }
    };

    var start = function () {
      if (reduceMotion || slides.length < 2) return;
      stop();
      timer = window.setInterval(function () { if (!paused) showSlide(current + 1); }, interval);
    };
    var stop = function () { if (timer) { window.clearInterval(timer); timer = null; } };

    dots.forEach(function (dot) {
      dot.addEventListener("click", function () {
        showSlide(parseInt(dot.getAttribute("data-slide-to"), 10) || 0);
        start();
      });
    });
    var prev = $("[data-slide-prev]", slider);
    var next = $("[data-slide-next]", slider);
    if (prev) prev.addEventListener("click", function () { showSlide(current - 1); start(); });
    if (next) next.addEventListener("click", function () { showSlide(current + 1); start(); });

    slider.addEventListener("mouseenter", function () { paused = true; });
    slider.addEventListener("mouseleave", function () { paused = false; });
    slider.addEventListener("focusin", function () { paused = true; });
    slider.addEventListener("focusout", function () { paused = false; });

    var touchStartX = null;
    slider.addEventListener("pointerdown", function (event) { touchStartX = event.clientX; });
    slider.addEventListener("pointerup", function (event) {
      if (touchStartX === null) return;
      var delta = event.clientX - touchStartX;
      if (Math.abs(delta) > 45) showSlide(current + (delta > 0 ? 1 : -1));
      touchStartX = null;
      start();
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop();
      else start();
    });

    showSlide(0);
    start();
  }

  /* ------------------------------------------------------------------ Live search */
  var searchForm = $("[data-search-form]");
  var searchInput = $("[data-search-input]");
  var suggestBox = $("[data-search-suggest]");
  var suggestTimer = null;
  var suggestController = null;

  function closeSuggest() {
    if (suggestBox) {
      suggestBox.hidden = true;
      suggestBox.innerHTML = "";
    }
  }

  function renderSuggestions(query, results) {
    if (!suggestBox) return;
    suggestBox.innerHTML = "";
    if (!results.length) {
      var empty = document.createElement("div");
      empty.className = "suggest__empty";
      empty.textContent = "محصولی برای «" + query + "» پیدا نشد.";
      suggestBox.appendChild(empty);
    } else {
      results.forEach(function (item) {
        var link = document.createElement("a");
        link.className = "suggest__item";
        link.href = item.url;
        var iconWrap = document.createElement("span");
        iconWrap.className = "suggest__icon";
        iconWrap.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-' + (item.icon || "filter") + '"></use></svg>';
        var bodyEl = document.createElement("span");
        bodyEl.className = "suggest__body";
        var name = document.createElement("span");
        name.className = "suggest__name";
        name.textContent = item.name;
        var meta = document.createElement("span");
        meta.className = "suggest__meta";
        meta.textContent = item.category + (item.in_stock ? " · موجود" : " · ناموجود");
        bodyEl.appendChild(name);
        bodyEl.appendChild(meta);
        var price = document.createElement("span");
        price.className = "suggest__price";
        price.textContent = item.price + " تومان";
        link.appendChild(iconWrap);
        link.appendChild(bodyEl);
        link.appendChild(price);
        suggestBox.appendChild(link);
      });
    }
    var all = document.createElement("a");
    all.className = "suggest__all";
    all.href = "/search/?q=" + encodeURIComponent(query);
    all.textContent = "مشاهده همه نتایج";
    suggestBox.appendChild(all);
    suggestBox.hidden = false;
  }

  if (searchInput && suggestBox) {
    searchInput.addEventListener("input", function () {
      var query = searchInput.value.trim();
      window.clearTimeout(suggestTimer);
      if (query.length < 2) { closeSuggest(); return; }
      suggestTimer = window.setTimeout(function () {
        if (suggestController) suggestController.abort();
        suggestController = new AbortController();
        fetch(body.dataset.suggestUrl + "?q=" + encodeURIComponent(query), {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: suggestController.signal,
        })
          .then(function (response) { return response.json(); })
          .then(function (data) { renderSuggestions(data.query || query, data.results || []); })
          .catch(function () {});
      }, 240);
    });
    searchInput.addEventListener("focus", function () {
      if (searchInput.value.trim().length >= 2 && suggestBox.innerHTML) suggestBox.hidden = false;
    });
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeSuggest();
    });
    document.addEventListener("click", function (event) {
      if (searchForm && !searchForm.contains(event.target)) closeSuggest();
    });
    if (searchForm) {
      searchForm.addEventListener("submit", function (event) {
        if (!searchInput.value.trim()) {
          event.preventDefault();
          searchInput.focus();
        }
      });
    }
  }

  /* ------------------------------------------------------------------ Cart badge + add to cart */
  var cartBadge = $("[data-cart-count]");
  function syncCartCount(count) {
    if (!cartBadge) return;
    cartBadge.textContent = toFa(count);
    cartBadge.hidden = !count;
    cartBadge.classList.remove("is-bump");
    void cartBadge.offsetWidth;
    cartBadge.classList.add("is-bump");
  }

  function postForm(form, options) {
    options = options || {};
    var formData = new FormData(form);
    if (options.submitter && options.submitter.name) formData.append(options.submitter.name, options.submitter.value);
    var payload = new URLSearchParams();
    formData.forEach(function (value, key) {
      if (typeof value === "string") payload.append(key, value);
    });
    return fetch(form.action, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf,
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      },
      body: payload.toString(),
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw data;
        return data;
      });
    });
  }

  $$("[data-add-to-cart]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      var submitter = event.submitter || $('[type="submit"]', form);
      var button = submitter;
      if (button) button.disabled = true;
      postForm(form, { submitter: submitter })
        .then(function (data) {
          if (requestBuyNow(submitter) && data.ok) {
            window.location.href = "/checkout/";
            return;
          }
          toast(data.message, "success");
          syncCartCount(data.cart_count);
        })
        .catch(function (error) {
          toast((error && error.message) || "افزودن محصول انجام نشد. دوباره تلاش کنید.", "error");
        })
        .finally(function () {
          if (button) button.disabled = false;
        });
    });
  });

  function requestBuyNow(submitter) {
    return submitter && submitter.getAttribute("name") === "redirect_to";
  }

  /* ------------------------------------------------------------------ Cart page */
  $$("[data-cart-remove]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      var row = form.closest("[data-cart-row]");
      postForm(form)
        .then(function (data) {
          toast(data.message, "info");
          syncCartCount(data.cart_count);
          if (row) {
            row.style.transition = "opacity .25s";
            row.style.opacity = "0";
            window.setTimeout(function () {
              row.remove();
              updateSummary(data);
              if (data.cart_count === 0) window.location.reload();
            }, 220);
          }
        })
        .catch(function () { toast("حذف محصول انجام نشد. صفحه را دوباره بارگذاری کنید.", "error"); });
    });
  });

  $$(".cart-item form").forEach(function (form) {
    if (form.hasAttribute("data-cart-remove")) return;
    form.addEventListener("submit", function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      var row = form.closest("[data-cart-row]");
      postForm(form)
        .then(function (data) {
          syncCartCount(data.cart_count);
          updateSummary(data);
          if (row) {
            var qty = $("[data-line-qty]", row);
            var total = $("[data-line-total]", row);
            if (qty) qty.value = toFa(data.quantity);
            if (total) total.innerHTML = data.item_total_display + "<small>تومان</small>";
          }
          if (data.limited && data.message) toast(data.message, "info");
          if (data.quantity === 0) {
            window.setTimeout(function () {
              if (row) row.remove();
              if (data.cart_count === 0) window.location.reload();
            }, 200);
          }
        })
        .catch(function () { toast("بروزرسانی سبد انجام نشد. دوباره تلاش کنید.", "error"); });
    });
  });

  function updateSummary(data) {
    var shipping = $("[data-summary-shipping]");
    var total = $("[data-summary-total]");
    if (shipping) shipping.textContent = data.shipping === 0 ? "رایگان" : data.shipping_display + " تومان";
    if (total) total.textContent = data.total_display + " تومان";
  }

  /* ------------------------------------------------------------------ Quantity steppers */
  $$("[data-qty]").forEach(function (wrapper) {
    var input = $("[data-qty-input]", wrapper);
    if (!input) return;
    var max = parseInt(wrapper.getAttribute("data-max") || "0", 10);
    var clamp = function (value) {
      var number = parseInt(value, 10);
      if (isNaN(number) || number < 1) number = 1;
      if (max > 0 && number > max) number = max;
      return number;
    };
    var minus = $("[data-qty-minus]", wrapper);
    var plus = $("[data-qty-plus]", wrapper);
    if (minus) minus.addEventListener("click", function () { input.value = clamp(parseInt(input.value, 10) - 1); });
    if (plus) plus.addEventListener("click", function () {
      var next = clamp(parseInt(input.value, 10) + 1);
      input.value = next;
      if (max > 0 && next >= max) toast("حداکثر موجودی این محصول " + toFa(max) + " عدد است.", "info");
    });
    input.addEventListener("change", function () { input.value = clamp(input.value); });
  });

  /* ------------------------------------------------------------------ Tabs */
  $$("[data-tabs]").forEach(function (tabsRoot) {
    var buttons = $$("[data-tab-target]", tabsRoot);
    var panels = $$("[data-tab-panel]", tabsRoot);
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var target = button.getAttribute("data-tab-target");
        buttons.forEach(function (item) {
          var active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          panel.classList.toggle("is-active", panel.getAttribute("data-tab-panel") === target);
        });
      });
    });
  });

  /* ------------------------------------------------------------------ Gallery */
  var gallery = $("[data-gallery]");
  if (gallery) {
    var mainImage = $("[data-gallery-main]", gallery);
    $$("[data-gallery-thumb]", gallery).forEach(function (thumb) {
      thumb.addEventListener("click", function () {
        if (!mainImage) return;
        mainImage.src = thumb.getAttribute("data-src");
        $$("[data-gallery-thumb]", gallery).forEach(function (item) { item.classList.remove("is-active"); });
        thumb.classList.add("is-active");
      });
    });
  }

  /* ------------------------------------------------------------------ Checkout shipping */
  var checkoutForm = $("[data-checkout-form]");
  if (checkoutForm) {
    var subtotal = parseInt(checkoutForm.getAttribute("data-subtotal") || "0", 10);
    var threshold = parseInt(checkoutForm.getAttribute("data-free-threshold") || "0", 10);
    var shippingLabel = $("[data-checkout-shipping]");
    var totalLabel = $("[data-checkout-total]");
    var updateTotals = function () {
      var selected = $('input[name="shipping_method"]:checked', checkoutForm);
      if (!selected) return;
      var cost = parseInt(selected.getAttribute("data-cost") || "0", 10);
      if (selected.value === "post" && threshold > 0 && subtotal >= threshold) cost = 0;
      if (shippingLabel) shippingLabel.textContent = cost === 0 ? "رایگان" : formatPrice(cost) + " تومان";
      if (totalLabel) totalLabel.textContent = formatPrice(subtotal + cost) + " تومان";
    };
    $$('input[name="shipping_method"]', checkoutForm).forEach(function (radio) {
      radio.addEventListener("change", updateTotals);
    });
    updateTotals();
  }

  /* ------------------------------------------------------------------ Auto submit selects */
  $$("[data-auto-submit]").forEach(function (select) {
    select.addEventListener("change", function () {
      if (select.form) select.form.submit();
    });
  });

  /* ------------------------------------------------------------------ Filters drawer */
  var filtersPanel = $("#filtersPanel");
  var filtersBackdrop = $(".filters-backdrop");
  function closeFilters() {
    if (!filtersPanel || !filtersPanel.classList.contains("is-open")) return;
    filtersPanel.classList.remove("is-open");
    if (filtersBackdrop) filtersBackdrop.classList.remove("is-open");
    body.classList.remove("filters-open");
  }
  $$("[data-filters-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!filtersPanel) return;
      filtersPanel.classList.add("is-open");
      if (filtersBackdrop) filtersBackdrop.classList.add("is-open");
      body.classList.add("filters-open");
    });
  });
  $$("[data-filters-close]").forEach(function (button) { button.addEventListener("click", closeFilters); });

  /* × در سربرگ فیلترها: جمع و باز کردن جزئیات فیلتراسیون */
  var filtersToggle = $("[data-filters-toggle]");
  if (filtersToggle && filtersPanel) {
    filtersToggle.addEventListener("click", function () {
      var collapsed = filtersPanel.classList.toggle("is-collapsed");
      filtersToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      filtersToggle.setAttribute("aria-label", collapsed ? "باز کردن جزئیات فیلترها" : "بستن جزئیات فیلترها");
    });
  }

  /* ------------------------------------------------------------------ FAQ search */
  var faqSearch = $("[data-faq-search]");
  if (faqSearch) {
    faqSearch.addEventListener("input", function () {
      var query = faqSearch.value.trim().toLowerCase();
      var groups = $$("[data-faq-group]");
      var anyVisible = false;
      groups.forEach(function (group) {
        var items = $$("[data-faq-item]", group);
        var visibleCount = 0;
        items.forEach(function (item) {
          var text = item.textContent.toLowerCase();
          var match = !query || text.indexOf(query) !== -1;
          item.classList.toggle("is-hidden", !match);
          if (match) visibleCount += 1;
        });
        group.style.display = visibleCount ? "" : "none";
        if (visibleCount) anyVisible = true;
      });
      var empty = $("[data-faq-empty]");
      if (empty) empty.classList.toggle("is-visible", !anyVisible);
    });
  }

  /* ------------------------------------------------------------------ Scroll reveal */
  var animationsOn = document.documentElement.getAttribute("data-anim") !== "off";
  if (animationsOn && !reduceMotion && "IntersectionObserver" in window) {
    var revealTargets = $$(
      ".section__head, .benefit, .category-card, .product-card, .about-split__art, " +
        ".about-split > div, .brand-strip, .cta-band, .stats-row, .content-split > *, .page-hero"
    );
    revealTargets = revealTargets.filter(function (el) {
      /* Elements already in the first viewport must never be hidden,
         otherwise they become late LCP candidates. */
      return el.getBoundingClientRect().top > window.innerHeight * 0.92;
    });
    revealTargets.forEach(function (el, index) {
      el.classList.add("reveal");
      el.style.transitionDelay = (index % 5) * 70 + "ms";
    });
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    revealTargets.forEach(function (el) { revealObserver.observe(el); });
  }

  /* ------------------------------------------------------------------ Cursor aura */
  var customCursor = document.documentElement.getAttribute("data-cursor") === "droplet";
  var finePointer = window.matchMedia("(pointer: fine)").matches;
  if (customCursor && animationsOn && finePointer && !reduceMotion) {
    var aura = document.createElement("div");
    aura.className = "cursor-aura";
    aura.setAttribute("aria-hidden", "true");
    document.body.appendChild(aura);

    var auraX = -120;
    var auraY = -120;
    var pointerX = -120;
    var pointerY = -120;
    var auraFrame = null;

    var auraTick = function () {
      auraX += (pointerX - auraX) * 0.2;
      auraY += (pointerY - auraY) * 0.2;
      aura.style.transform = "translate3d(" + auraX.toFixed(1) + "px," + auraY.toFixed(1) + "px,0) translate(-50%,-50%)";
      if (Math.abs(pointerX - auraX) > 0.3 || Math.abs(pointerY - auraY) > 0.3) {
        auraFrame = window.requestAnimationFrame(auraTick);
      } else {
        auraFrame = null;
      }
    };

    document.addEventListener(
      "pointermove",
      function (event) {
        pointerX = event.clientX;
        pointerY = event.clientY;
        aura.classList.add("is-on");
        if (!auraFrame) auraFrame = window.requestAnimationFrame(auraTick);
      },
      { passive: true }
    );

    document.addEventListener("pointerover", function (event) {
      var target = event.target;
      var interactive = target && target.closest
        ? target.closest("a, button, summary, select, input, textarea, [role='button']")
        : null;
      aura.classList.toggle("is-hover", !!interactive);
    });

    document.addEventListener("pointerdown", function () { aura.classList.add("is-press"); });
    document.addEventListener("pointerup", function () { aura.classList.remove("is-press"); });
    document.addEventListener("mouseleave", function () { aura.classList.remove("is-on"); });
    document.addEventListener("mouseenter", function () { aura.classList.add("is-on"); });
  }

  /* ------------------------------------------------------------------ Print */
  $$("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () { window.print(); });
  });
})();
