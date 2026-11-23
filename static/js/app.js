(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---------- Drawers (cart drawer, mobile filter sheet) ----------
  const openDrawer = (name) => {
    const el = $(`[data-drawer="${name}"]`);
    if (!el) return;
    el.classList.remove("hidden");
    document.documentElement.classList.add("overflow-hidden");
  };
  const closeDrawer = (el) => {
    el.classList.add("hidden");
    document.documentElement.classList.remove("overflow-hidden");
  };

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-drawer-open]");
    if (opener) openDrawer(opener.dataset.drawerOpen);

    const closer = e.target.closest("[data-drawer-close]");
    if (closer) {
      const drawer = closer.closest("[data-drawer]");
      // The filter sidebar is a static column on desktop; only close it on mobile.
      if (drawer && getComputedStyle(drawer).position === "fixed") closeDrawer(drawer);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$("[data-drawer]:not(.hidden)").forEach((d) => {
      if (getComputedStyle(d).position === "fixed") closeDrawer(d);
    });
  });

  // ---------- Search suggestions (sample data; will call the backend later) ----------
  const SUGGESTIONS = [
    { title: "اشتراک ChatGPT Plus", keys: ["chatgpt", "چت جی پی تی", "چت‌جی‌پی‌تی", "openai", "gpt"] },
    { title: "اشتراک Gemini Advanced", keys: ["gemini", "جمینای", "جمنای", "هوش مصنوعی گوگل", "google"] },
    { title: "اشتراک Claude Pro", keys: ["claude", "کلود", "anthropic"] },
    { title: "اشتراک Midjourney", keys: ["midjourney", "میدجرنی", "تولید تصویر"] },
    { title: "اشتراک Cursor Pro", keys: ["cursor", "کرسر", "برنامه نویسی"] },
    { title: "اشتراک Perplexity Pro", keys: ["perplexity", "پرپلکسیتی"] },
    { title: "اشتراک GitHub Copilot", keys: ["copilot", "کوپایلوت", "github"] },
  ];
  const norm = (s) => s.toLowerCase().replace(/\u200c/g, " ").replace(/ي/g, "ی").replace(/ك/g, "ک").trim();

  $$("[data-search]").forEach((box) => {
    const input = $("[data-search-input]", box);
    const panel = $("[data-search-panel]", box);
    const list = $("[data-search-results]", box);
    if (!input) return;

    const render = () => {
      const q = norm(input.value);
      if (!q) return panel.classList.add("hidden");
      const hits = SUGGESTIONS.filter((s) => norm(s.title).includes(q) || s.keys.some((k) => norm(k).includes(q)));
      list.innerHTML = hits.length
        ? hits.map((h) => `<li><a href="/design/product/" class="flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50">🔍 ${h.title}</a></li>`).join("")
        : `<li class="px-4 py-3 text-slate-500">نتیجه‌ای پیدا نشد؛ عبارت دیگری امتحان کنید.</li>`;
      panel.classList.remove("hidden");
    };
    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    document.addEventListener("click", (e) => { if (!box.contains(e.target)) panel.classList.add("hidden"); });
  });

  // ---------- Product page: variant picker ----------
  const product = $("[data-product]");
  if (product) {
    const buttons = $$("[data-variant]", product);
    const select = (btn) => {
      buttons.forEach((b) => b.setAttribute("aria-checked", String(b === btn)));
      const d = btn.dataset;
      $$("[data-variant-name]").forEach((el) => (el.textContent = d.vName));
      $$("[data-price]").forEach((el) => (el.textContent = d.vPrice));
      $$("[data-compare]").forEach((el) => { el.textContent = d.vCompare; el.hidden = !d.vCompare; });
      $$("[data-off-badge]").forEach((el) => { el.textContent = `${d.vOff}٪`; el.hidden = !d.vOff; });
      $$("[data-delivery]").forEach((el) => (el.textContent = d.vDelivery));
      $$("[data-warranty]").forEach((el) => (el.textContent = d.vWarranty));
      $$("[data-private-note]").forEach((el) => { el.classList.toggle("hidden", !d.vPrivate); el.classList.toggle("flex", !!d.vPrivate); });
      $$("[data-add-to-cart]").forEach((el) => {
        el.disabled = !d.vStock;
        el.textContent = d.vStock ? (el.closest("aside") ? "افزودن به سبد خرید" : "افزودن به سبد") : "ناموجود";
      });
      const drawerVariant = $("[data-drawer-variant]");
      if (drawerVariant) drawerVariant.textContent = d.vName;
    };
    buttons.forEach((b) => b.addEventListener("click", () => select(b)));
    if (buttons[0]) select(buttons[0]);
  }

  $$("[data-add-to-cart]").forEach((btn) => btn.addEventListener("click", () => openDrawer("cart")));

  // ---------- Tabs ----------
  $$("[data-tabs]").forEach((root) => {
    const tabs = $$("[data-tab]", root);
    tabs.forEach((tab) => tab.addEventListener("click", () => {
      tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      $$("[data-panel]", root).forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== tab.dataset.tab));
    }));
  });

  // ---------- OTP inputs: auto-advance ----------
  $$("[data-otp]").forEach((root) => {
    const inputs = $$("input", root);
    inputs.forEach((input, i) => {
      input.addEventListener("input", () => { if (input.value && inputs[i + 1]) inputs[i + 1].focus(); });
      input.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !input.value && inputs[i - 1]) inputs[i - 1].focus(); });
    });
  });
})();
